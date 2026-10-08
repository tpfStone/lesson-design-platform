"""Environment-backed settings for the internal engine service."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "var"


def _path_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


@dataclass(frozen=True)
class EngineSettings:
    state_root: Path
    artifacts_root: Path
    config_path: Path
    internal_token: str = ""
    max_upload_bytes: int = 20 * 1024 * 1024
    max_zip_entries: int = 5000
    max_zip_entry_bytes: int = 20 * 1024 * 1024
    max_zip_expanded_bytes: int = 100 * 1024 * 1024
    max_compression_ratio: float = 250.0
    max_normalizer_characters: int = 120_000

    @classmethod
    def from_environment(cls) -> "EngineSettings":
        # A single repository-level .env is shared by the local launchers and
        # Docker Compose. Keep the older project-local file as a fallback for
        # existing installations; explicit process variables always win.
        load_dotenv(PROJECT_ROOT.parent / ".env")
        load_dotenv(PROJECT_ROOT / ".env")
        base = _path_env(
            "PAPER4_WEB_STATE_ROOT", DEFAULT_RUNTIME_ROOT / "engine-state"
        )
        return cls(
            state_root=base,
            artifacts_root=_path_env(
                "PAPER4_ARTIFACTS_ROOT", DEFAULT_RUNTIME_ROOT / "engine-artifacts"
            ),
            config_path=_path_env(
                "PAPER4_CONFIG_PATH",
                PROJECT_ROOT / "configs" / "deepseek_v4_flash.json",
            ),
            internal_token=os.getenv("ENGINE_INTERNAL_TOKEN", "").strip(),
            max_upload_bytes=int(
                os.getenv("PAPER4_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))
            ),
        )

    def worker_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("internal_token", None)
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in payload.items()
        }

    @classmethod
    def from_worker_payload(cls, payload: dict[str, object]) -> "EngineSettings":
        values = dict(payload)
        for name in ("state_root", "artifacts_root", "config_path"):
            values[name] = Path(str(values[name])).resolve()
        return cls(**values)
