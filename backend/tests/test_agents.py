"""Agent-layer tests.

None of these call Ollama. The model is the one part that cannot be asserted on,
so everything around it — argument validation, the repair messages, the proposal
boundary, and the executor's staleness checks — is tested without it. That split
is deliberate: the guardrails are what make an unreliable model safe, so the
guardrails are what must be covered.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai import ollama
from app.ai.agents import FLEET
from app.ai.executor import ApplyError, apply_proposal, reject_proposal
from app.ai.toolkit import ToolError, validate_arguments
from app.ai import tools as T
from app.models import Course, Enrollment, InventoryItem, Intervention, Proposal, Student


# --- the fleet is shaped for a small model --------------------------------
def test_every_agent_has_a_small_tool_surface():
    assert FLEET, "the fleet must not be empty"
    for name, agent in FLEET.items():
        assert 3 <= len(agent.tools) <= 7, f"{name} has {len(agent.tools)} tools — too many for a 4B model"
        assert len({t.name for t in agent.tools}) == len(agent.tools), f"{name} has duplicate tool names"
        # The general manager is the one exception: it dispatches specialists, who
        # propose. Giving it propose_ tools would let it bypass them.
        if name != "manager":
            assert any(t.proposes for t in agent.tools), f"{name} cannot propose anything"
        else:
            assert not any(t.proposes for t in agent.tools), "the manager must not propose changes itself"
        assert agent.opening, f"{name} has no opening read, so it can start by inventing data"
        assert agent.opening[0] in {t.name for t in agent.tools}, f"{name}'s opening read is not one of its tools"


def test_no_tool_writes_to_the_database(db):
    """The whole safety model: reading tools read, proposing tools only record intent."""
    before = {
        "courses": db.query(Course).count(),
        "enrollments": db.query(Enrollment).count(),
        "interventions": db.query(Intervention).count(),
        "requisitioned": db.query(InventoryItem).filter(InventoryItem.requisitioned).count(),
    }
    ctx: dict = {"proposals": []}
    item = db.scalar(select(InventoryItem).where(InventoryItem.on_hand <= InventoryItem.reorder_point))
    T.propose_requisition(db, ctx, skus=[item.sku], reason="test")
    sid = T.list_flagged_students(db, ctx)["items"][0]["sid"]
    T.propose_support_plan(db, ctx, student_sid=sid, kind="check-in",
                           title="Test plan", rationale="test")
    db.expire_all()
    after = {
        "courses": db.query(Course).count(),
        "enrollments": db.query(Enrollment).count(),
        "interventions": db.query(Intervention).count(),
        "requisitioned": db.query(InventoryItem).filter(InventoryItem.requisitioned).count(),
    }
    assert before == after, "a tool changed the record — agents must only propose"
    assert len(ctx["proposals"]) == 2


# --- argument repair: the observed failure --------------------------------
def test_wrong_parameter_name_gets_a_repair_message():
    """Observed live: list_items_for_course({"category": "All"}) — wrong parameter entirely."""
    tool = {t.name: t for t in FLEET["stockroom"].tools}["list_items_for_course"]
    with pytest.raises(ToolError) as e:
        validate_arguments(tool, {"category": "All"})
    msg = str(e.value)
    assert "course_code" in msg and "required" in msg
    assert "category" in msg, "the message should name the argument that was wrong"


def test_quoted_numbers_are_coerced_not_rejected():
    tool = {t.name: t for t in FLEET["registrar"].tools}["find_open_rooms"]
    assert validate_arguments(tool, {"period": "4"}) == {"period": 4}


def test_comma_string_is_accepted_for_an_array():
    tool = {t.name: t for t in FLEET["stockroom"].tools}["propose_requisition"]
    got = validate_arguments(tool, {"skus": "A-1, B-2", "reason": "r"})
    assert got["skus"] == ["A-1", "B-2"]


def test_enum_violation_lists_the_valid_values():
    tool = {t.name: t for t in FLEET["support"].tools}["propose_support_plan"]
    with pytest.raises(ToolError) as e:
        validate_arguments(tool, {"student_sid": "S-1", "kind": "astrology",
                                  "title": "t", "rationale": "r"})
    assert "tutoring" in str(e.value)


def test_unknown_extra_arguments_are_dropped_once_required_are_present():
    tool = {t.name: t for t in FLEET["stockroom"].tools}["get_item"]
    assert validate_arguments(tool, {"sku": "X-1", "nonsense": 1}) == {"sku": "X-1"}


# --- hallucinated identifiers never become proposals ----------------------
def test_invented_sku_is_refused_with_guidance(db):
    ctx: dict = {"proposals": []}
    with pytest.raises(ToolError) as e:
        T.propose_requisition(db, ctx, skus=["MAT-ALG-101"], reason="invented")
    assert "do not exist" in str(e.value)
    assert "list_low_stock" in str(e.value), "the error should tell the model how to recover"
    assert ctx["proposals"] == []


def test_invented_student_is_refused(db):
    ctx: dict = {"proposals": []}
    with pytest.raises(ToolError):
        T.propose_support_plan(db, ctx, student_sid="S-9999", kind="tutoring",
                               title="t", rationale="r")
    assert ctx["proposals"] == []


def test_section_proposal_refuses_a_room_already_in_use(db):
    ctx: dict = {"proposals": []}
    pressured = T.list_waitlist_pressure(db, ctx)["items"]
    assert pressured, "the seeded term should have waitlists"
    code = pressured[0]["code"]
    clash = db.scalar(select(Course).where(Course.code == code))
    with pytest.raises(ToolError) as e:
        T.propose_new_section(db, ctx, course_code=code, period=clash.period,
                              room=clash.room, seats=20, reason="r")
    assert "already used" in str(e.value)


def test_section_proposal_refuses_a_class_with_no_waitlist(db):
    ctx: dict = {"proposals": []}
    rows = T.list_sections(db, ctx)["items"]
    calm = next(r for r in rows if r["waitlist"] == 0)
    with pytest.raises(ToolError) as e:
        T.propose_new_section(db, ctx, course_code=calm["code"], period=1,
                              room="ZZ-999", seats=10, reason="r")
    assert "nobody on its waitlist" in str(e.value)


# --- tool results stay small ----------------------------------------------
def test_list_tools_cap_their_output(db):
    ctx: dict = {"proposals": []}
    for result in (T.list_low_stock(db, ctx), T.list_sections(db, ctx),
                   T.list_flagged_students(db, ctx), T.list_skill_gaps(db, ctx)):
        assert result["returned"] <= T.LIST_CAP
        if result["total"] > T.LIST_CAP:
            assert "note" in result, "a truncated result must say so"


# --- the executor ----------------------------------------------------------
def _pending(db, agent, kind, payload, summary="test") -> Proposal:
    p = Proposal(agent=agent, kind=kind, summary=summary, reason="test",
                 payload=payload, evidence=[], status="pending")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_approving_a_requisition_applies_it(db):
    item = db.scalar(select(InventoryItem).where(InventoryItem.requisitioned == False))  # noqa: E712
    sku = item.sku
    p = _pending(db, "stockroom", "requisition", {"skus": [sku]})
    try:
        result = apply_proposal(db, p)
        db.expire_all()
        assert db.scalar(select(InventoryItem).where(InventoryItem.sku == sku)).requisitioned is True
        assert p.status == "approved" and "requisition" in result
    finally:
        db.scalar(select(InventoryItem).where(InventoryItem.sku == sku)).requisitioned = False
        db.commit()


def test_a_proposal_cannot_be_applied_twice(db):
    item = db.scalar(select(InventoryItem))
    sku, was = item.sku, item.requisitioned
    p = _pending(db, "stockroom", "requisition", {"skus": [sku]})
    try:
        apply_proposal(db, p)
        with pytest.raises(ApplyError) as e:
            apply_proposal(db, p)
        assert "already" in str(e.value)
    finally:
        db.scalar(select(InventoryItem).where(InventoryItem.sku == sku)).requisitioned = was
        db.commit()


def test_capacity_change_is_refused_when_it_would_strand_students(db):
    course = db.scalar(select(Course).where(Course.code == "MAT-150"))
    enrolled = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == course.id, Enrollment.status == "enrolled")).all())
    p = _pending(db, "registrar", "capacity_change",
                 {"course_code": "MAT-150", "new_capacity": max(0, enrolled - 1)})
    with pytest.raises(ApplyError) as e:
        apply_proposal(db, p)
    assert "enrolled" in str(e.value)


def test_support_plan_is_refused_if_one_was_opened_meanwhile(db):
    sid = T.list_flagged_students(db, {"proposals": []})["items"][0]["sid"]
    st = db.scalar(select(Student).where(Student.sid == sid))
    p = _pending(db, "support", "support_plan",
                 {"student_sid": sid, "kind": "family-contact", "title": "Call home", "rationale": "r"})
    blocker = Intervention(student_id=st.id, kind="family-contact", title="Already open",
                           rationale="", owner="office", status="active",
                           opened_on=__import__("datetime").date(2026, 9, 1))
    db.add(blocker)
    db.commit()
    try:
        with pytest.raises(ApplyError) as e:
            apply_proposal(db, p)
        assert "already has an active" in str(e.value)
    finally:
        db.delete(blocker)
        db.commit()


def test_new_section_moves_students_off_the_waitlist(db):
    ctx: dict = {"proposals": []}
    pressured = T.list_waitlist_pressure(db, ctx)["items"][0]
    code = pressured["code"]
    src = db.scalar(select(Course).where(Course.code == code))
    waiting_before = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == src.id, Enrollment.status == "waitlist")).all())
    free = T.find_open_rooms(db, ctx, period=6)["free_rooms"]
    room = free[0] if free else "NEW-1"
    p = _pending(db, "registrar", "new_section",
                 {"course_code": code, "period": 6, "room": room, "seats": 20,
                  "move_from_waitlist": 5, "teacher": src.teacher})
    result = apply_proposal(db, p)
    new = None
    try:
        db.expire_all()
        new = db.scalar(select(Course).where(Course.code == code.split(".")[0] + ".B"))
        assert new is not None, result
        moved = db.scalars(select(Enrollment).where(
            Enrollment.course_id == new.id, Enrollment.status == "enrolled")).all()
        waiting_after = len(db.scalars(select(Enrollment).where(
            Enrollment.course_id == src.id, Enrollment.status == "waitlist")).all())
        assert len(moved) == 5
        assert waiting_after == waiting_before - 5
    finally:
        # Put the term back as it was — the API tests assert exact catalogue counts.
        if new is not None:
            for enr in db.scalars(select(Enrollment).where(Enrollment.course_id == new.id)).all():
                enr.course_id = src.id
                enr.status = "waitlist"
            # Autoflush is off: without this, deleting the section cascades to the
            # enrollments just moved back, and the waitlist loses those students.
            db.flush()
            db.delete(new)
            db.commit()


def test_rejecting_changes_nothing(db):
    item = db.scalar(select(InventoryItem).where(InventoryItem.requisitioned == False))  # noqa: E712
    p = _pending(db, "stockroom", "requisition", {"skus": [item.sku]})
    reject_proposal(db, p, "Not this term")
    db.expire_all()
    assert db.scalar(select(InventoryItem).where(InventoryItem.sku == item.sku)).requisitioned is False
    assert p.status == "rejected"


# --- routes ---------------------------------------------------------------
def test_fleet_endpoint_reports_runtime_and_agents(client):
    body = client.get("/api/agents").json()
    assert {a["name"] for a in body["agents"]} == set(FLEET)
    assert "reachable" in body["runtime"] and "can_run_agents" in body["runtime"]
    for a in body["agents"]:
        assert a["tools"] and (a["name"] == "manager" or any(t["proposes"] for t in a["tools"]))


def test_running_an_unknown_agent_is_404(client):
    assert client.post("/api/agents/nosuchagent/run", json={}).status_code == 404


def test_run_is_refused_when_the_model_cannot_call_tools(client, monkeypatch):
    monkeypatch.setattr(ollama, "health", lambda: {
        "reachable": True, "error": None, "model": "gemma3:1b",
        "models": ["gemma3:1b"], "capabilities": ["completion"], "can_run_agents": False})
    r = client.post("/api/agents/stockroom/run", json={})
    assert r.status_code == 503
    assert "cannot call tools" in r.json()["detail"]


def test_run_is_refused_when_ollama_is_down(client, monkeypatch):
    monkeypatch.setattr(ollama, "health", lambda: {
        "reachable": False, "error": "Cannot reach Ollama at http://localhost:11434",
        "models": [], "model": "qwen3:4b", "can_run_agents": False})
    r = client.post("/api/agents/stockroom/run", json={})
    assert r.status_code == 503
    assert "Cannot reach Ollama" in r.json()["detail"]


def test_starting_a_run_records_it_without_blocking(client, monkeypatch):
    monkeypatch.setattr(ollama, "health", lambda: {
        "reachable": True, "error": None, "model": "qwen3:4b",
        "models": ["qwen3:4b"], "capabilities": ["tools"], "can_run_agents": True})
    from app.db import SessionLocal
    from app.models import Job

    r = client.post("/api/agents/support/run", json={"task": "Look at grade 7 only."})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["agent"] == "support"
    with SessionLocal() as s:
        job = s.scalar(select(Job).where(Job.kind == "agent_run").order_by(Job.id.desc()).limit(1))
        assert job.payload == {"run_id": body["id"], "agent": "support", "task": "Look at grade 7 only."}
        s.delete(job)          # nothing here should reach the model
        s.commit()
    assert client.get(f"/api/agents/runs/{body['id']}").json()["id"] == body["id"]


def test_approving_a_stale_proposal_returns_409(client):
    """Uses its own short-lived session: holding one open across an HTTP call
    that writes through a second connection deadlocks SQLite."""
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        item = s.scalar(select(InventoryItem))
        p = _pending(s, "stockroom", "reorder_point",
                     {"sku": item.sku, "new_reorder_point": item.par + 500})
        pid = p.id
    finally:
        s.close()
    r = client.post(f"/api/agents/proposals/{pid}/approve")
    assert r.status_code == 409
    assert "par level" in r.json()["detail"]


def test_a_run_whose_process_died_does_not_stay_running_for_ever(client):
    """A server restart or a kill mid-inference would otherwise strand it."""
    from datetime import datetime, timedelta

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import AgentRun

    s = SessionLocal()
    try:
        old = AgentRun(
            agent="stockroom", model="qwen3:4b", prompt="orphaned", status="running",
            transcript=[],
            started_at=datetime.utcnow() - timedelta(seconds=get_settings().agent_max_seconds + 600),
        )
        s.add(old)
        s.commit()
        rid = old.id
    finally:
        s.close()

    body = client.get(f"/api/agents/runs/{rid}").json()
    assert body["status"] == "failed"
    assert "did not" in (body["error"] or "") or "stopped without finishing" in (body["error"] or "")


def test_a_fresh_run_is_not_reaped(client, monkeypatch):
    from app.ai import ollama as _ollama

    monkeypatch.setattr(_ollama, "health", lambda: {
        "reachable": True, "error": None, "model": "qwen3:4b",
        "models": ["qwen3:4b"], "capabilities": ["tools"], "can_run_agents": True})
    from app.db import SessionLocal
    from app.models import Job

    started = client.post("/api/agents/registrar/run", json={}).json()
    assert client.get(f"/api/agents/runs/{started['id']}").json()["status"] == "queued"
    with SessionLocal() as s:
        for job in s.scalars(select(Job).where(Job.kind == "agent_run", Job.status == "queued")).all():
            if job.payload.get("run_id") == started["id"]:
                s.delete(job)
        s.commit()
