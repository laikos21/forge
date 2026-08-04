"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import api_router
from .config import get_settings
from .migrations import upgrade_to_head

logger = logging.getLogger("forge")

DESCRIPTION = """
FORGE is a local-first personal research intelligence system.

Everything runs on this machine: SQLite for storage and full-text search, the
local filesystem for original files, and an optional local model provider for
the accessory features. No API key, account or internet connection is required.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_dirs()
    if settings.auto_migrate:
        revision = upgrade_to_head()
        logger.info("database migrated to %s", revision)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FORGE",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Return a message the UI can show verbatim instead of a raw error list."""

        problems = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", []) if part not in ("body", "query"))
            problems.append(f"{location or 'request'}: {error.get('msg', 'invalid value')}")
        return JSONResponse(
            status_code=422,
            content={"detail": "; ".join(problems) or "Invalid request.", "problems": problems},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("value error on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    app.include_router(api_router)

    dist = settings.frontend_dist
    if settings.serve_frontend and dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            candidate = dist / full_path
            if full_path and candidate.is_file() and dist.resolve() in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> dict:
            return {
                "name": "FORGE",
                "version": __version__,
                "api_docs": "/api/docs",
                "frontend": (
                    "Not built. Run 'npm run dev' in frontend/ for development, "
                    "or .\\build.ps1 to produce frontend/dist."
                ),
            }

    return app


app = create_app()


def frontend_available() -> bool:
    return Path(get_settings().frontend_dist / "index.html").is_file()
