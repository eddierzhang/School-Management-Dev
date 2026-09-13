"""Sign-in, roles, teacher scoping and the audit log.

Every role is exercised through the real routes with a real session cookie, so a
route that forgets its permission check fails here rather than in a school.
"""
import base64
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

import seed
from app.models import AuditEvent, Course, Enrollment, Proposal, Student, User

DOMAIN = seed.DEMO_DOMAIN


def _teacher_and_outsider(db):
    """A teacher, one of their sections, and a student they do not teach."""
    teacher = "R. Okonkwo"
    mine = db.scalars(select(Course).where(Course.teacher == teacher)).all()
    taught = {sid for (sid,) in db.execute(
        select(Student.sid).join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id.in_([c.id for c in mine]))).all()}
    outsider = db.scalar(select(Student.sid).where(Student.sid.not_in(taught)).limit(1))
    other_course = db.scalar(select(Course.code).where(Course.teacher != teacher).limit(1))
    return mine[0].code, taught, outsider, other_course


# ---- signing in -----------------------------------------------------------------
def test_everything_but_health_and_sign_in_needs_a_session(anon):
    for path in ("/api/students", "/api/summary", "/api/courses", "/api/inventory", "/api/finance/summary",
                 "/api/agents", "/api/admin/users", "/api/auth/me"):
        assert anon.get(path).status_code == 401, path
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/auth/config").json()["password_login"] is True


def test_wrong_password_is_refused_and_logged(anon, db):
    r = anon.post("/api/auth/login", json={"email": f"counselor@{DOMAIN}", "password": "not-the-password"})
    assert r.status_code == 401
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "auth.login_failed",
                                              AuditEvent.actor_email == f"counselor@{DOMAIN}"))


def test_repeated_failures_lock_the_account_for_a_while(anon, settings):
    email = f"h.ashford@{DOMAIN}"         # an account no other test signs in with
    for _ in range(settings.login_max_failures):
        anon.post("/api/auth/login", json={"email": email, "password": "wrong-wrong-wrong"})
    r = anon.post("/api/auth/login", json={"email": email, "password": seed.DEMO_PASSWORD})
    assert r.status_code == 429


def test_changes_need_the_csrf_header(login):
    c = login("counselor")
    r = c.post("/api/interventions", headers={"X-Requested-With": ""},
               json={"student_sid": "S-1507", "kind": "check-in", "title": "x"})
    assert r.status_code == 403 and "X-Requested-With" in r.json()["detail"]


