"""F3 Complete Classroom Simulation API.

Formal v2 contract:
- sessionId-isolated, asynchronous dynamic classroom sessions
- Start/Pause/Resume/End/Timeout settings
- structured events/result/artifacts
- evidence-constrained IssueAnalysisAgent

Legacy /start /message /{id}/state adapters remain during migration.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.contracts.session import CreateSessionRequest, SettingsPatch
from app.web.service import ClassroomService


app = FastAPI(title="F3 Complete Classroom Simulation API", version="3.0")
service = ClassroomService(
    storage_root=os.getenv("F3_STORAGE_ROOT", "runtime/f3_sessions")
)


class MessageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    message: str = Field(
        validation_alias=AliasChoices("message", "content"), min_length=1
    )


class LegacyMaterial(BaseModel):
    id: str | int
    title: str
    teaching_script: str
    key_points: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacySource(BaseModel):
    module: str = "F4"
    session_id: str = "legacy"
    lesson_plan_id: str = "legacy"


class LegacyStartRequest(BaseModel):
    lesson_id: str
    version_id: str
    source: LegacySource | None = None
    materials: list[LegacyMaterial]
    model_mode: str | None = None
    request_key: str | None = None


class LegacyMessageRequest(BaseModel):
    session_id: str
    message: str


def _not_found(session_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"session not found: {session_id}")


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
@app.get("/health")
def health():
    return {
        "status": "up",
        "service": "F3 Complete Classroom Simulation API",
        "version": "3.0",
        "port": 8003,
    }


@app.post("/api/classroom/sessions", status_code=status.HTTP_201_CREATED)
def create_session(request: CreateSessionRequest, response: Response):
    try:
        snapshot, idempotent = service.create_session(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {**snapshot, "idempotentReplay": idempotent}


@app.get("/api/classroom/sessions/{session_id}")
def get_session(session_id: str):
    try:
        return service.get_session(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc


@app.get("/api/classroom/sessions/{session_id}/events")
def get_events(session_id: str):
    try:
        return {"sessionId": session_id, "events": service.get_events(session_id)}
    except KeyError as exc:
        raise _not_found(session_id) from exc


@app.post("/api/classroom/sessions/{session_id}/messages", status_code=202)
def send_message(session_id: str, request: MessageRequest):
    try:
        snapshot = service.send_message(session_id, request.message)
        return {"accepted": True, "session": snapshot}
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except (ValueError, RuntimeError) as exc:
        raise _bad_request(exc) from exc


@app.post("/api/classroom/sessions/{session_id}/pause")
def pause(session_id: str):
    try:
        return service.pause(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except RuntimeError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/classroom/sessions/{session_id}/resume")
def resume(session_id: str):
    try:
        return service.resume(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except RuntimeError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/classroom/sessions/{session_id}/end")
def end(session_id: str):
    try:
        return service.end(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc


@app.patch("/api/classroom/sessions/{session_id}/settings")
def patch_settings(session_id: str, patch: SettingsPatch):
    try:
        return service.patch_settings(session_id, patch)
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except RuntimeError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/classroom/sessions/{session_id}/analyze")
def analyze(session_id: str):
    try:
        return service.analyze(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc
    except RuntimeError as exc:
        raise _bad_request(exc) from exc


@app.get("/api/classroom/sessions/{session_id}/result")
def get_result(session_id: str):
    try:
        return service.get_result(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc


@app.get("/api/classroom/sessions/{session_id}/artifacts/{kind}")
def get_artifact(session_id: str, kind: str):
    try:
        path = service.artifact_path(session_id, kind)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"artifact not found: {kind}") from exc
    return FileResponse(path, filename=path.name)


# ---------------------------------------------------------------------------
# Legacy migration adapters. These keep the old URLs alive without reintroducing
# the global singleton/synchronous step implementation.
# ---------------------------------------------------------------------------

@app.post("/api/classroom/start")
def legacy_start(request: LegacyStartRequest):
    payload = {
        "lessonId": request.lesson_id,
        "versionId": request.version_id,
        "materials": [
            {
                "materialId": str(item.id),
                "title": item.title,
                "teachingScript": item.teaching_script,
                "keyPoints": item.key_points,
                "metadata": item.metadata,
            }
            for item in request.materials
        ],
        "modelMode": request.model_mode,
        "requestKey": request.request_key or f"legacy:{request.lesson_id}:{request.version_id}",
        "source": request.source.model_dump() if request.source else None,
    }
    formal = CreateSessionRequest.model_validate(payload)
    try:
        snapshot, replay = service.create_session(formal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "session_id": snapshot["sessionId"],
        "status": "started" if not replay else "existing",
        "lesson_id": snapshot["lessonId"],
        "version_id": snapshot["versionId"],
        "source": snapshot.get("source"),
        "material_count": len(snapshot["materials"]),
        "model_mode": snapshot["modelMode"],
    }


@app.post("/api/classroom/message", status_code=202)
def legacy_message(request: LegacyMessageRequest):
    try:
        snapshot = service.send_message(request.session_id, request.message)
    except KeyError as exc:
        raise _not_found(request.session_id) from exc
    except (ValueError, RuntimeError) as exc:
        raise _bad_request(exc) from exc
    return {
        "status": "queued",
        "session_id": request.session_id,
        "session_status": snapshot["status"],
    }


@app.get("/api/classroom/{session_id}/state")
def legacy_state(session_id: str):
    try:
        snapshot = service.get_session(session_id)
        events = service.get_events(session_id)
    except KeyError as exc:
        raise _not_found(session_id) from exc
    return {
        "session_id": session_id,
        "lesson_id": snapshot["lessonId"],
        "version_id": snapshot["versionId"],
        "source": snapshot.get("source"),
        "status": snapshot["status"],
        "history": [
            {
                "speaker": e.get("speaker"),
                "function": e.get("function"),
                "content": e.get("content", ""),
            }
            for e in events
            if e.get("status") == "COMPLETED"
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
