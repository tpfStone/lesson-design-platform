"""Read-only audit for a preserved Lessongen runtime directory.

The command validates representative historical JSON, Markdown, DOCX, manifest
hashes, engine state and uploaded source files without printing lesson content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any


def _json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _docx(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"corrupt DOCX member: {bad_member}")
        members = set(archive.namelist())
        required = {"[Content_Types].xml", "word/document.xml"}
        if not required.issubset(members):
            raise ValueError("DOCX package has no Word document body")


def _artifact_path(run_dir: Path, item: dict[str, Any]) -> Path:
    declared = Path(str(item.get("path", "")))
    if declared.is_file():
        return declared
    return run_dir / declared.name


def _validate_engine_delivery(manifest_path: Path) -> None:
    run_dir = manifest_path.parent
    manifest = _json(manifest_path)
    _json(run_dir / "run_result.json")
    _json(run_dir / "best_lesson_plan.json")
    (run_dir / "best_lesson_plan.md").read_text(encoding="utf-8")
    _docx(run_dir / "best_lesson_plan.docx")
    for item in manifest.get("artifacts", []):
        if item.get("status") != "ok" or not item.get("sha256"):
            continue
        artifact = _artifact_path(run_dir, item)
        if not artifact.is_file():
            raise FileNotFoundError(f"manifest artifact missing: {artifact.name}")
        if _sha256(artifact) != item["sha256"]:
            raise ValueError(f"manifest hash mismatch: {artifact.name}")


def _audit_engine_artifact(root: Path) -> tuple[str, int]:
    artifact_root = root / "engine-artifacts"
    manifests = sorted(artifact_root.glob("*/manifest.json"), reverse=True)
    invalid = 0
    for manifest_path in manifests:
        run_dir = manifest_path.parent
        required = {
            "best_lesson_plan.json",
            "best_lesson_plan.md",
            "best_lesson_plan.docx",
            "run_result.json",
        }
        if not all((run_dir / name).is_file() for name in required):
            continue
        try:
            _validate_engine_delivery(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile):
            invalid += 1
            continue
        return run_dir.name[-6:], invalid
    raise FileNotFoundError("no complete historical engine delivery was found")


def _audit_engine_state(root: Path) -> str:
    state_files = sorted((root / "engine-state" / "runs").glob("*/web_run.json"), reverse=True)
    if not state_files:
        raise FileNotFoundError("no historical engine state was found")
    record = _json(state_files[0])
    if not record.get("engine_run_id") or not record.get("status"):
        raise ValueError("historical engine state is missing identity or status")
    return state_files[0].parent.name[-6:]


def _audit_web_storage(root: Path) -> tuple[str, str]:
    jobs_root = root / "web-storage" / "jobs"
    source_files = sorted(jobs_root.glob("*/input/original.docx"), reverse=True)
    result_files = sorted(jobs_root.glob("*/result/engine_result.json"), reverse=True)
    if not source_files:
        raise FileNotFoundError("no historical uploaded Word source was found")
    if not result_files:
        raise FileNotFoundError("no historical web result was found")
    _docx(source_files[0])
    _json(result_files[0])
    return source_files[0].parents[1].name[-6:], result_files[0].parents[1].name[-6:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_root", type=Path)
    args = parser.parse_args()
    root = args.runtime_root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"runtime directory does not exist: {root}")
    try:
        artifact_id, invalid_deliveries = _audit_engine_artifact(root)
        state_id = _audit_engine_state(root)
        source_id, result_id = _audit_web_storage(root)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"RUNTIME AUDIT FAILED: {exc}", file=sys.stderr)
        return 1
    print("RUNTIME AUDIT PASSED")
    print(f"engine delivery: ...{artifact_id} (JSON/Markdown/DOCX + manifest hashes)")
    print(f"engine state:    ...{state_id} (JSON)")
    print(f"uploaded source: ...{source_id} (DOCX)")
    print(f"web result:      ...{result_id} (JSON)")
    if invalid_deliveries:
        print(
            f"warning: skipped {invalid_deliveries} newer delivery with stale or invalid integrity data"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
