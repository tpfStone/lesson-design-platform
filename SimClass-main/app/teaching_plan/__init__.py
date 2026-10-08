"""真实教案输入适配：上游 JSON -> Schema 校验 -> 轻量解析 -> 教学环节。"""
from .models import TeachingPlanInput
from .parser import (
    ParsedTeachingSection,
    parse_teaching_plan,
    parse_teaching_script,
    sections_to_materials,
)

__all__ = [
    "TeachingPlanInput",
    "ParsedTeachingSection",
    "parse_teaching_plan",
    "parse_teaching_script",
    "sections_to_materials",
]
