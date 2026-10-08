"""Scenario runner —— 驱动 Manager/Executor 循环并记录每轮决策轨迹。

复用 Classroom 已有的 manager / executor / state / logger 组件，
不复制、不修改核心课堂循环（本模块只做验证层的驱动与观测）。

每轮记录:
    turn_id / current_material_before / speaker / function / reason /
    validation_status / current_material_after / session_status

验证层基础设施（不属于课堂行为）:
    pace_seconds      轮间节奏控制，避免触发 LLM 服务商限流
    429 backoff       命中 429 限流时退避后整轮重试一次
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.controller.executor import InvalidActionError
from app.llm.base import LLMError

RATE_LIMIT_BACKOFF_SECONDS = 30.0
MAX_LLM_ATTEMPTS_PER_TURN = 3


@dataclass
class ScenarioResult:
    """一次场景运行的完整观测结果。"""
    records: list[dict] = field(default_factory=list)
    crashed: bool = False
    error: str = ""
    # None: 不适用（课程已结束，无需继续性检查）
    continuation_ok: bool | None = None
    final_status: str = "active"

    @property
    def finished(self) -> bool:
        return self.final_status == "finished"


def _material_title(state) -> str | None:
    m = state.current_material
    return m["title"] if m else None


def _run_turn_once(classroom, state):
    """单轮一次尝试: decide -> execute（含与核心循环一致的一次决策重试）。"""
    decision = classroom.manager.decide(state)
    validation_status = "ok"
    try:
        entry = classroom.executor.execute(decision, state)
    except InvalidActionError as e:
        retry = classroom.manager.decide(state, feedback=f"刚才的决策无效: {e}")
        try:
            entry = classroom.executor.execute(retry, state)
            decision = retry
        except InvalidActionError as e2:
            validation_status = f"invalid_action: {e2}"
            state.pending_user_message = None  # 与核心循环一致，避免重复处理
    return decision, entry, validation_status


def _run_turn_with_retry(classroom, state):
    """带瞬时故障退避的单轮执行: LLMError（429 限流 / 网络瞬断等）退避后整轮重试，
    最多 MAX_LLM_ATTEMPTS_PER_TURN 次。"""
    for attempt in range(MAX_LLM_ATTEMPTS_PER_TURN):
        try:
            return _run_turn_once(classroom, state)
        except LLMError:
            if attempt == MAX_LLM_ATTEMPTS_PER_TURN - 1:
                raise
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)


def run_scenario(classroom, user_message: str | None = None,
                 max_turns: int = 6, with_continuation: bool = True,
                 pace_seconds: float = 0.0) -> ScenarioResult:
    """运行一个验证场景。

    流程（对应任务第 4 节伪代码）:
        注入用户消息(可选)
        for turn in range(max_turns):        # 安全上限，防止验证运行失控
            decision = manager.decide(state)
            entry = executor.execute(decision, state)
            记录 trace
    """
    state = classroom.state
    result = ScenarioResult()
    if user_message:
        state.add_user_message(user_message)

    try:
        for turn_id in range(1, max_turns + 1):
            if state.session_status != "active":
                break
            if pace_seconds and turn_id > 1:
                time.sleep(pace_seconds)
            mat_before = _material_title(state)
            user_msg = user_message if turn_id == 1 else None

            decision, entry, validation_status = _run_turn_with_retry(classroom, state)
            mat_after = _material_title(state)

            if validation_status == "ok":
                if decision.end_class:
                    state.end_session()
                classroom.logger.log_turn(
                    decision.speaker, decision.function, decision.reason,
                    user_msg, entry.content,
                )
                state.pending_user_message = None

            result.records.append({
                "turn_id": turn_id,
                "current_material_before": mat_before,
                "speaker": decision.speaker,
                "function": decision.function,
                "reason": decision.reason,
                "validation_status": validation_status,
                "current_material_after": mat_after,
                "session_status": state.session_status,
            })
    except Exception as e:  # 验证层需要捕获一切异常，用于判定 "no crash"
        result.crashed = True
        result.error = f"{type(e).__name__}: {e}"

    result.final_status = state.session_status

    # 继续性检查: 场景结束后课堂还能否正常走一轮（不注入新的用户消息）
    if with_continuation and not result.crashed and state.session_status == "active":
        try:
            decision, entry, _ = _run_turn_with_retry(classroom, state)
            classroom.logger.log_turn(decision.speaker, decision.function,
                                      decision.reason, None, entry.content)
            state.pending_user_message = None
            result.continuation_ok = True
        except Exception:  # noqa: BLE001
            result.continuation_ok = False

    return result
