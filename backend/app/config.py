"""Deployment configuration.

Two layers of configuration exist in FORGE:

* **Deployment config** (this module) - where data lives, upload limits, network
  binding. Read from environment variables prefixed with ``FORGE_`` and fixed for
  the lifetime of the process.
* **User preferences** - stored in the ``app_setting`` table and editable from the
  Settings screen at runtime (see :mod:`app.services.settings_store`).

Keeping them apart means a user can never brick their install from the UI.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Process-level settings. Override with ``FORGE_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="FORGE_", env_file=None, extra="ignore")

    #: Root directory for the database, stored originals and backups.
    data_dir: Path = Field(default=PROJECT_ROOT / "data")

    #: Maximum accepted upload size, in mebibytes.
    max_upload_mb: int = 128

    #: Maximum number of files accepted in a single batch import request.
    max_batch_files: int = 50

    #: Origins allowed to call the API (the Vite dev server by default).
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ]
    )

    #: Serve the built frontend from the API process when ``frontend/dist`` exists.
    serve_frontend: bool = True

    #: Run Alembic migrations automatically on startup.
    auto_migrate: bool = True

    #: Base URL of an optional local Ollama instance. 127.0.0.1 rather than
    #: "localhost": on Windows the latter resolves to ::1 first, and when
    #: nothing is listening the IPv6 attempt has to time out before the IPv4
    #: one is tried - four seconds of dead wait for a "not installed" answer.
    ollama_base_url: str = "http://127.0.0.1:11434"

    #: Network timeout (seconds) for optional local LLM calls.
    llm_timeout_seconds: float = 120.0

    #: Echo SQL to stdout (debugging aid).
    sql_echo: bool = False

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(os.path.expandvars(value)).expanduser()
        return value

    @property
    def db_path(self) -> Path:
        return self.data_dir / "forge.db"

    @property
    def database_url(self) -> str:
        # ``as_posix`` keeps the URL valid on Windows (C:/Users/... instead of C:\Users\...).
        return f"sqlite+pysqlite:///{self.db_path.as_posix()}"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def frontend_dist(self) -> Path:
        return PROJECT_ROOT / "frontend" / "dist"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.files_dir, self.backups_dir, self.tmp_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def reset_settings_cache() -> None:
    """Used by the test-suite when it points FORGE at a temporary data directory."""

    get_settings.cache_clear()
