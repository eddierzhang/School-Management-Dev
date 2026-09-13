"""The platform under the features: migrations, startup, health and readiness."""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import Base, engine, schema_status


def test_migrations_match_the_models():
    """A model change without a migration would pass every other test on a
    freshly built database and then break the first real deploy."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models and migrations disagree; run `alembic revision --autogenerate`: {diff}"


def test_database_is_at_the_newest_migration():
    s = schema_status()
    assert s["head"] and s["up_to_date"], s


def test_health_answers_without_touching_anything(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_checks_database_and_schema_but_not_the_model(client):
    r = client.get("/api/ready")
    body = r.json()
    assert r.status_code == 200, body
    assert body["checks"]["database"]["ok"] and body["checks"]["schema"]["ok"]
    assert body["checks"]["model"]["required"] is False


def test_ready_fails_when_the_schema_is_behind(client, monkeypatch):
    import app.routers.meta as meta

    monkeypatch.setattr(meta, "schema_status", lambda: {"current": None, "head": "0001", "up_to_date": False})
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.json()["checks"]["schema"]["ok"] is False


def test_clock_is_real_unless_pinned(monkeypatch):
    from datetime import date

    from app.config import Settings

    monkeypatch.delenv("HR_TODAY", raising=False)
    assert Settings(_env_file=None).today == date.today()
    monkeypatch.setenv("HR_TODAY", "2030-01-02")
    assert Settings(_env_file=None).today == date(2030, 1, 2)
