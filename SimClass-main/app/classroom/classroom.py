"""Classroom Loop —— 核心课堂循环。

    initialize_class()
    -> (User Input OR Timeout τ)   # 两种 trigger 进入同一条决策管线
    -> Manager.decide(state)
    -> Executor.execute(decision, state)
    -> Update ClassState / print / log
"""
from __future__ import annotations

from ..agents import AGENT_CLASSES
from ..controller.executor import FunctionExecutor, InvalidActionError
from ..controller.manager import Manager
from ..controller.state import ClassState
from ..llm.base import BaseLLMProvider, LLMError
from ..llm.provider import create_llm
from ..materials import load_materials
from .events import (
    ClassroomEvent,
    TRIGGER_EMPTY_ENTER,
    TRIGGER_INITIALIZATION,
    TRIGGER_TIMEOUT,
    TRIGGER_USER_INPUT,
    make_terminal_event_fn,
)
from .session_logger import SessionLogger

QUIT_COMMANDS = {"quit", "exit", "/quit", "/exit", "结束", "下课"}


class Classroom:
    def __init__(self, llm: BaseLLMProvider | None = None, debug: bool = False,
                 input_fn=None, materials: list[dict] | None = None,
                 log_dir: str = "logs", event_fn=None,
                 timeout_seconds: float = 15.0,
                 max_consecutive_timeouts: int = 3,
                 active_roles: list[str] | None = None,
                 teaching_plan: list | None = None):
        self.llm = llm if llm is not None else create_llm()
        self.agents = {cls.name: cls(self.llm) for cls in AGENT_CLASSES}
        self.plan_meta: dict = {}
        if teaching_plan and materials is None:
            from ..teaching_plan import sections_to_materials
            materials = sections_to_materials(list(teaching_plan))
        else:
            materials = materials if materials is not None else load_materials()
        self.state = ClassState(
            materials,
            self._normalize_active_roles(active_roles),
            teaching_plan=list(teaching_plan) if teaching_plan else None,
        )
        self.manager = Manager(self.llm, self.agents)
        self.executor = FunctionExecutor(self.agents)
        self.debug = debug
        self.timeout_seconds = timeout_seconds
        self.max_consecutive_timeouts = max_consecutive_timeouts
        # 事件源优先级: 显式 event_fn > 旧版阻塞 input_fn（测试/脚本注入）> 真实终端 τ
        if event_fn is not None:
            self.event_fn = event_fn
        elif input_fn is not None:
            self.event_fn = self._wrap_legacy_input(input_fn)
        else:
            self.event_fn = make_terminal_event_fn()
        self.logger = SessionLogger(log_dir)
        # Formal API/session service inspection hooks. They do not change CLI behavior.
        self.last_decision = None
        self.last_turn_error = None

    # ---------- 角色配置校验 ----------

    @staticmethod
    def _normalize_active_roles(active_roles: list[str] | None) -> list[str]:
        """None/空表示全部角色；Teacher 必须存在。"""
        known = [cls.name for cls in AGENT_CLASSES]
        if not active_roles:
            return list(known)
        unknown = [r for r in active_roles if r not in known]
        if unknown:
            raise ValueError(f"未知课堂角色: {unknown}，可用角色: {known}")
        if "teacher" not in active_roles:
            raise ValueError("Teacher 角色必须存在（课堂无法在没有教师的情况下推进）")
        selected = set(active_roles)
        return [r for r in known if r in selected]

    # ---------- 主循环 ----------

    def run(self) -> None:
        self._print_banner()
        # initialization: 课堂开始即触发第一次决策（不等待输入）
        event: ClassroomEvent | None = ClassroomEvent(TRIGGER_INITIALIZATION)
        while (event is not None and not self._is_quit(event)
               and self.state.session_status == "active"):
            self._process_event(event)
            self._run_one_turn()
            if self.state.session_status != "active":
                break
            event = self._next_event()
        self.state.end_session()
        self._print_farewell()

    def _run_one_turn(self):
        """Run one Manager -> Executor -> Agent turn and return its DialogueEntry.

        Returning the entry is backward-compatible with CLI callers (which ignore it)
        and fixes the existing API adapter, which already expects a return value.
        last_decision/last_turn_error are read-only inspection hooks for the formal
        session service and structured EventStore.
        """
        self.last_decision = None
        self.last_turn_error = None
        try:
            decision = self.manager.decide(self.state)
            self.last_decision = decision
        except LLMError as e:
            self.last_turn_error = f"manager_llm_error: {e}"
            # Do not leak a failed turn's user message into a later trigger.
            self.state.pending_user_message = None
            print(f"[SYSTEM] LLM 调用失败: {e}")
            return None

        user_msg = self.state.pending_user_message
        if self.debug:
            status = "PAUSED_FOR_USER" if not self.state.autonomous_mode else "AUTONOMOUS"
            print(f"\n[TRIGGER]\n{self.state.last_trigger_type}")
            print(f"[STATE]\nconsecutive_timeout_count = {self.state.consecutive_timeout_count}\n"
                  f"autonomous_mode = {str(self.state.autonomous_mode).lower()}\n"
                  f"status = {status}")
        self._print_manager(decision)

        try:
            entry = self._execute_decision(decision)
        except LLMError as e:
            # Agent 响应生成失败（网络抖动 / 超时 / 限流）: 跳过本轮而非崩溃。
            # 旧实现此处异常会杀死课堂线程，导致 WebUI 卡在"已暂停"无法恢复。
            self.last_turn_error = f"agent_llm_error: {e}"
            print(f"[SYSTEM] Agent 响应生成失败，跳过本轮: {e}")
            self.state.pending_user_message = None
            return None
        if entry is None:  # 决策两次无效，跳过本轮
            self.last_turn_error = "invalid_action_after_retry"
            self.state.pending_user_message = None
            return None

        self._print_agent(entry)
        self.logger.log_turn(entry.speaker, entry.function, decision.reason,
                             user_msg, entry.content,
                             trigger_type=self.state.last_trigger_type,
                             consecutive_timeout_count=self.state.consecutive_timeout_count,
                             autonomous_mode=self.state.autonomous_mode)
        self.state.pending_user_message = None

        if decision.end_class:
            self.state.end_session()
        return entry

    def _execute_decision(self, decision):
        """执行决策；决策与状态冲突时带 feedback 让 Manager 重试一次。

        返回 DialogueEntry；两次决策均无效时返回 None。
        LLMError（网络/超时/限流）向上抛出，由 _run_one_turn 统一跳过本轮，
        保证课堂线程不会因单次 LLM 调用失败而死亡。
        """
        try:
            return self.executor.execute(decision, self.state)
        except InvalidActionError as e:
            print(f"[SYSTEM] 决策无效: {e}，请求 Manager 重新决策...")
            decision = self.manager.decide(self.state, feedback=f"刚才的决策无效: {e}")
            self._print_manager(decision)
            try:
                return self.executor.execute(decision, self.state)
            except InvalidActionError as e2:
                print(f"[SYSTEM] 仍然无效，跳过本轮: {e2}")
                return None

    # ---------- 事件: User Input OR Timeout τ ----------

    def _next_event(self) -> ClassroomEvent | None:
        """等待下一个事件: 用户输入，或 τ 秒超时。二者进入同一条决策管线。

        暂停判断只看 autonomous_mode（PAUSED_FOR_USER），
        与 consecutive_timeout_count（计数）是两个独立概念。
        """
        if not self.state.autonomous_mode:
            # PAUSED_FOR_USER: 防失控暂停，无限期等待用户输入
            print(f"\n[PAUSED]\n课堂已连续自主运行 {self.state.consecutive_timeout_count} 次。\n"
                  "请输入问题继续，或直接按 Enter 让课堂恢复自主运行。")
            timeout = None
        else:
            timeout = self.timeout_seconds
        try:
            return self.event_fn(timeout)
        except KeyboardInterrupt:
            return None

    def _process_event(self, event: ClassroomEvent) -> None:
        """事件先写入 ClassState，再进入同一条 Manager -> Executor 管线。

        暂停/恢复状态机:
            timeout 使计数累加，达到 MAX 时进入 PAUSED_FOR_USER（本轮动作照常执行）。
            有意义输入 / 暂停下的空回车 -> 恢复自主模式并清零计数，开启新超时周期。
        """
        self.state.record_trigger(event.trigger_type)
        if event.trigger_type == TRIGGER_TIMEOUT:
            print("[SYSTEM] 用户超时未输入 (timeout τ)，课堂自主继续。")
            if self.state.consecutive_timeout_count >= self.max_consecutive_timeouts:
                # 本轮动作执行完毕后进入 PAUSED_FOR_USER（见 _next_event）
                self.state.autonomous_mode = False
        elif event.trigger_type in (TRIGGER_USER_INPUT, TRIGGER_EMPTY_ENTER):
            if not self.state.autonomous_mode:
                self.state.autonomous_mode = True
                if event.trigger_type == TRIGGER_USER_INPUT:
                    print("\n[RESUMED]\n收到你的问题，课堂恢复自主运行。")
                else:
                    print("\n[RESUMED]\n课堂恢复自主运行，下一轮将重新计时。")
        if event.trigger_type == TRIGGER_USER_INPUT and event.user_message:
            self.state.add_user_message(event.user_message)
        # timeout / empty_enter 不伪造用户消息

    def _is_quit(self, event: ClassroomEvent) -> bool:
        return (event.trigger_type == TRIGGER_USER_INPUT
                and bool(event.user_message)
                and event.user_message.lower() in QUIT_COMMANDS)

    def _wrap_legacy_input(self, input_fn):
        """兼容旧的阻塞式 input_fn（测试/脚本注入用），忽略 timeout、永不超时。"""
        def wait(timeout):
            try:
                line = input_fn("You: ")
            except (EOFError, KeyboardInterrupt):
                return None
            text = (line or "").strip()
            if not text:
                return ClassroomEvent(TRIGGER_EMPTY_ENTER)
            return ClassroomEvent(TRIGGER_USER_INPUT, user_message=text)
        return wait

    # ---------- CLI 输出 ----------

    def _print_banner(self) -> None:
        print("=" * 62)
        if self.state.teaching_plan:
            print(f"SimClass MVP — 真实教案: {self.plan_meta.get('title', '教学过程')}")
        else:
            print("SimClass MVP — Introduction to Large Language Models")
        print(f"LLM Provider: {self.llm.name}"
              + ("   [DEBUG]" if self.debug else ""))
        print(f"提示: 输入消息回车发送；静默 {self.timeout_seconds:g} 秒后课堂自主继续"
              f"（连续 {self.max_consecutive_timeouts} 轮后暂停等待输入）；输入 quit 下课。")
        print("教学环节:" if self.state.teaching_plan else "课程大纲:")
        for i, m in enumerate(self.state.materials, 1):
            dur = m.get("duration_minutes")
            suffix = f"（{dur}分钟）" if dur else ""
            print(f"  {i}. {m['title']}{suffix}")
        if len(self.state.active_roles) < len(self.agents):
            display = [self.agents[r].display_name for r in self.state.active_roles]
            print("本节课参与角色: " + ", ".join(display))
        print("=" * 62)

    def _print_manager(self, decision) -> None:
        print("\n[MANAGER]")
        print(f"speaker = {decision.speaker}")
        print(f"function = {decision.function}")
        if self.debug:
            print(f"reason = {decision.reason}")
            print(f"end_class = {decision.end_class}")

    def _print_agent(self, entry) -> None:
        display = self.agents[entry.speaker].display_name if entry.speaker in self.agents \
            else entry.speaker.upper()
        print(f"\n[{display}]\n{entry.content}")

    def _print_farewell(self) -> None:
        print("\n" + "=" * 62)
        print("[SYSTEM] Class dismissed. 下课！")
        print(f"[SYSTEM] 会话日志已保存: {self.logger.path}")
        print("=" * 62)
