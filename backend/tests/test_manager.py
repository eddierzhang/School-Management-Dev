"""General manager tests. No Ollama calls: the tools and the queue are exercised directly.

The queue is stubbed so dispatched runs stay `queued` instead of reaching the model.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai import manager as M
from app.ai.agents import FLEET
from app.ai.toolkit import ToolError
from app.models import AgentRun, Proposal


@pytest.fixture
def no_worker(monkeypatch):
    queued = []
    monkeypatch.setattr(M, "enqueue", lambda db, run: queued.append(run.id))
    return queued


@pytest.fixture
def cleanup(db):
    """Remove runs a test creates, and set aside runs other tests left "running",
    which would otherwise make every agent look busy."""
    before = {r.id: r.status for r in db.scalars(select(AgentRun)).all()}
    for r in db.scalars(select(AgentRun).where(AgentRun.status.in_(["running", "queued"]))).all():
        r.status = "set-aside"
    db.commit()
    yield
    db.rollback()
    for r in db.scalars(select(AgentRun)).all():
        if r.id not in before:
            db.delete(r)
        elif r.status == "set-aside":
            r.status = before[r.id]
    db.commit()


# --- the briefing --------------------------------------------------------------
def test_briefing_numbers_match_the_screens(client):
    b = client.get("/api/manager/briefing").json()
    s = client.get("/api/summary").json()
    assert b["students"]["total"] == s["students"]
    assert b["students"]["needs_plan"] == s["needs_plan"]
    assert b["students"]["open_plans"] == s["open_interventions"]
    f = client.get("/api/finance/summary").json()
    assert b["finance"]["over_budget"] == f["over"] and b["finance"]["at_risk"] == f["at_risk"]
    stock = client.get("/api/inventory/summary").json()
    assert b["stockroom"]["needs_attention"] == stock["needs_attention"]


def test_briefing_raises_what_needs_attention(client):
    b = client.get("/api/manager/briefing").json()
    text = " ".join(b["attention"])
    assert "need a support plan" in text
    assert "Physical education equipment" in text, "the over-budget line is raised"
    assert all(isinstance(line, str) and line for line in b["attention"])


def test_overview_tool_is_compact(db):
    out = M.school_briefing(db, {"proposals": []})
    import json
    assert len(json.dumps(out)) < 3500, "the overview must fit comfortably in a small model's context"
    assert out["needs_attention"]


def test_unknown_section_is_refused(db):
    with pytest.raises(ToolError, match="section must be one of"):
        M.school_briefing(db, {"proposals": []}, section="gossip")


# --- the fleet ------------------------------------------------------------------
def test_manager_is_in_the_fleet_and_proposes_nothing():
    assert "manager" in FLEET
    assert not any(t.proposes for t in FLEET["manager"].tools)


def test_fleet_status_lists_specialists_not_itself(db):
    names = {a["agent"] for a in M.fleet_status(db, {})["agents"]}
    assert "manager" not in names and {"support", "stockroom", "finance", "registrar"} <= names


def test_agent_report_refuses_unknown_agents(db):
    with pytest.raises(ToolError, match="No specialist"):
        M.agent_report(db, {}, "janitor")


# --- dispatch --------------------------------------------------------------------
def test_dispatch_queues_a_run_linked_to_the_manager_run(db, no_worker, cleanup):
    parent = AgentRun(agent="manager", model="test", prompt="get work done", status="running", transcript=[])
    db.add(parent); db.commit()
    out = M.dispatch_agent(db, {"proposals": []}, "finance", "Review PE-EQP and propose a transfer to cover it.",
                           "PE-EQP is over budget")
    run = db.get(AgentRun, out["run_id"])
    assert run.status == "queued" and run.agent == "finance"
    assert run.parent_run_id == parent.id
    assert no_worker == [run.id]
    parent.status = "done"; db.commit()


def test_dispatch_refuses_itself_unknowns_vague_tasks_and_busy_agents(db, no_worker, cleanup):
    ctx = {"proposals": []}
    with pytest.raises(ToolError, match="cannot dispatch yourself"):
        M.dispatch_agent(db, ctx, "manager", "Do a full review of everything please.", "x")
    with pytest.raises(ToolError, match="No specialist"):
        M.dispatch_agent(db, ctx, "janitor", "Clean the science wing thoroughly today.", "x")
    with pytest.raises(ToolError, match="full instruction"):
        M.dispatch_agent(db, ctx, "stockroom", "go", "x")
    M.dispatch_agent(db, ctx, "stockroom", "Check the science lab items and propose orders.", "low stock")
    with pytest.raises(ToolError, match="already dispatched stockroom"):
        M.dispatch_agent(db, ctx, "stockroom", "Check the science lab items and propose orders.", "again")
    with pytest.raises(ToolError, match="already working"):
        M.dispatch_agent(db, {"proposals": []}, "stockroom", "Check the maths items and propose orders.", "busy")


def test_dispatch_is_capped_per_run(db, no_worker, cleanup):
    ctx = {"proposals": []}
    for name in ("support", "registrar", "stockroom"):
        M.dispatch_agent(db, ctx, name, f"Review your area carefully and propose what is needed ({name}).", "x")
    with pytest.raises(ToolError, match="already dispatched 3"):
        M.dispatch_agent(db, ctx, "finance", "Review the budget lines at risk and propose transfers.", "x")


def test_dispatch_puts_a_job_on_the_queue(db, cleanup):
    """Dispatched runs are database jobs, so a restart cannot lose them (tests/test_jobs.py)."""
    from app.models import Job

    out = M.dispatch_agent(db, {"proposals": []}, "support", "Review the flagged students and propose plans.", "x")
    job = db.scalar(select(Job).where(Job.kind == "agent_run").order_by(Job.id.desc()).limit(1))
    assert job.payload["run_id"] == out["run_id"] and job.status == "queued"
    db.delete(job); db.commit()


def test_manager_run_endpoint_shows_dispatched_runs_and_their_proposals(client, db, no_worker, cleanup):
    parent = AgentRun(agent="manager", model="test", prompt="work", status="running", transcript=[])
    db.add(parent); db.commit()
    out = M.dispatch_agent(db, {"proposals": []}, "support", "Review the flagged students and propose plans.", "x")
    child = db.get(AgentRun, out["run_id"])
    p = Proposal(agent="support", kind="support_plan", summary="test plan", reason="r", payload={}, evidence=[],
                 status="pending", run_id=child.id)
    db.add(p); db.commit()
    try:
        body = client.get(f"/api/manager/runs/{parent.id}").json()
        assert [d["id"] for d in body["dispatched"]] == [child.id]
        assert body["dispatched"][0]["proposals"][0]["summary"] == "test plan"
    finally:
        db.delete(db.get(Proposal, p.id)); parent.status = "done"; db.commit()
