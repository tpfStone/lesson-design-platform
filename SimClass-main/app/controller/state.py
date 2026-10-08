"""ClassState —— SimClass 课堂的全局状态，Manager 与 FunctionExecutor 的唯一数据源。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DialogueEntry:
    """一条课堂发言记录（Teacher / Assistant / Classmates / User）。"""
    speaker: str
    function: str
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


@dataclass
class ManagerDecision:
    """Manager Agent 的决策输出：speaker + function (+ reason / end_class)。"""
    speaker: str
    function: str
    reason: str = ""
    end_class: bool = False


class ClassState:
    """课堂状态。

    teaching_plan 仅用于真实教案模式，和 materials 共用同一个游标。
    active_roles 是本节课真正可被 Manager 选择的角色集合。
    """

    def __init__(self, materials: list[dict], active_roles: list[str],
                 teaching_plan: Optional[list] = None):
        self.materials = materials
        self.material_index = 0
        self.taught_materials: list[str] = []
        self.dialogue_history: list[DialogueEntry] = []
        self.teaching_plan: list = list(teaching_plan) if teaching_plan else []
        self.active_roles: list[str] = list(active_roles)
        # 兼容旧测试/旧调用：class_roles 继续保留为只读语义别名。
        self.class_roles: list[str] = self.active_roles
        self.last_speaker: Optional[str] = None
        self.last_function: Optional[str] = None
        self.session_status: str = "active"
        self.pending_user_message: Optional[str] = None
        self.last_trigger_type: str = "initialization"
        self.consecutive_timeout_count: int = 0
        self.autonomous_mode: bool = True

    @property
    def current_material(self) -> Optional[dict]:
        if 0 <= self.material_index < len(self.materials):
            return self.materials[self.material_index]
        return None

    @property
    def all_materials_finished(self) -> bool:
        return self.material_index >= len(self.materials)

    @property
    def remaining_materials(self) -> list[str]:
        if self.all_materials_finished:
            return []
        return [m["title"] for m in self.materials[self.material_index:]]

    @property
    def current_material_taught(self) -> bool:
        m = self.current_material
        return m is not None and m["title"] in self.taught_materials

    def mark_taught(self) -> None:
        m = self.current_material
        if m and m["title"] not in self.taught_materials:
            self.taught_materials.append(m["title"])

    def advance_material(self) -> Optional[dict]:
        self.mark_taught()
        if not self.all_materials_finished:
            self.material_index += 1
        return self.current_material

    @property
    def current_section_index(self) -> int:
        return self.material_index

    @property
    def current_section(self) -> Optional[object]:
        if not self.teaching_plan:
            return None
        if 0 <= self.material_index < len(self.teaching_plan):
            return self.teaching_plan[self.material_index]
        return None

    @property
    def completed_sections(self) -> list[str]:
        return list(self.taught_materials)

    def advance_section(self) -> Optional[dict]:
        return self.advance_material()

    def add_entry(self, entry: DialogueEntry) -> None:
        self.dialogue_history.append(entry)
        self.last_speaker = entry.speaker
        self.last_function = entry.function

    def add_user_message(self, text: str) -> None:
        self.add_entry(DialogueEntry(speaker="user", function="user_message", content=text))
        self.pending_user_message = text

    def recent_dialogue(self, n: int = 8) -> list[DialogueEntry]:
        return self.dialogue_history[-n:]

    def record_trigger(self, trigger_type: str) -> None:
        self.last_trigger_type = trigger_type
        if trigger_type == "timeout":
            self.consecutive_timeout_count += 1
        elif trigger_type == "user_input":
            self.consecutive_timeout_count = 0
        elif trigger_type == "empty_enter" and not self.autonomous_mode:
            self.consecutive_timeout_count = 0

    def end_session(self) -> None:
        self.session_status = "finished"
