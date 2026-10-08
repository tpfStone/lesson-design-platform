"""Append-only, per-attempt model accounting shared by graph and DOCX import."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from paper4_pipeline.domain.models import ModelCallAttempt


_ACTIVE: ContextVar["CallLedger | None"] = ContextVar("paper4_call_ledger", default=None)


class CallLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[ModelCallAttempt] = []

    def append(self, attempt: ModelCallAttempt) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(
                attempt.model_dump(mode="json"), ensure_ascii=False,
                sort_keys=True, separators=(",", ":"),
            ) + "\n")
            handle.flush()
        self.records.append(attempt)


def current_ledger() -> CallLedger | None:
    return _ACTIVE.get()


@contextmanager
def activate_call_ledger(path: Path) -> Iterator[CallLedger]:
    ledger = CallLedger(path)
    token = _ACTIVE.set(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE.reset(token)
