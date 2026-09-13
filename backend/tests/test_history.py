"""Student history, staff overrides of a flag, and reasons on every rejection."""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.ai.executor import reject_proposal
from app.history import take_snapshots
from app.models import Intervention, Proposal, Student, StudentSnapshot

TODAY = date(2026, 9, 12)


def _unplanned_needs_plan(client, db) -> str:
    planned = {sid for (sid,) in db.execute(select(Student.sid).join(Intervention, Intervention.student_id == Student.id)
                                            .where(Intervention.status == "active")).all()}
    return next(r["sid"] for r in client.get("/api/students", params={"band": "needs-plan"}).json()
                if r["sid"] not in planned)


@pytest.fixture
def revoke_after(client):
    made: list[tuple[str, int]] = []
    yield made
    for sid, oid in made:
        client.delete(f"/api/students/{sid}/overrides/{oid}")


# ---- history ---------------------------------------------------------------------
def test_the_seed_leaves_a_weekly_history_ending_today(client):
    h = client.get("/api/students/S-1507/history").json()
    days = [s["on"] for s in h["snapshots"]]
    assert len(days) >= 4 and days == sorted(days) and days[-1] == TODAY.isoformat()


def test_past_readings_come_from_the_gradebook_as_it_stood(db):
    first, last = (db.scalar(select(func.min(StudentSnapshot.taken_on))),
                   db.scalar(select(func.max(StudentSnapshot.taken_on))))
    rows = {(s.student_id, s.taken_on): s for s in db.scalars(select(StudentSnapshot)).all()}
    changed = sum(1 for (sid, day), s in rows.items()
                  if day == last and (sid, first) in rows and rows[(sid, first)].struggle_index != s.struggle_index)
    assert changed > 0, "every student read the same in week three as today"


def test_retaking_a_day_replaces_it(db):
    before = db.scalar(select(func.count()).select_from(StudentSnapshot))
    take_snapshots(db, TODAY)
    assert db.scalar(select(func.count()).select_from(StudentSnapshot)) == before


def test_history_marks_plans_on_the_timeline(client, db):
    sid = db.scalar(select(Student.sid).join(Intervention, Intervention.student_id == Student.id).limit(1))
    events = client.get(f"/api/students/{sid}/history").json()["events"]
    assert any(e["kind"] == "plan-opened" for e in events)


def test_teachers_only_see_history_for_their_own_students(login, db):
    from tests.test_auth import _teacher_and_outsider

    _, taught, outsider, _ = _teacher_and_outsider(db)
    c = login("r.okonkwo")
    assert c.get(f"/api/students/{outsider}/history").status_code == 404
    assert c.get(f"/api/students/{sorted(taught)[0]}/history").status_code == 200


# ---- overrides -------------------------------------------------------------------
def test_acknowledging_takes_a_student_off_the_to_do_list_but_not_the_index(client, db, revoke_after):
    sid = _unplanned_needs_plan(client, db)
    before = client.get("/api/summary").json()["unaddressed"]
    r = client.post(f"/api/students/{sid}/overrides", json={
        "kind": "acknowledge", "note": "Family meeting held; tutoring starts Monday.",
        "expires_on": (TODAY + timedelta(days=14)).isoformat()})
    assert r.status_code == 201, r.text
    revoke_after.append((sid, r.json()["id"]))

    assert client.get("/api/summary").json()["unaddressed"] == before - 1
    assert sid not in {s["sid"] for s in client.get("/api/watchlist?limit=200").json()}
    assert sid in {s["sid"] for s in client.get("/api/watchlist?limit=200&include_acknowledged=true").json()}
    detail = client.get(f"/api/students/{sid}").json()
    assert detail["band"] == detail["computed_band"] == "needs-plan" and detail["acknowledged"]
    assert detail["override"]["note"].startswith("Family meeting")
    assert any(e["kind"] == "override" for e in client.get(f"/api/students/{sid}/history").json()["events"])

    client.delete(f"/api/students/{sid}/overrides/{r.json()['id']}")
    assert client.get("/api/summary").json()["unaddressed"] == before


def test_setting_the_band_changes_it_everywhere_and_keeps_the_computed_one(client, db, revoke_after):
    sid = _unplanned_needs_plan(client, db)
    r = client.post(f"/api/students/{sid}/overrides", json={
        "kind": "set-band", "band": "watch", "note": "Grades are from a unit retaken last week.",
        "expires_on": (TODAY + timedelta(days=7)).isoformat()})
    assert r.status_code == 201, r.text
    revoke_after.append((sid, r.json()["id"]))
    row = next(s for s in client.get("/api/students", params={"band": "watch"}).json() if s["sid"] == sid)
    assert row["band"] == "watch" and row["computed_band"] == "needs-plan"


