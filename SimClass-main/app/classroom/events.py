"""Classroom 事件源: User Input OR Timeout τ。

ClassroomEvent(trigger_type, user_message) —— 两种 trigger 进入同一条
Manager -> Executor 决策管线，唯一区别是触发来源。

TimedInput: 后台 daemon 线程逐行读 stdin、主线程带超时取行。
Windows 没有可移植的 select-on-stdin，这是纯 Python 下最可靠的
跨平台实现（详见文件底部"已知限制"）。
"""
from __future__ import annotations

import queue
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Optional

# 触发类型: 课堂开始 / 用户发言 / 用户空回车示意继续 / 用户超时未输入
TRIGGER_INITIALIZATION = "initialization"
TRIGGER_USER_INPUT = "user_input"
TRIGGER_EMPTY_ENTER = "empty_enter"
TRIGGER_TIMEOUT = "timeout"


@dataclass
class ClassroomEvent:
    """一次课堂事件。user_message 仅在 trigger_type == user_input 时非空。"""
    trigger_type: str
    user_message: Optional[str] = None


class TimedInput:
    """后台线程读 stdin，主线程按超时取一行。

    readline(timeout) 返回:
        str           —— 一行输入（空串 = 用户敲了空回车）
        None          —— timeout 到期，本轮没有输入
        TimedInput.EOF —— stdin 已关闭（EOF）
    timeout=None 表示无限期阻塞等待。
    """

    EOF = object()

    def __init__(self):
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._eof = False

    def _reader_loop(self) -> None:
        while True:
            try:
                line = sys.stdin.readline()
            except (OSError, ValueError):
                line = ""
            if line == "":  # EOF: 管道读完 / Ctrl+Z / Ctrl+D
                self._eof = True
                self._queue.put(self.EOF)
                return
            self._queue.put(line.rstrip("\r\n"))

    def readline(self, timeout: Optional[float] = None):
        if self._thread is None:
            self._thread = threading.Thread(target=self._reader_loop,
                                            daemon=True)
            self._thread.start()
        if self._eof:
            return self.EOF
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return item


def make_terminal_event_fn() -> Callable[[Optional[float]], Optional[ClassroomEvent]]:
    """真实终端事件源: 等待用户输入，或 τ 秒超时。

    调用方传入 timeout=None 表示自主推进已暂停，无限期等待用户输入。
    返回 None 表示 stdin 关闭（等价于 quit，课堂结束）。
    """
    reader = TimedInput()

    def wait(timeout: Optional[float]) -> Optional[ClassroomEvent]:
        if timeout is None:
            prompt = "You: "
        else:
            prompt = f"You (type a message, or wait {timeout:g} seconds): "
        print(prompt, end="", flush=True)
        line = reader.readline(timeout)
        print()  # 收掉提示行，保持后续输出整洁
        if line is None:
            return ClassroomEvent(TRIGGER_TIMEOUT)
        if line is TimedInput.EOF:
            return None
        text = line.strip()
        if not text:
            return ClassroomEvent(TRIGGER_EMPTY_ENTER)
        return ClassroomEvent(TRIGGER_USER_INPUT, user_message=text)

    return wait


# 已知限制（跨平台 timed stdin 的固有权衡）:
# 1. 用户在超时后补完的半行输入，会在下一轮等待时才被读到。
# 2. 输入线程是 daemon: 进程退出时不等待未完成的输入行。
# 3. 阻塞等待（暂停自主推进）期间 Ctrl+C 由 Classroom 捕获并优雅下课。
