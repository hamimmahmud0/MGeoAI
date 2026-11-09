"""The web application: the open dashboard API (`/api/x/*`) and the built frontend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from traffic_fusion import __version__
from traffic_fusion.api.extraction import build_router


def create_app(extraction_dir: Path | None = None) -> FastAPI:
    root = extraction_dir or Path(os.getenv("MGEOAI_EXTRACTION_DIR", "extraction"))
    app = FastAPI(title="MGeoAI road-accident news workspace", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # the Vite dev server
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        allow_credentials=True,
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "articles": len(list((root / "articles").glob("*/meta.json")))}

    app.include_router(
        build_router(root, secure_cookies=os.getenv("MGEOAI_SECURE_COOKIES", "").lower() in {"1", "true", "yes"})
    )

    frontend = Path("web/dist")
    if frontend.exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = frontend / path
            return FileResponse(candidate if candidate.is_file() else frontend / "index.html")

    return app
