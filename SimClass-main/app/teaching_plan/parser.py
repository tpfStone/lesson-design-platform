"""TeachingPlanParser —— 轻量 Markdown 表格解析器。

把上游 teachingScript 中的「教学过程」Markdown 表格解析成独立教学环节。
不调用 LLM，不做内容补写；解析失败明确报错。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedTeachingSection:
    section_index: int
    title: str
    duration_minutes: int | None = None
    teacher_activity: str = ""
    student_task: str = ""
    evaluation_control: str = ""
    raw_content: str = field(default="", repr=False)

    def to_dict(self) -> dict:
        return {
            "section_index": self.section_index,
            "title": self.title,
            "duration_minutes": self.duration_minutes,
            "teacher_activity": self.teacher_activity,
            "student_task": self.student_task,
            "evaluation_control": self.evaluation_control,
            "raw_content": self.raw_content,
        }


_DURATION_RE = re.compile(r"[（(]\s*(\d+)\s*分钟\s*[)）]")
_BOLD_TITLE_RE = re.compile(r"^\*\*(.+?)\*\*(.*)$", re.S)


def parse_teaching_plan(plan) -> list[ParsedTeachingSection]:
    return parse_teaching_script(plan.teachingScript)


def parse_teaching_script(teaching_script: str) -> list[ParsedTeachingSection]:
    if not isinstance(teaching_script, str) or not teaching_script.strip():
        raise ValueError("teachingScript 必须是非空字符串")
    rows = _extract_table_rows(teaching_script.lstrip("\ufeff"))
    if not rows:
        raise ValueError(
            "teachingScript 中未找到教学过程 Markdown 表格数据行"
            "（需要包含表头‘环节与教师活动’的表格）"
        )
    sections: list[ParsedTeachingSection] = []
    for raw_line, cells in rows:
        teacher_cell = cells[0] if len(cells) > 0 else ""
        student_task = cells[1].strip() if len(cells) > 1 else ""
        evaluation = cells[2].strip() if len(cells) > 2 else ""
        title, duration, activity = _parse_teacher_cell(teacher_cell)
        if not (title or activity or student_task or evaluation):
            continue
        sections.append(ParsedTeachingSection(
            section_index=len(sections),
            title=title or f"教学环节 {len(sections) + 1}",
            duration_minutes=duration,
            teacher_activity=activity,
            student_task=student_task,
            evaluation_control=evaluation,
            raw_content=raw_line,
        ))
    if not sections:
        raise ValueError("教学过程表格中没有可用的教学环节数据行")
    return sections


def _extract_table_rows(text: str) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    header_seen = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not any(cells):
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        if any("环节与教师活动" in c for c in cells):
            header_seen = True
            rows.clear()
            continue
        if header_seen:
            rows.append((line, cells))
    return rows


def _parse_teacher_cell(cell: str) -> tuple[str, int | None, str]:
    text = cell.strip()
    duration: int | None = None
    m = _BOLD_TITLE_RE.match(text)
    if m:
        head, rest = m.group(1).strip(), m.group(2)
        dm = _DURATION_RE.search(head)
        if dm:
            duration = int(dm.group(1))
            title = head[:dm.start()].strip()
        else:
            title = head.strip()
        activity = rest
    else:
        dm = _DURATION_RE.search(text[:80])
        if dm:
            title = text[:dm.start()].strip().strip("；;*# ")
            duration = int(dm.group(1))
            activity = text[dm.end():]
        else:
            head, sep, activity = text.partition("；")
            if not sep:
                head, sep, activity = text.partition(";")
            title, activity = head.strip().strip("*# "), (activity if sep else "")
    activity = activity.strip().lstrip("；;：:、 ").strip()
    return title, duration, activity


def sections_to_materials(sections: list[ParsedTeachingSection]) -> list[dict]:
    return [{
        "id": f"section-{s.section_index + 1}",
        "title": s.title,
        "teaching_script": s.teacher_activity,
        "key_points": [],
        "duration_minutes": s.duration_minutes,
        "student_task": s.student_task,
        "evaluation_control": s.evaluation_control,
        "raw_content": s.raw_content,
    } for s in sections]
