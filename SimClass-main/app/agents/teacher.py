"""Teacher —— 唯一可以执行 tutoring functions（teach / next_material）的 Agent。"""
from .base import BaseAgent


class Teacher(BaseAgent):
    name = "teacher"
    display_name = "TEACHER"
    system_prompt = (
        "你是 SimClass 虚拟课堂中的 Teacher（教师），负责讲授课程、解答问题、"
        "深入解释概念、引导课堂节奏。你讲解清晰、耐心，善于用具体例子说明抽象概念。"
        "你是课堂里唯一有权执行教学类动作（讲授新材料、进入下一份材料）的角色。"
        "只把真实课堂历史中的学生或用户发言当作已发生的回答；若尚无实际发言，"
        "不能声称‘学生回答得很好’‘大家已经做完’等。提出问题后应等待真实的学生/用户发言，"
        "不要在同一段发言里替学生作答或直接评价其答案。"
        "请始终围绕当前学习材料，用中文以课堂口吻发言，每次发言不超过 250 字。"
    )
    allowed_functions = [
        "teach", "next_material",
        "answer_question", "elaborate", "summarize", "discuss",
    ]

    # ---------- Tutoring Functions (仅 Teacher) ----------

    def teach(self, state) -> str:
        m = state.current_material
        title = m["title"] if m else "（无）"
        instruction = (
            f"[teach] 请按教案讲授当前教学环节「{title}」。先理解教师活动要求，"
            "再转化成自然、口语化的课堂语言与学生互动，不要机械朗读教案原文；"
            "可结合学生任务与产出邀请学生参与活动，但不能编造学生已经完成的活动。"
        )
        return self._respond(state, instruction)

    def next_material(self, state) -> str:
        # 注意: executor 会先推进材料再调用本方法，所以这里的 current_material 已是新材料
        m = state.current_material
        title = m["title"] if m else "（无）"
        instruction = (
            f"[next_material] 当前教学环节已经完成，请自然地过渡并引入下一个教学环节"
            f"「{title}」，简要说明它和上一环节的联系。"
        )
        return self._respond(state, instruction)
