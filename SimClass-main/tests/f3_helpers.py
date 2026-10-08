from __future__ import annotations

import time

from app.contracts.session import CreateSessionRequest


def one_material_request(
    key: str,
    *,
    lesson: str = "lesson-1",
    version: str = "version-1",
    timeout: float = 0.02,
    max_timeouts: int = 100,
    max_events: int = 20,
    max_wall: int = 30,
):
    return CreateSessionRequest.model_validate(
        {
            "lessonId": lesson,
            "versionId": version,
            "modelMode": "MOCK",
            "requestKey": key,
            "timeoutSeconds": timeout,
            "maxConsecutiveTimeouts": max_timeouts,
            "maxEvents": max_events,
            "maxWallClockSeconds": max_wall,
            "materials": [
                {
                    "materialId": "m1",
                    "title": "一次函数定义",
                    "teachingScript": "一次函数一般形式为 y=kx+b，其中 k 不等于 0。",
                    "keyPoints": ["k 不等于 0", "一般形式 y=kx+b"],
                    "sourceSectionId": "section-new-knowledge",
                }
            ],
        }
    )


def wait_until(predicate, timeout=2.0, interval=0.01):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not reached before timeout")
