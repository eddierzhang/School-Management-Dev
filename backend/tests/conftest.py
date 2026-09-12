"""Tests run against their own freshly seeded database, never the dev one.

The env var is set before any app module is imported, because `app.db` builds its
engine at import time from the cached settings.
"""
import os
import pathlib
import sys
import tempfile

TMP_DB = pathlib.Path(tempfile.mkdtemp(prefix="hr-test-")) / "test.db"
os.environ["HR_DATABASE_URL"] = f"sqlite:///{TMP_DB}"

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import seed  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded():
    seed.build()
    yield


@pytest.fixture(scope="session")
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def settings():
    return get_settings()
