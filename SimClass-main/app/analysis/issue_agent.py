from __future__ import annotations

import json
from typing import Any

from app.contracts.analysis import AnalysisResult, IssueRecord
from app.contracts.event import ClassroomEventRecord
from app.llm.base import LLMError
from .evidence_validator import EvidenceValidator
from .issue_consolidator import IssueConsolidator


SYSTEM_PROMPT = """你是 F3 课堂模拟的 IssueAnalysisAgent。
你只分析给定的真实课堂事件，不得补写、改写或虚构课堂事实。
目标是发现“教案实施层”可操作问题，而不是复述课堂。

硬性规则：
1. 每个 issue 至少引用一个输入中真实存在的 eventId。
2. contentQuote 必须逐字摘自该 event 的 content，禁止转述后当成引文。
3. resolvedInSimulation=true 时，resolutionEvidenceEventIds 必须引用更晚发生的事件。
4. 不得把请求耗时当作教学时长。
5. targetLessonSection 只能填写输入材料的 title/materialId/sourceSectionId；无法定位就填 null。
6. 类别只能是 student_misconception / insufficient_explanation /
   participation_imbalance / interaction_gap / pace_risk / material_transition /
   assessment_gap / other。
7. severity 只能是 LOW / MEDIUM / HIGH / CRITICAL。
8. 最多输出 12 个 issues。没有证据就返回空数组。

只输出严格 JSON：
{"issues":[{"nativeIssueId":"ISSUE-01","category":"...","severity":"MEDIUM",
"title":"...","problem":"...","evidence":[{"eventId":"...","sequence":1,
"speaker":"...","contentQuote":"..."}],"resolvedInSimulation":false,
"resolutionEvidenceEventIds":[],"resolution":null,"suggestedAction":"...",
"targetLessonSection":null,"confidence":0.8}]}
"""


