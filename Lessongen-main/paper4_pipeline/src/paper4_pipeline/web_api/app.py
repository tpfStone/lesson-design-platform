"""FastAPI application exposing the internal, authenticated engine contract."""

from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from paper4_pipeline import __version__
from paper4_pipeline.providers.openai_compatible import OpenAICompatibleProvider
from paper4_pipeline.web_api.manager import EngineManager
from paper4_pipeline.web_api.projection import EngineProjection
from paper4_pipeline.web_api.schemas import (
    CreateRunRequest,
    EngineArtifact,
    EngineEventPage,
    EngineResult,
    RunAccepted,
    RunSnapshot,
)
from paper4_pipeline.web_api.settings import EngineSettings, PROJECT_ROOT


def _build_fingerprint() -> tuple[str, str]:
    commit = os.getenv("LESSONGEN_BUILD_COMMIT", "").strip()
    dirty = os.getenv("LESSONGEN_BUILD_DIRTY", "").strip()
    if commit and commit != "unknown" and dirty:
        return commit, dirty
    try:
        repo = PROJECT_ROOT.parent
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=normal"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return commit or "unknown", str(bool(status.strip())).lower()
    except (OSError, subprocess.SubprocessError):
        return commit or "unknown", dirty or "unknown"


def create_app(
    settings: EngineSettings | None = None,
    manager: EngineManager | None = None,
) -> FastAPI:
    effective = settings or EngineSettings.from_environment()
    coordinator = manager or EngineManager(effective)
    projection = EngineProjection(effective)
    build_commit, build_dirty = _build_fingerprint()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        coordinator.start()
        yield
        coordinator.shutdown()

    app = FastAPI(
        title="Paper#4 Internal Engine",
        version="0.1.0",
        docs_url="/internal/docs",
        openapi_url="/internal/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = effective
    app.state.manager = coordinator
    app.state.projection = projection

    def authorize(
        x_engine_token: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = effective.internal_token
        if not expected or x_engine_token != expected:
            raise HTTPException(status_code=401, detail="ENGINE_UNAUTHORIZED")

    auth = [Depends(authorize)]

    @app.exception_handler(KeyError)
    async def missing(_: Request, exc: KeyError) -> JSONResponse:
        return _problem(404, "ENGINE_RUN_NOT_FOUND", f"未找到引擎资源：{exc.args[0]}")

    @app.exception_handler(FileNotFoundError)
    async def artifact_file_missing(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return _problem(
            404,
            "ENGINE_ARTIFACT_NOT_FOUND",
            f"引擎产物文件缺失：{Path(exc.filename).name if exc.filename else ''}",
        )

    @app.exception_handler(ValidationError)
    async def invalid_model(_: Request, exc: ValidationError) -> JSONResponse:
        return _problem(422, "ENGINE_INVALID_REQUEST", "内部请求不符合引擎契约")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(422, "ENGINE_INVALID_REQUEST", "内部请求字段缺失或格式错误")

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = str(exc.detail)
        explicit = detail if detail.isupper() and " " not in detail else ""
        code = explicit or {
            401: "ENGINE_UNAUTHORIZED",
            404: "ENGINE_RESOURCE_NOT_FOUND",
            409: "ENGINE_STATE_CONFLICT",
            413: "DOCX_TOO_LARGE",
            415: "INVALID_DOCX",
            422: "ENGINE_INVALID_REQUEST",
        }.get(exc.status_code, "ENGINE_HTTP_ERROR")
        public_detail = {
            "ENGINE_UNAUTHORIZED": "内部服务鉴权失败",
            "ENGINE_IDEMPOTENCY_CONFLICT": "任务标识已被另一份请求占用",
            "ENGINE_RESULT_NOT_READY": "任务尚未形成结构化结果",
            "DOCX_TOO_LARGE": "Word 文件超过大小限制",
            "INVALID_DOCX": "文件不是受支持的 .docx 教案",
        }.get(code, "内部引擎无法处理该请求")
        return _problem(exc.status_code, code, public_detail)

    @app.get("/internal/v1/health")
    def health() -> dict[str, object]:
        OpenAICompatibleProvider.load_environment()
        config_sha256 = (
            hashlib.sha256(effective.config_path.read_bytes()).hexdigest()
            if effective.config_path.is_file()
            else None
        )
        return {
            "status": "up",
            "worker_ready": coordinator._executor is not None,
            "model_configured": bool(os.getenv("DEEPSEEK_API_KEY", "").strip()),
            "config_present": effective.config_path.is_file(),
            "config_sha256": config_sha256,
            "build_commit": build_commit,
            "build_dirty": build_dirty,
            "package_version": __version__,
        }

    @app.post(
        "/internal/v1/runs/generate",
        response_model=RunAccepted,
        status_code=202,
        dependencies=auth,
    )
    def create_generate(request: CreateRunRequest) -> RunAccepted:
        try:
            return coordinator.submit_generate(request)
        except ValueError as exc:
            if str(exc) == "ENGINE_IDEMPOTENCY_CONFLICT":
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/internal/v1/runs/optimize",
        response_model=RunAccepted,
        status_code=202,
        dependencies=auth,
    )
    async def create_optimize(
        request_json: Annotated[str, Form(alias="request")],
        document: Annotated[UploadFile, File()],
    ) -> RunAccepted:
        try:
            request = CreateRunRequest.model_validate_json(request_json)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        filename = Path(document.filename or "lesson.docx").name
        if not filename.lower().endswith(".docx"):
            raise HTTPException(status_code=415, detail="INVALID_DOCX")
        incoming = effective.state_root / "incoming" / f"{uuid.uuid4().hex}.docx"
        incoming.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with incoming.open("xb") as handle:
                while chunk := await document.read(1024 * 1024):
                    size += len(chunk)
                    if size > effective.max_upload_bytes:
                        raise HTTPException(status_code=413, detail="DOCX_TOO_LARGE")
                    handle.write(chunk)
            return coordinator.submit_optimize(
                request, incoming, original_filename=filename
            )
        except Exception:
            incoming.unlink(missing_ok=True)
            raise
        finally:
            await document.close()

    @app.get(
        "/internal/v1/runs/{engine_run_id}",
        response_model=RunSnapshot,
        dependencies=auth,
    )
    def get_run(engine_run_id: str) -> RunSnapshot:
        return projection.snapshot(engine_run_id)

    @app.get(
        "/internal/v1/runs/{engine_run_id}/events",
        response_model=EngineEventPage,
        dependencies=auth,
    )
    def get_events(
        engine_run_id: str,
        after_sequence: int = Query(default=0, alias="afterSequence", ge=0),
    ) -> EngineEventPage:
        return projection.events(engine_run_id, after_sequence=after_sequence)

    @app.get(
        "/internal/v1/runs/{engine_run_id}/result",
        response_model=EngineResult,
        dependencies=auth,
    )
    def get_result(engine_run_id: str) -> EngineResult:
        try:
            return projection.result(engine_run_id)
        except RuntimeError as exc:
            if str(exc) == "ENGINE_RESULT_NOT_READY":
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise

    @app.get(
        "/internal/v1/runs/{engine_run_id}/artifacts",
        response_model=list[EngineArtifact],
        dependencies=auth,
    )
    def list_artifacts(engine_run_id: str) -> list[EngineArtifact]:
        return projection.artifacts(engine_run_id)

    @app.get(
        "/internal/v1/runs/{engine_run_id}/artifacts/{artifact_id}",
        dependencies=auth,
    )
    def download_artifact(engine_run_id: str, artifact_id: str) -> FileResponse:
        try:
            path = projection.artifact_path(engine_run_id, artifact_id)
        except KeyError as exc:
            # A missing run surfaces KeyError(run_id) from the registry lookup;
            # a missing artifact surfaces KeyError(artifact_id). Only the latter
            # is "artifact not found" -- the former must keep its run semantics
            # so Java treats it as a missing run, not as an artifact gap.
            if exc.args and exc.args[0] == artifact_id:
                raise HTTPException(
                    status_code=404, detail="ENGINE_ARTIFACT_NOT_FOUND"
                ) from exc
            raise
        metadata = next(
            (
                item
                for item in projection.artifacts(engine_run_id)
                if item.artifact_id == artifact_id
            ),
            None,
        )
        if metadata is None:
            raise HTTPException(status_code=404, detail="ENGINE_ARTIFACT_NOT_FOUND")
        return FileResponse(
            path,
            media_type=metadata.media_type,
            filename=metadata.display_name,
            headers={"Digest": f"sha-256={metadata.sha256}"},
        )

    return app


def _problem(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "type": f"urn:paper4:error:{code.lower()}",
            "title": "Paper#4 Engine Error",
            "status": status,
            "code": code,
            "detail": detail,
        },
        media_type="application/problem+json",
    )


app = create_app()
