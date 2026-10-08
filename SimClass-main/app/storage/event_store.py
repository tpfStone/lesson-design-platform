from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterable

from app.contracts.event import ClassroomEventRecord


class EventStore:
    """Thread-safe append store with an on-disk JSON mirror per session."""

    def __init__(self, root: str | Path, session_id: str):
        self.root = Path(root)
        self.session_id = session_id
        self.session_dir = self.root / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.session_dir / "events.json"
        self._events: list[ClassroomEventRecord] = []
        self._lock = threading.RLock()
        self._persist()

    def append(self, event: ClassroomEventRecord) -> None:
        with self._lock:
            expected = len(self._events) + 1
            if event.sequence != expected:
                raise ValueError(
                    f"event sequence must be monotonic: expected {expected}, got {event.sequence}"
                )
            if any(e.event_id == event.event_id for e in self._events):
                raise ValueError(f"duplicate eventId: {event.event_id}")
            self._events.append(event)
            self._persist()

    def all(self) -> list[ClassroomEventRecord]:
        with self._lock:
            return [e.model_copy(deep=True) for e in self._events]

    def get(self, event_id: str) -> ClassroomEventRecord | None:
        with self._lock:
            for event in self._events:
                if event.event_id == event_id:
                    return event.model_copy(deep=True)
        return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    def _persist(self) -> None:
        payload = [e.model_dump(by_alias=True) for e in self._events]
        tmp = self.events_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.events_path)
