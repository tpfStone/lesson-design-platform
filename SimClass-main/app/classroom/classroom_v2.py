"""
classroom_v2.py

F3 API适配扩展版

说明：
- 不修改原 classroom.py 核心逻辑
- 通过给 Classroom 增加 step() 方法支持 API 单轮调用
- 不依赖不存在的 state.history

依据：
ClassState 实际保存课堂记录的字段为:
state.dialogue_history
"""

from .events import ClassroomEvent, TRIGGER_USER_INPUT
from .classroom import Classroom


def api_step(self, user_message=None):
    """
    API模式执行一次课堂推进。

    流程:
    用户输入
        ↓
    ClassState.add_user_message()
        ↓
    Manager.decide()
        ↓
    Executor.execute()
        ↓
    DialogueEntry返回
    """

    if user_message:
        event = ClassroomEvent(
            TRIGGER_USER_INPUT,
            user_message=user_message
        )
        self._process_event(event)

    # _run_one_turn内部已经完成:
    # Manager -> Executor -> Agent -> Logger -> State更新
    entry = self._run_one_turn()

    return entry


# 挂载API扩展方法
Classroom.step = api_step
