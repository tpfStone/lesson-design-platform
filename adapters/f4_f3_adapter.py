"""
f4_f3_adapter.py

将 F4 current-state.sections 转换为 F3 Classroom API 所需 materials。

本文件只负责：
- 过滤允许进入课堂模拟的 section 类型；
- 按 F4 order_index 排序；
- 跳过空正文；
- 生成 F3 所需 material，并保留 F4 section 来源信息。

不修改 F4/F3 核心业务算法。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


CLASSROOM_SECTION_TYPES = {
    "introduction",
    "exploration",
    "teaching_process",
    "practice",
    "summary",
}


def is_classroom_section(section: Dict[str, Any]) -> bool:
    """仅允许既属于课堂环节、又有非空正文的 section 进入 F3。"""
    if section.get("section_type") not in CLASSROOM_SECTION_TYPES:
        return False
    content = section.get("current_content")
    return isinstance(content, str) and bool(content.strip())


def _order_key(section: Dict[str, Any]) -> tuple[int, int]:
    """按 F4 order_index 升序；缺失/非法 order_index 放到最后并保持稳定顺序。"""
    value = section.get("order_index")
    if isinstance(value, int):
        return (0, value)
    return (1, 0)


def convert_section_to_material(
    section: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    """将单个 F4 section 转成 F3 material，并保留来源追踪信息。"""
    return {
        "id": index,
        "title": section.get("title") or f"section_{index}",
        "teaching_script": section["current_content"],
        "key_points": [],
        "metadata": {
            "source_section_id": section.get("id"),
            "source_section_type": section.get("section_type"),
            "source_order_index": section.get("order_index"),
        },
    }


def convert_f4_sections_to_f3_materials(
    sections: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """F4 sections -> F3 materials。"""
    if sections is None:
        return []

    ordered_sections = sorted(list(sections), key=_order_key)
    materials: List[Dict[str, Any]] = []

    for section in ordered_sections:
        if not is_classroom_section(section):
            continue
        materials.append(convert_section_to_material(section, len(materials) + 1))

    return materials
