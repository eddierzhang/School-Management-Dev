"""The optional modules: off by default, and closed together when off."""
import pytest

from app.config import Settings


@pytest.fixture
def core_only(settings, monkeypatch):
    monkeypatch.setattr(settings, "modules", "")


def test_modules_are_off_unless_listed(monkeypatch):
    monkeypatch.delenv("HR_MODULES", raising=False)
    assert Settings(_env_file=None).enabled_modules == frozenset()
    monkeypatch.setenv("HR_MODULES", "finance, Stockroom, nonsense")
    assert Settings(_env_file=None).enabled_modules == {"finance", "stockroom"}
    monkeypatch.setenv("HR_MODULES", "all")
    assert Settings(_env_file=None).enabled_modules == {"registrar", "stockroom", "finance", "manager"}


def test_core_only_closes_every_optional_route(client, core_only):
    for path in ("/api/inventory", "/api/finance/summary", "/api/manager/briefing", "/api/courses/demand",
                 "/api/courses/openings?period=3"):
        assert client.get(path).status_code == 404, path
    assert client.post("/api/courses", json={"code": "ART-197", "title": "x", "dept": "Arts", "teacher": "x",
                                             "period": 7, "room": "x", "capacity": 10}).status_code == 404


def test_core_only_keeps_student_support(client, core_only):
    for path in ("/api/students", "/api/summary", "/api/courses", "/api/courses/MAT-150", "/api/schedule",
                 "/api/interventions", "/api/improvement"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/courses/MAT-150").json()["supplies"] == []


def test_core_only_fleet_is_the_support_agents(client, core_only):
    assert {a["name"] for a in client.get("/api/agents").json()["agents"]} == {"support", "classes", "study"}
    me = client.get("/api/auth/me").json()
    assert me["modules"] == []
    assert not {"inventory.read", "finance.read", "courses.write", "manager.run"} & set(me["permissions"])


def test_business_office_has_nothing_without_its_modules(login, core_only):
    me = login("business").get("/api/auth/me").json()
    assert me["permissions"] == ["agents.read", "courses.read"]