def test_a_new_override_replaces_the_old_one(client, db, revoke_after):
    sid = _unplanned_needs_plan(client, db)
    until = (TODAY + timedelta(days=7)).isoformat()
    a = client.post(f"/api/students/{sid}/overrides", json={"kind": "acknowledge", "note": "Known to the counselor.", "expires_on": until}).json()
    b = client.post(f"/api/students/{sid}/overrides", json={"kind": "set-band", "band": "steady", "note": "Doing fine after a family illness.", "expires_on": until}).json()
    revoke_after.extend([(sid, a["id"]), (sid, b["id"])])
    overrides = client.get(f"/api/students/{sid}/history").json()["overrides"]
    assert [o["active"] for o in overrides if o["id"] in (a["id"], b["id"])] == [True, False]


def test_overrides_must_expire_soon_and_make_sense(client, db):
    sid = _unplanned_needs_plan(client, db)
    far = client.post(f"/api/students/{sid}/overrides", json={
        "kind": "acknowledge", "note": "Known to everyone involved.", "expires_on": (TODAY + timedelta(days=200)).isoformat()})
    assert far.status_code == 422
    same = client.post(f"/api/students/{sid}/overrides", json={
        "kind": "set-band", "band": "needs-plan", "note": "No change at all here.", "expires_on": (TODAY + timedelta(days=5)).isoformat()})
    assert same.status_code == 422
    steady = next(s["sid"] for s in client.get("/api/students", params={"band": "steady"}).json())
    ack = client.post(f"/api/students/{steady}/overrides", json={
        "kind": "acknowledge", "note": "Nothing to acknowledge here.", "expires_on": (TODAY + timedelta(days=5)).isoformat()})
    assert ack.status_code == 422


def test_only_plan_owners_can_override(login, db):
    from tests.test_auth import _teacher_and_outsider

    _, taught, _, _ = _teacher_and_outsider(db)
    r = login("r.okonkwo").post(f"/api/students/{sorted(taught)[0]}/overrides", json={
        "kind": "acknowledge", "note": "I know about this one.", "expires_on": (TODAY + timedelta(days=5)).isoformat()})
    assert r.status_code == 403


def test_expired_overrides_stop_applying(client, db, revoke_after):
    from app.analytics import build_signals

    sid = _unplanned_needs_plan(client, db)
    r = client.post(f"/api/students/{sid}/overrides", json={
        "kind": "set-band", "band": "steady", "note": "Temporary while records are fixed.",
        "expires_on": (TODAY + timedelta(days=3)).isoformat()})
    revoke_after.append((sid, r.json()["id"]))
    assert build_signals(db, TODAY)[sid].band == "steady"
    assert build_signals(db, TODAY + timedelta(days=4))[sid].band == "needs-plan"


# ---- rejection reasons ---------------------------------------------------------------
def test_a_rejection_needs_a_reason_and_keeps_it(client, db):
    p = Proposal(agent="support", kind="support_plan", summary="Open a check-in", status="pending", evidence=[],
                 payload={"student_sid": "S-1507", "kind": "check-in", "title": "Check-in"})
    db.add(p)
    db.commit()
    assert client.post(f"/api/agents/proposals/{p.id}/reject", json={}).status_code == 422
    r = client.post(f"/api/agents/proposals/{p.id}/reject",
                    json={"note": "Already seeing the counselor weekly."})
    assert r.status_code == 200
    out = r.json()["proposal"]
    assert out["decision_note"] == "Already seeing the counselor weekly." and out["decided_by"].startswith("admin@")
    rejected = client.get("/api/agents/proposals", params={"status": "rejected"}).json()
    assert any(x["id"] == p.id and x["decision_note"] for x in rejected)


def test_reject_proposal_records_the_note(db):
    p = Proposal(agent="support", kind="support_plan", summary="x", status="pending", evidence=[], payload={})
    db.add(p)
    db.commit()
    reject_proposal(db, p, "Duplicate of an existing plan", by_email="someone@example.edu")
    assert p.decision_note == "Duplicate of an existing plan" and p.decided_by == "someone@example.edu"