class IssueAnalysisAgent:
    def __init__(
        self,
        llm,
        validator: EvidenceValidator | None = None,
        consolidator: IssueConsolidator | None = None,
    ):
        self.llm = llm
        self.validator = validator or EvidenceValidator()
        self.consolidator = consolidator or IssueConsolidator(max_final_issues=5)

    def analyze(
        self,
        *,
        session_id: str,
        version_id: str,
        events: list[ClassroomEventRecord],
        materials: list[dict[str, Any]],
        session_status: str,
        stop_reason: str | None,
        model_mode: str | None = None,
    ) -> AnalysisResult:
        base_warnings: list[str] = []
        if session_status in {"INTERRUPTED", "FAILED"}:
            base_warnings.append(
                f"analysis scope is partial because session status is {session_status}"
            )
            if stop_reason:
                base_warnings.append(f"session stopReason: {stop_reason}")
        if not events:
            base_warnings.append("no classroom events available; no issues generated")
            return AnalysisResult(
                sessionId=session_id,
                sourceVersionId=version_id,
                modelMode=model_mode,
                issues=[],
                actionItems=[],
                warnings=base_warnings,
            )

        if getattr(self.llm, "name", "") == "mock":
            candidates = self._mock_candidates(events, materials)
            outcome = self.validator.validate(candidates, events, materials)
            consolidated = self.consolidator.consolidate(outcome.valid_issues, materials)
            final_outcome = self.validator.validate(
                [issue.model_dump(by_alias=True) for issue in consolidated.issues],
                events,
                materials,
            )
            return self._result(
                session_id,
                version_id,
                final_outcome.valid_issues,
                base_warnings
                + outcome.warnings
                + consolidated.warnings
                + final_outcome.warnings,
                model_mode,
            )

        # Long sessions are analyzed hierarchically by material / bounded event window.
        # Each chunk is independently evidence-validated and gets at most one repair retry.
        chunks = self._chunk_events(events, max_events=20)
        collected: list[IssueRecord] = []
        all_warnings = list(base_warnings)
        for chunk_index, chunk in enumerate(chunks, start=1):
            issues, warnings = self._analyze_validated_chunk(chunk, materials)
            collected.extend(issues)
            all_warnings.extend(
                f"chunk {chunk_index}: {warning}" for warning in warnings
            )

        # Post-process only evidence-validated candidates. Similar engagement/feedback
        # issues in the same lesson material are merged, then ranked and capped before
        # one final global evidence validation against the complete session.
        consolidated = self.consolidator.consolidate(collected, materials)
        all_warnings.extend(consolidated.warnings)
        final_outcome = self.validator.validate(
            [issue.model_dump(by_alias=True) for issue in consolidated.issues],
            events,
            materials,
        )
        all_warnings.extend(final_outcome.warnings)
        return self._result(
            session_id, version_id, final_outcome.valid_issues, all_warnings, model_mode
        )

    def _analyze_validated_chunk(
        self,
        events: list[ClassroomEventRecord],
        materials: list[dict[str, Any]],
    ) -> tuple[list[IssueRecord], list[str]]:
        first_raw, first_error = self._call_llm(events, materials, repair_warnings=None)
        if first_error:
            return [], [first_error]
        first_outcome = self.validator.validate(first_raw, events, materials)
        if not first_outcome.warnings:
            return first_outcome.valid_issues, []

        second_raw, second_error = self._call_llm(
            events, materials, repair_warnings=first_outcome.warnings
        )
        if second_error:
            return first_outcome.valid_issues, first_outcome.warnings + [second_error]
        second_outcome = self.validator.validate(second_raw, events, materials)
        return second_outcome.valid_issues, first_outcome.warnings + second_outcome.warnings

    @staticmethod
    def _chunk_events(
        events: list[ClassroomEventRecord], max_events: int = 20
    ) -> list[list[ClassroomEventRecord]]:
        chunks: list[list[ClassroomEventRecord]] = []
        current: list[ClassroomEventRecord] = []
        current_material: str | None = None
        for event in sorted(events, key=lambda item: item.sequence):
            material_id = event.material.material_id if event.material else None
            material_changed = current and material_id != current_material
            if current and (material_changed or len(current) >= max_events):
                chunks.append(current)
                current = []
            if not current:
                current_material = material_id
            current.append(event)
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _dedupe_issues(issues: list[IssueRecord]) -> list[IssueRecord]:
        chosen: dict[tuple[str, str, str | None], IssueRecord] = {}
        order: list[tuple[str, str, str | None]] = []
        for issue in issues:
            key = (issue.category, issue.title.strip(), issue.target_lesson_section)
            previous = chosen.get(key)
            if previous is None:
                chosen[key] = issue
                order.append(key)
            elif issue.confidence > previous.confidence:
                chosen[key] = issue
        result = [chosen[key] for key in order]
        for index, issue in enumerate(result, start=1):
            issue.native_issue_id = f"ISSUE-{index:02d}"
        return result

    def _call_llm(
        self,
        events: list[ClassroomEventRecord],
        materials: list[dict[str, Any]],
        repair_warnings: list[str] | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        payload = {
            "materials": [
                {
                    "materialId": str(m.get("materialId", m.get("id", ""))),
                    "title": m.get("title"),
                    "sourceSectionId": m.get("sourceSectionId"),
                }
                for m in materials
            ],
            "events": [e.model_dump(by_alias=True) for e in events],
        }
        user = "请分析以下课堂事件：\n" + json.dumps(payload, ensure_ascii=False)
        if repair_warnings:
            user += (
                "\n\n上一次输出未通过确定性证据校验。只修复这些问题，不要新增无证据内容：\n- "
                + "\n- ".join(repair_warnings)
            )
        try:
            raw = self.llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
            )
        except LLMError as exc:
            return [], f"IssueAnalysisAgent LLM call failed: {exc}"
        except Exception as exc:
            return [], f"IssueAnalysisAgent unexpected failure: {exc}"

        try:
            data = self._parse_json(raw)
            issues = data.get("issues", [])
            if not isinstance(issues, list):
                raise ValueError("issues must be a list")
            return issues, None
        except Exception as exc:
            return [], f"IssueAnalysisAgent returned invalid JSON: {exc}"

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("no JSON object found")
        return json.loads(text[start : end + 1])

    @staticmethod
    def _mock_candidates(
        events: list[ClassroomEventRecord], materials: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Deterministic evidence-only analyzer for MOCK functional tests.

        It flags an Agent `ask_question` when no later answer_question appears before
        the material changes. This creates a real, inspectable interaction-gap sample
        without pretending that mock output is a real-model judgment.
        """
        candidates: list[dict[str, Any]] = []
        completed = [e for e in events if e.status == "COMPLETED"]
        for event in completed:
            if event.function != "ask_question" or not event.content.strip():
                continue
            later_same_material = [
                e for e in completed
                if e.sequence > event.sequence
                and e.material is not None
                and event.material is not None
                and e.material.material_id == event.material.material_id
            ]
            answer = next((e for e in later_same_material if e.function == "answer_question"), None)
            if answer is not None:
                continue
            quote = event.content.strip()[:120]
            target = event.material.title if event.material else None
            candidates.append(
                {
                    "nativeIssueId": f"ISSUE-{len(candidates)+1:02d}",
                    "category": "interaction_gap",
                    "severity": "MEDIUM",
                    "title": "课堂提问缺少后续显式回应",
                    "problem": "课堂中出现了提问，但在同一材料范围内未观察到后续 answer_question 事件。",
                    "evidence": [
                        {
                            "eventId": event.event_id,
                            "sequence": event.sequence,
                            "speaker": event.speaker,
                            "contentQuote": quote,
                        }
                    ],
                    "resolvedInSimulation": False,
                    "resolutionEvidenceEventIds": [],
                    "resolution": None,
                    "suggestedAction": "在对应教案环节增加对该问题的回应或检查理解的追问。",
                    "targetLessonSection": target,
                    "confidence": 0.9,
                }
            )
        return candidates[:12]

    @staticmethod
    def _result(
        session_id: str,
        version_id: str,
        issues: list[IssueRecord],
        warnings: list[str],
        model_mode: str | None = None,
    ) -> AnalysisResult:
        action_items = [
            {
                "actionId": f"ACTION-{i:02d}",
                "sourceIssueId": issue.native_issue_id,
                "action": issue.suggested_action,
                "targetLessonSection": issue.target_lesson_section,
                "priority": issue.severity,
            }
            for i, issue in enumerate(issues, start=1)
        ]
        return AnalysisResult(
            sessionId=session_id,
            sourceVersionId=version_id,
            modelMode=model_mode,
            issues=issues,
            actionItems=action_items,
            warnings=warnings,
        )
