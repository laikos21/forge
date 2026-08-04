"""Test fixtures.

Every test runs against its own temporary data directory: a fresh SQLite file,
a fresh blob store and a fresh backup folder. Nothing in the suite touches the
developer's real ``data/`` directory.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"

# The data directory must be set before app.config is imported anywhere.
_BOOTSTRAP_DIR = Path(tempfile.mkdtemp(prefix="forge-tests-bootstrap-"))
os.environ.setdefault("FORGE_DATA_DIR", str(_BOOTSTRAP_DIR))

from app.config import get_settings, reset_settings_cache  # noqa: E402
from app.db import reset_engine, session_scope  # noqa: E402
from app.migrations import upgrade_to_head  # noqa: E402


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    shutil.rmtree(_BOOTSTRAP_DIR, ignore_errors=True)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point FORGE at a throwaway data directory and migrate it."""

    target = tmp_path / "forge-data"
    monkeypatch.setenv("FORGE_DATA_DIR", str(target))
    reset_settings_cache()
    reset_engine()
    get_settings().ensure_dirs()
    upgrade_to_head()
    yield target
    reset_engine()
    reset_settings_cache()


@pytest.fixture
def session(data_dir: Path) -> Iterator:
    with session_scope() as db_session:
        yield db_session


@pytest.fixture
def client(data_dir: Path) -> Iterator:
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def seeded(client) -> Iterator:  # noqa: ANN001
    response = client.post("/api/maintenance/seed", json={"reset": True})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "created"
    yield client


@pytest.fixture(scope="session")
def samples() -> Path:
    if not SAMPLES_DIR.is_dir():
        pytest.skip("samples/ not generated; run python scripts/make_samples.py")
    return SAMPLES_DIR


@pytest.fixture
def sample_bytes(samples: Path):  # noqa: ANN201
    def _read(name: str) -> bytes:
        path = samples / name
        if not path.is_file():
            pytest.skip(f"sample file missing: {name}")
        return path.read_bytes()

    return _read
