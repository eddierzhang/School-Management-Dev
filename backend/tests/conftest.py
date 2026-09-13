"""Tests run against their own freshly seeded database, never the dev one.

SQLite by default. Set HR_TEST_DATABASE_URL to run the same suite against
Postgres (CI does both); that database is dropped and rebuilt from the migrations.

The env vars are set before any app module is imported, because `app.db` builds
its engine at import time from the cached settings.
"""
import os
import pathlib
import sys
import tempfile

TMP_DB = pathlib.Path(tempfile.mkdtemp(prefix="hr-test-")) / "test.db"
os.environ["HR_DATABASE_URL"] = os.environ.get("HR_TEST_DATABASE_URL") or f"sqlite:///{TMP_DB}"
os.environ["HR_TODAY"] = "2026-09-12"
os.environ["HR_APP_ENV"] = "test"
# Every module on, so the whole codebase is under test; test_modules.py turns them off.
os.environ["HR_MODULES"] = "all"

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


CSRF = {"X-Requested-With": "tests"}


def signed_in_client(email: str) -> TestClient:
    """A client with its own cookie jar, signed in as a demo account."""
    c = TestClient(app, headers=CSRF)
    c.__enter__()
    r = c.post("/api/auth/login", json={"email": email, "password": seed.DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def client(seeded):
    """Signed in as the demo administrator, who may do everything."""
    c = signed_in_client(f"admin@{seed.DEMO_DOMAIN}")
    yield c
    c.__exit__(None, None, None)


@pytest.fixture(scope="session")
def login(seeded):
    """login("counselor") or login("r.okonkwo"): a client signed in as that demo account."""
    made: list[TestClient] = []

    def _login(local: str) -> TestClient:
        c = signed_in_client(f"{local}@{seed.DEMO_DOMAIN}")
        made.append(c)
        return c
    yield _login
    for c in made:
        c.__exit__(None, None, None)


@pytest.fixture
def anon(seeded):
    with TestClient(app, headers=CSRF) as c:
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
