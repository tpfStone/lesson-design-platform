"""Freeze Python's internal wire contract for Java drift checks.

Run from any directory with the project's Python environment:
    python scripts/export_engine_contract.py
    python scripts/export_engine_contract.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from paper4_pipeline.web_api.schemas import (
    CreateRunRequest, EngineArtifact, EngineEventPage, EngineResult,
    RunAccepted, RunSnapshot,
)


TARGET = Path(__file__).resolve().parents[2] / "specs/002-project-improvement/contracts/engine-models.json"
MODELS = (CreateRunRequest, RunAccepted, RunSnapshot, EngineEventPage, EngineArtifact, EngineResult)


def render() -> str:
    payload = {
        "contract_version": "p1-engine-v1",
        "models": {
            model.__name__: model.model_json_schema(mode="serialization")
            for model in MODELS
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != expected:
            raise SystemExit("Engine contract drift: regenerate engine-models.json and update Java adapter/tests")
        print("Engine contract matches Python models")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