def test_session_cookie_is_httponly_and_sign_out_ends_it(anon):
    r = anon.post("/api/auth/login", json={"email": f"business@{DOMAIN}", "password": seed.DEMO_PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert anon.get("/api/auth/me").json()["role"] == "business"
    assert anon.post("/api/auth/logout").status_code == 200
    assert anon.get("/api/auth/me").status_code == 401


def test_me_lists_the_roles_permissions(login):
    me = login("counselor").get("/api/auth/me").json()
    assert me["role"] == "counselor" and "plans.write" in me["permissions"] and "finance.read" not in me["permissions"]


# ---- roles ------------------------------------------------------------------------
def test_business_office_sees_money_and_stock_but_no_students(login):
    c = login("business")
    assert c.get("/api/inventory").status_code == 200
    assert c.get("/api/finance/summary").status_code == 200
    for path in ("/api/students", "/api/students/S-1507", "/api/watchlist", "/api/interventions"):
        assert c.get(path).status_code == 403, path
    agents = {a["name"] for a in c.get("/api/agents").json()["agents"]}
    assert agents == {"stockroom", "finance"}


def test_counselor_manages_plans_but_not_classes_or_money(login):
    c = login("counselor")
    assert c.get("/api/students").status_code == 200
    assert c.get("/api/finance/summary").status_code == 403
    assert c.get("/api/inventory").status_code == 403
    assert c.post("/api/courses", json={"code": "ART-199", "title": "x", "dept": "Arts", "teacher": "x",
                                        "period": 7, "room": "x", "capacity": 10}).status_code == 403
    assert c.get("/api/admin/users").status_code == 403


def test_registrar_cannot_open_support_plans(login):
    r = login("registrar").post("/api/interventions", json={"student_sid": "S-1507", "kind": "check-in", "title": "x"})
    assert r.status_code == 403


def test_proposals_are_decided_only_by_the_matching_role(login, db):
    budget = Proposal(agent="finance", kind="transaction_review", summary="Hold a charge", payload={"transaction_id": 1},
                      evidence=[], status="pending")
    db.add(budget)
    db.commit()
    counselor, business = login("counselor"), login("business")
    # The counselor cannot even see the finance agent's proposals.
    assert all(p["agent"] != "finance" for p in counselor.get("/api/agents/proposals").json())
    assert counselor.post(f"/api/agents/proposals/{budget.id}/reject", json={"note": "no"}).status_code == 404
    r = business.post(f"/api/agents/proposals/{budget.id}/reject", json={"note": "Checked; the charge is fine."})
    assert r.status_code == 200
    db.refresh(budget)
    assert budget.decided_by == f"business@{DOMAIN}"


def test_manager_and_admin_screens_are_for_administrators(login, client):
    assert login("counselor").get("/api/manager/briefing").status_code == 403
    assert client.get("/api/admin/users").status_code == 200


# ---- teachers see their own students ------------------------------------------------
def test_teacher_sees_only_students_in_their_sections(login, db):
    code, taught, outsider, other_course = _teacher_and_outsider(db)
    c = login("r.okonkwo")
    listed = {r["sid"] for r in c.get("/api/students").json()}
    assert listed and listed <= taught
    assert c.get(f"/api/students/{outsider}").status_code == 404
    assert c.get(f"/api/students/{outsider}/documents").status_code == 404
    assert c.get(f"/api/students/{outsider}/study").status_code == 404
    assert c.get(f"/api/courses/{other_course}").status_code == 404
    assert c.get(f"/api/courses/{code}").status_code == 200
    assert all(s["sid"] in taught for s in c.get("/api/watchlist?limit=200").json())
    assert all(cl["sid"] in taught for cl in c.get("/api/schedule").json()["student_clashes"])


def test_teacher_records_scores_only_in_their_own_sections(login, db):
    code, taught, _, other_course = _teacher_and_outsider(db)
    c = login("r.okonkwo")
    mine = c.get(f"/api/courses/{code}/assessments").json()[0]
    enrolled = db.scalar(select(Student.sid).join(Enrollment, Enrollment.student_id == Student.id)
                         .join(Course, Course.id == Enrollment.course_id)
                         .where(Course.code == code, Enrollment.status == "enrolled").limit(1))
    assert c.put("/api/scores", json={"assessment_id": mine["id"], "student_sid": enrolled,
                                      "points": 1, "late": False}).status_code == 200
    theirs = c.get(f"/api/courses/{other_course}/assessments").json()[0]
    assert c.put("/api/scores", json={"assessment_id": theirs["id"], "student_sid": enrolled,
                                      "points": 1, "late": False}).status_code == 404


def test_teacher_cannot_approve_or_see_the_fleet(login):
    c = login("r.okonkwo")
    assert c.get("/api/agents").status_code == 403
    assert c.post("/api/interventions", json={"student_sid": "S-1507", "kind": "check-in", "title": "x"}).status_code == 403


# ---- the audit log ---------------------------------------------------------------------
def test_changes_and_student_views_are_audited_with_the_actor(login, client, db):
    c = login("counselor")
    before = db.scalar(select(AuditEvent.id).order_by(AuditEvent.id.desc()).limit(1)) or 0
    c.get("/api/students/S-1507")
    c.post("/api/interventions", json={"student_sid": "S-1507", "kind": "family-contact", "title": "Call home"})
    c.post("/api/courses", json={"code": "ART-198", "title": "x", "dept": "Arts", "teacher": "x",
                                 "period": 7, "room": "x", "capacity": 10})
    events = client.get("/api/admin/audit", params={"actor": f"counselor@{DOMAIN}"}).json()["events"]
    new = [e for e in events if e["id"] > before]
    actions = {(e["action"], e["status"]) for e in new}
    assert ("student.view", 200) in actions
    assert ("POST /api/interventions", 201) in actions
    assert ("POST /api/courses", 403) in actions        # refused attempts are recorded too
    view = next(e for e in new if e["action"] == "student.view")
    assert view["entity_type"] == "student" and view["entity_id"] == "S-1507" and view["actor_role"] == "counselor"
    assert login("counselor").get("/api/admin/audit").status_code == 403


def test_every_response_carries_a_request_id_and_no_store(client):
    r = client.get("/api/students/S-1507")
    assert r.headers["x-request-id"] and r.headers["cache-control"] == "no-store"


# ---- accounts -----------------------------------------------------------------------------
def test_admin_creates_a_teacher_linked_to_the_timetable(client):
    bad = client.post("/api/admin/users", json={"email": "new.teacher@example.edu", "name": "New", "role": "teacher",
                                                "teacher_name": "Nobody Here"})
    assert bad.status_code == 422
    ok = client.post("/api/admin/users", json={"email": "new.teacher@example.edu", "name": "New", "role": "teacher",
                                               "teacher_name": "R. Okonkwo", "password": "a-long-enough-password"})
    assert ok.status_code == 201 and ok.json()["has_password"]
    assert client.post("/api/admin/users", json={"email": "NEW.teacher@example.edu", "name": "Again",
                                                 "role": "counselor"}).status_code == 409


def test_changing_a_role_ends_that_persons_sessions(client, anon, db):
    anon.post("/api/auth/login", json={"email": f"j.whitfield@{DOMAIN}", "password": seed.DEMO_PASSWORD})
    assert anon.get("/api/auth/me").status_code == 200
    uid = db.scalar(select(User.id).where(User.email == f"j.whitfield@{DOMAIN}"))
    assert client.patch(f"/api/admin/users/{uid}", json={"active": False}).status_code == 200
    assert anon.get("/api/auth/me").status_code == 401
    client.patch(f"/api/admin/users/{uid}", json={"active": True})


def test_the_last_administrator_cannot_be_removed(client, db):
    me = client.get("/api/auth/me").json()
    r = client.patch(f"/api/admin/users/{me['id']}", json={"role": "counselor"})
    assert r.status_code == 409


# ---- production settings -------------------------------------------------------------------
def test_production_refuses_unsafe_settings(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("HR_TODAY", raising=False)
    monkeypatch.setenv("HR_APP_ENV", "production")
    monkeypatch.setenv("HR_DATABASE_URL", "sqlite:///x.db")
    problems = " ".join(Settings(_env_file=None).production_problems())
    assert "HR_SECRET_KEY" in problems and "SQLite" in problems
    monkeypatch.setenv("HR_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("HR_DATABASE_URL", "postgresql+psycopg://u:p@db/x")
    assert Settings(_env_file=None).production_problems() == []


# ---- sign-in through the school's identity provider -----------------------------------------
@pytest.fixture
def provider(monkeypatch):
    """A fake OpenID provider: discovery, a token endpoint and published keys."""
    from app.auth import oidc

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk |= {"kid": "k1", "alg": "RS256", "use": "sig"}
    issuer = "https://idp.example.edu"
    state = {"email": f"counselor@{DOMAIN}", "nonce": None, "aud": "halverson"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": issuer, "authorization_endpoint": f"{issuer}/authorize",
                                             "token_endpoint": f"{issuer}/token", "jwks_uri": f"{issuer}/jwks"})
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path == "/token":
            now = int(time.time())
            claims = {"iss": issuer, "aud": state["aud"], "sub": "123", "iat": now, "exp": now + 300,
                      "email": state["email"], "email_verified": True, "nonce": state["nonce"]}
            return httpx.Response(200, json={"id_token": jwt.encode(claims, key, algorithm="RS256",
                                                                   headers={"kid": "k1"})})
        return httpx.Response(404)

    s = oidc.settings
    for k, v in {"oidc_issuer": issuer, "oidc_client_id": "halverson", "oidc_client_secret": "shh",
                 "oidc_redirect_uri": "http://testserver/api/auth/oidc/callback"}.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(oidc, "_discovery", None)
    monkeypatch.setattr(oidc, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return state


def _start(anon, provider):
    r = anon.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    params = dict(httpx.URL(r.headers["location"]).params)
    payload = json.loads(base64.urlsafe_b64decode(anon.cookies.get("hr_oidc").rsplit(".", 1)[0]))
    provider["nonce"] = payload["nonce"]
    assert params["code_challenge_method"] == "S256"
    return params["state"]


def test_oidc_signs_in_an_existing_account(anon, provider):
    state = _start(anon, provider)
    r = anon.get(f"/api/auth/oidc/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    assert anon.get("/api/auth/me").json()["email"] == f"counselor@{DOMAIN}"


def test_oidc_never_creates_accounts(anon, provider):
    provider["email"] = "stranger@example.edu"
    state = _start(anon, provider)
    r = anon.get(f"/api/auth/oidc/callback?code=abc&state={state}", follow_redirects=False)
    assert "not-registered" in r.headers["location"]
    assert anon.get("/api/auth/me").status_code == 401


def test_oidc_rejects_a_forged_state_or_wrong_audience(anon, provider):
    _start(anon, provider)
    r = anon.get("/api/auth/oidc/callback?code=abc&state=forged", follow_redirects=False)
    assert "sign-in-failed" in r.headers["location"]
    provider["aud"] = "someone-else"
    state = _start(anon, provider)
    r = anon.get(f"/api/auth/oidc/callback?code=abc&state={state}", follow_redirects=False)
    assert "sign-in-failed" in r.headers["location"]
