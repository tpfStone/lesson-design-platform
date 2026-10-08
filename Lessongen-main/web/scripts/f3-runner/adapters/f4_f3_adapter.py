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

import re
from typing import Any, Dict, Iterable, List


CLASSROOM_SECTION_TYPES = {
    "introduction",
    "exploration",
    "teaching_process",
    "practice",
    "summary",
}

# F4 may return a whole DOCX teaching process as one section. Unlike F3's
# Markdown-table parser, this recognizes explicit numbered lesson steps.
_PROCESS_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]{1,3}[、.．]\s*教学过程\s*$",
    re.MULTILINE,
)
_NEXT_CHAPTER = re.compile(
    r"^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]{1,3}[、.．]\s*\S+",
    re.MULTILINE,
)
_STEP_HEADING = re.compile(r"^\s*(\d{1,2})[.．、]\s*(\S[^\r\n]*)$", re.MULTILINE)


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


def _numbered_teaching_materials(section: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    """Split only unambiguous teaching steps; never invent missing content."""
    content = section["current_content"].strip()
    heading = _PROCESS_HEADING.search(content)
    if heading:
        remainder = content[heading.end():]
        next_chapter = _NEXT_CHAPTER.search(remainder)
        process = (remainder[:next_chapter.start()] if next_chapter else remainder).strip()
        if not process:
            raise ValueError("教案的‘教学过程’没有正文；请先补全并保存新版本，再开始课堂推演")
    else:
        process = content

    matches = list(_STEP_HEADING.finditer(process))
    step_numbers = [int(match.group(1)) for match in matches]
    # A list of objectives or exercises is not necessarily a teaching sequence.
    if (len(matches) < 2 or step_numbers != list(range(1, len(matches) + 1))
            or not any(word in process for word in ("教师活动", "学生活动","teacher activities", "student activities","teacher activitiey", "student activitiey"))):
        single = convert_section_to_material(section, index)
        single["teaching_script"] = process
        return [single]

    source_id = str(section.get("id") or f"section-{index}")
    result: List[Dict[str, Any]] = []
    for position, match in enumerate(matches):
        block_end = matches[position + 1].start() if position + 1 < len(matches) else len(process)
        block = process[match.start():block_end].strip()
        if not block:
            continue
        result.append({
            "id": f"{source_id}-step-{position + 1}",
            "title": match.group(2).strip(),
            "teaching_script": block,
            "key_points": [],
            "metadata": {
                "source_section_id": section.get("id"),
                "source_section_type": section.get("section_type"),
                "source_order_index": section.get("order_index"),
                "teaching_step_index": position + 1,
                "teaching_step_title": match.group(2).strip(),
            },
        })
    return result


def convert_f4_sections_to_f3_materials(
    sections: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """F4 sections -> F3 materials。

    优先使用可识别的课堂环节。旧版/不同解析器可能生成中文或自定义
    section_type；若严格筛选结果为空，则退回到全部非空节次，确保一份
    已选择的有效教案可以独立进入课堂模拟。
    """
    if sections is None:
        return []

    ordered_sections = sorted(list(sections), key=_order_key)
    materials: List[Dict[str, Any]] = []

    for section in ordered_sections:
        if not is_classroom_section(section):
            continue
        if section.get("section_type") == "teaching_process":
            materials.extend(_numbered_teaching_materials(section, len(materials) + 1))
        else:
            materials.append(convert_section_to_material(section, len(materials) + 1))

    if materials:
        return materials

    # Compatibility fallback: do not discard a valid lesson merely because its
    # parser used an unknown/localized section_type.
    for section in ordered_sections:
        content = section.get("current_content")
        if not isinstance(content, str) or not content.strip():
            continue
        materials.append(convert_section_to_material(section, len(materials) + 1))

    return materials
