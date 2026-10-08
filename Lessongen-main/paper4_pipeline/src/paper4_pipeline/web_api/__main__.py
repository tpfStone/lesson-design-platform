"""Console entry point for the internal engine service."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "paper4_pipeline.web_api.app:app",
        host=os.getenv("PAPER4_BIND_HOST", "127.0.0.1"),
        port=int(os.getenv("PAPER4_BIND_PORT", "8001")),
        reload=False,
    )


if __name__ == "__main__":
    main()
