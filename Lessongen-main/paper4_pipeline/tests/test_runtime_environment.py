"""Local launch checks that do not contact a model or start a server."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from paper4_pipeline.web_api import settings as settings_module
from paper4_pipeline.web_api.__main__ import main


def test_repository_env_precedes_legacy_project_env() -> None:
    with TemporaryDirectory() as folder:
        root = Path(folder)
        project = root / "paper4_pipeline"
        project.mkdir()
        (root / ".env").write_text(
            "DEEPSEEK_API_KEY=root-test-key\nENGINE_INTERNAL_TOKEN=root-test-token\n",
            encoding="utf-8",
        )
        (project / ".env").write_text(
            "DEEPSEEK_API_KEY=legacy-test-key\nENGINE_INTERNAL_TOKEN=legacy-test-token\n",
            encoding="utf-8",
        )
        with (
            patch.object(settings_module, "PROJECT_ROOT", project),
            patch.object(settings_module, "DEFAULT_RUNTIME_ROOT", project / "var"),
            patch.dict(os.environ, {}, clear=True),
        ):
            actual = settings_module.EngineSettings.from_environment()
            assert actual.internal_token == "root-test-token"
            assert os.environ["DEEPSEEK_API_KEY"] == "root-test-key"


def test_explicit_environment_precedes_dotenv() -> None:
    with TemporaryDirectory() as folder:
        root = Path(folder)
        project = root / "paper4_pipeline"
        project.mkdir()
        (root / ".env").write_text(
            "ENGINE_INTERNAL_TOKEN=file-test-token\n", encoding="utf-8"
        )
        with (
            patch.object(settings_module, "PROJECT_ROOT", project),
            patch.dict(os.environ, {"ENGINE_INTERNAL_TOKEN": "process-test-token"}, clear=True),
        ):
            actual = settings_module.EngineSettings.from_environment()
            assert actual.internal_token == "process-test-token"


def test_engine_bind_can_be_set_for_container_only() -> None:
    with (
        patch.dict(
            os.environ,
            {"PAPER4_BIND_HOST": "0.0.0.0", "PAPER4_BIND_PORT": "8010"},
        ),
        patch("uvicorn.run") as run,
    ):
        main()
        run.assert_called_once_with(
            "paper4_pipeline.web_api.app:app",
            host="0.0.0.0",
            port=8010,
            reload=False,
        )
