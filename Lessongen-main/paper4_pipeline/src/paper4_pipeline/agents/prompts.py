"""External prompt registry with immutable content hashes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


PROMPT_FILES = {
    "design_architect_prompt": ("design_architect_prompt.v1.0.md", "1.0"),
    "writer_prompt": ("writer_prompt.v1.3.md", "1.3"),
    "subject_critic_prompt": ("subject_critic_prompt.v1.2.md", "1.2"),
    "pedagogy_critic_prompt": ("pedagogy_critic_prompt.v1.3.md", "1.3"),
    "alignment_critic_prompt": ("alignment_critic_prompt.v1.1.md", "1.1"),
    "validator_prompt": ("validator_prompt.v1.6.md", "1.6"),
    "judge_prompt": ("judge_prompt.v1.3.md", "1.3"),
    "rewriter_prompt": ("rewriter_prompt.v1.6.md", "1.6"),
    "rewrite_patch_prompt": ("rewrite_patch_prompt.v1.3.md", "1.3"),
    "docx_normalizer_prompt": ("docx_normalizer_prompt.v1.1.md", "1.1"),
    "docx_overview_prompt": ("docx_overview_prompt.v1.0.md", "1.0"),
    "docx_activities_prompt": ("docx_activities_prompt.v1.0.md", "1.0"),
}


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    version: str
    path: Path
    content: str
    sha256: str


def default_prompt_root() -> Path:
    return Path(__file__).resolve().parents[3] / "prompts"


def load_prompt(prompt_id: str, prompt_root: Path | None = None) -> PromptSpec:
    if prompt_id not in PROMPT_FILES:
        raise ValueError(f"unknown prompt_id: {prompt_id}")
    root = (prompt_root or default_prompt_root()).resolve()
    filename, version = PROMPT_FILES[prompt_id]
    path = root / filename
    content = path.read_text(encoding="utf-8").strip()
    if len(content) < 500:
        raise ValueError(f"prompt is unexpectedly short: {path}")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return PromptSpec(
        prompt_id=prompt_id,
        version=version,
        path=path,
        content=content,
        sha256=digest,
    )
