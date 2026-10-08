"""Backward-compatible wrapper for the package's offline process exporter.

Prefer:
    python -m paper4_pipeline.cli export-process --run-dir <run_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from paper4_pipeline.observability.report import export_process_report


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: render_process_doc.py <run_dir> [out.md]")
        return 2
    run_dir = Path(argv[1])
    output = Path(argv[2]) if len(argv) > 2 else None
    target = export_process_report(run_dir, output)
    print(f"written: {target.resolve()} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
