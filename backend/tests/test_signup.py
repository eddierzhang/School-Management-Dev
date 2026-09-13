"""Asking for an account on the sign-in screen, and an administrator deciding."""
import pytest
from sqlalchemy import select

from app.models import AuditEvent, User

PASSWORD = "a-long-enough-password"


@pytest.fixture(autouse=True)
def roomy_limit(settings, monkeypatch):
    """Every test here signs up from the same test client address."""
    monkeypatch.setattr(settings, "signup_max_per_hour", 1000)


def _ask(anon, email, role="counselor", **extra):
    return anon.post("/api/auth/signup", json={"name": "New Person", "email": email, "password": PASSWORD,
                                               "requested_role": role, **extra})


def test_the_sign_in_screen_offers_account_requests(anon):
    cfg = anon.get("/api/auth/config").json()
    assert cfg["signup"] is True
    assert {r["role"] for r in cfg["signup_roles"]} == {"teacher", "counselor", "registrar", "business"}


def test_a_request_creates_a_pending_account_with_no_access(anon, db):
    r = _ask(anon, "pending.person@example.edu", note="New counselor starting Monday.")
    assert r.status_code == 202 and "administrator" in r.json()["message"]
    u = db.scalar(select(User).where(User.email == "pending.person@example.edu"))
    assert (u.pending, u.active, u.requested_role, u.request_note) == (True, False, "counselor",
                                                                      "New counselor starting Monday.")
    signin = anon.post("/api/auth/login", json={"email": "pending.person@example.edu", "password": PASSWORD})
    assert signin.status_code == 403 and "waiting for an administrator" in signin.json()["detail"]
    wrong = anon.post("/api/auth/login", json={"email": "pending.person@example.edu", "password": "not-the-password"})
    assert wrong.status_code == 401, "the pending state is only revealed to someone with the password"
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "auth.signup_requested",
                                              AuditEvent.actor_email == "pending.person@example.edu"))


def test_an_existing_email_gets_the_same_answer_and_nothing_changes(anon, db):
    r = _ask(anon, "counselor@halverson.example.edu", role="teacher")
    assert r.status_code == 202 and r.json()["requested"] is True
    u = db.scalar(select(User).where(User.email == "counselor@halverson.example.edu"))
    assert (u.role, u.active, u.pending) == ("counselor", True, False)


def test_administrator_cannot_be_requested_and_weak_passwords_are_refused(anon):
    assert _ask(anon, "wants.admin@example.edu", role="admin").status_code == 422
    weak = anon.post("/api/auth/signup", json={"name": "X", "email": "weak@example.edu", "password": "short",
                                               "requested_role": "teacher"})
    assert weak.status_code == 422


def test_requests_can_be_limited_to_school_email_domains(anon, settings, monkeypatch):
    monkeypatch.setattr(settings, "signup_email_domains", "school.edu")
    assert _ask(anon, "someone@gmail.com").status_code == 422
    assert _ask(anon, "someone@school.edu").status_code == 202


def test_requests_can_be_turned_off(anon, settings, monkeypatch):
    monkeypatch.setattr(settings, "signup_enabled", False)
    assert anon.get("/api/auth/config").json()["signup"] is False
    assert _ask(anon, "closed@example.edu").status_code == 404


def test_repeated_requests_from_one_address_are_limited(anon, settings, monkeypatch):
    monkeypatch.setattr(settings, "signup_max_per_hour", 0)
    assert _ask(anon, "flood@example.edu").status_code == 429


def test_an_administrator_approves_with_the_role_they_choose(client, anon, db):
    _ask(anon, "to.approve@example.edu", role="counselor")
    uid = db.scalar(select(User.id).where(User.email == "to.approve@example.edu"))
    listed = client.get("/api/admin/users").json()
    assert listed[0]["pending"] is True, "requests are listed first"
    bad = client.post(f"/api/admin/users/{uid}/approve", json={"role": "teacher", "teacher_name": "Nobody"})
    assert bad.status_code == 422
    ok = client.post(f"/api/admin/users/{uid}/approve", json={"role": "teacher", "teacher_name": "R. Okonkwo"})
    assert ok.status_code == 200 and ok.json()["active"] and not ok.json()["pending"]
    assert ok.json()["decided_by"].startswith("admin@")
    signin = anon.post("/api/auth/login", json={"email": "to.approve@example.edu", "password": PASSWORD})
    assert signin.status_code == 200
    assert anon.get("/api/auth/me").json()["role"] == "teacher"
    assert client.post(f"/api/admin/users/{uid}/approve", json={"role": "teacher",
                                                                 "teacher_name": "R. Okonkwo"}).status_code == 409


def test_a_declined_request_can_never_sign_in(client, anon, db):
    _ask(anon, "to.decline@example.edu")
    uid = db.scalar(select(User.id).where(User.email == "to.decline@example.edu"))
    r = client.post(f"/api/admin/users/{uid}/decline")
    assert r.status_code == 200 and not r.json()["active"] and not r.json()["pending"]
    signin = anon.post("/api/auth/login", json={"email": "to.decline@example.edu", "password": PASSWORD})
    assert signin.status_code == 401


def test_a_pending_request_cannot_be_activated_by_editing(client, anon, db):
    _ask(anon, "sneaky@example.edu")
    uid = db.scalar(select(User.id).where(User.email == "sneaky@example.edu"))
    assert client.patch(f"/api/admin/users/{uid}", json={"active": True}).status_code == 409


def test_only_administrators_decide_requests(login, anon, db):
    _ask(anon, "not.yours@example.edu")
    uid = db.scalar(select(User.id).where(User.email == "not.yours@example.edu"))
    assert login("counselor").post(f"/api/admin/users/{uid}/approve", json={"role": "counselor"}).status_code == 403
