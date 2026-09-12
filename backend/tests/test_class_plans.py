"""Class improvement plans, without calling Ollama.

The model drafts; everything around the draft is deterministic and tested here:
the performance snapshot, the checks that send a bad draft back, scoping a run
to one class, adopting a plan with its baseline, and closing it.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.ai import tools as T
from app.ai.agents import FLEET
from app.ai.executor import ApplyError, apply_proposal
from app.ai.toolkit import ToolError
from app.class_plans import all_performance, performance, uncited_percentages
from app.models import AgentRun, ClassPlan, Proposal

GOOD = dict(
    course_code="MAT-150", title="Reteach word problems",
    diagnosis="The class average is 70%, under the 72% line. Word problems average 66%.",
    focus_strands=["word problems"],
    actions=["S. Frankel reteaches word problems with worked examples over the next two weeks",
             "A five-question word problems quiz every Friday, reviewed the following Monday"],
    goal="Word problems average to 72% by the review",
)


@pytest.fixture
def clean(db):
    yield
    db.rollback()
    for plan in db.scalars(select(ClassPlan)).all():
        db.delete(plan)
    for p in db.scalars(select(Proposal).where(Proposal.kind == "class_plan")).all():
        db.delete(p)
    db.commit()


# --- the snapshot -----------------------------------------------------------
def test_every_class_is_read_and_the_neediest_come_first(db):
    rows = all_performance(db)
    assert len(rows) == 14
    order = {"needs-plan": 0, "watch": 1, "strong": 2, "no-data": 3}
    assert [order[r.status] for r in rows] == sorted(order[r.status] for r in rows)
    assert rows[0].status == "needs-plan" and rows[0].issues


def test_snapshot_names_the_cohort_gap(db):
    p = performance(db, "MAT-150")
    assert p.strands[0].strand == "word problems"
    assert p.strands == sorted(p.strands, key=lambda s: s.mean)
    assert any("word problems" in i for i in p.issues)
    assert 0 < p.completion <= 1 and p.kinds


def test_class_agent_is_in_the_fleet_and_opens_on_real_data():
    agent = FLEET["classes"]
    assert agent.opening[0] == "list_classes_by_need"
    assert any(t.proposes == "class_plan" for t in agent.tools)


# --- checks on a draft ------------------------------------------------------
def test_a_well_formed_draft_is_recorded_not_written(db, clean):
    ctx: dict = {"proposals": []}
    before = db.query(ClassPlan).count()
    T.propose_class_plan(db, ctx, **GOOD)
    assert len(ctx["proposals"]) == 1 and ctx["proposals"][0]["kind"] == "class_plan"
    assert db.query(ClassPlan).count() == before


def test_an_invented_percentage_is_sent_back(db):
    with pytest.raises(ToolError) as e:
        T.propose_class_plan(db, {"proposals": []}, **(GOOD | {
            "diagnosis": "Word problems average 41%, the lowest in the school."}))
    assert "41%" in str(e.value) and "not in the class data" in str(e.value)


def test_a_target_may_name_a_number_the_class_has_not_reached():
    p_text = "Raise word problems to 83% and hold the average above 79%."
    from app.class_plans import performance as perf
    from app.db import SessionLocal
    with SessionLocal() as s:
        assert uncited_percentages(p_text, perf(s, "MAT-150")) == []


def test_a_strand_the_course_does_not_teach_is_refused(db):
    with pytest.raises(ToolError) as e:
        T.propose_class_plan(db, {"proposals": []}, **(GOOD | {"focus_strands": ["graphing"]}))
    assert "does not teach" in str(e.value) and "word problems" in str(e.value)


def test_vague_or_unmeasurable_plans_are_refused(db):
    with pytest.raises(ToolError):
        T.propose_class_plan(db, {"proposals": []}, **(GOOD | {"actions": ["Reteach", "Quiz"]}))
    with pytest.raises(ToolError):
        T.propose_class_plan(db, {"proposals": []}, **(GOOD | {"goal": "Students understand better"}))


def test_a_plan_that_ignores_missing_work_is_sent_back(db):
    """Observed live on SOC-130: 16% of work not handed in, and a plan of two reteach lessons."""
    p = performance(db, "SOC-130")
    assert p.completion < 0.85
    strands = [s.strand for s in p.strands[:2]]
    draft = dict(course_code="SOC-130", title="Reteach research", focus_strands=strands,
                 diagnosis="The class average is 68%, under the 72% line.",
                 actions=["T. Ellery reteaches research with a guided source hunt next week",
                          "Short presentation practice in pairs every Thursday for three weeks"],
                 goal="Research average to 72%")
    with pytest.raises(ToolError) as e:
        T.propose_class_plan(db, {"proposals": []}, **draft)
    assert "not handed in" in str(e.value)
    ctx: dict = {"proposals": []}
    draft["actions"].append("Ten minutes of class time on Mondays to catch up on past-due work")
    T.propose_class_plan(db, ctx, **draft)
    assert len(ctx["proposals"]) == 1


def test_a_scoped_run_cannot_plan_for_another_class(db):
    with pytest.raises(ToolError) as e:
        T.propose_class_plan(db, {"proposals": [], "only_course": "ENG-201"}, **GOOD)
    assert "only for ENG-201" in str(e.value)


# --- adopting and closing ---------------------------------------------------
def _pending(db, payload) -> Proposal:
    p = Proposal(agent="classes", kind="class_plan", summary="t", reason="t", payload=payload,
                 evidence=[], status="pending")
    db.add(p)
    db.commit()
    return p


def test_approving_adopts_a_plan_with_its_baseline(client, db, clean):
    p = _pending(db, {k: GOOD[k] for k in GOOD})
    apply_proposal(db, p)
    plan = db.scalar(select(ClassPlan).where(ClassPlan.course_code == "MAT-150"))
    assert plan.status == "active" and plan.owner == "S. Frankel"
    assert plan.baseline["mean"] == performance(db, "MAT-150").mean

    body = client.get("/api/courses/MAT-150/improvement").json()
    assert body["plans"][0]["title"] == GOOD["title"]
    measures = {r["measure"]: r for r in body["plans"][0]["progress"]}
    assert measures["word problems"]["change"] == 0

    # A second plan cannot be proposed or adopted while one is active.
    with pytest.raises(ToolError):
        T.propose_class_plan(db, {"proposals": []}, **GOOD)
    with pytest.raises(ApplyError):
        apply_proposal(db, _pending(db, {k: GOOD[k] for k in GOOD}))

    closed = client.patch(f"/api/improvement-plans/{plan.id}",
                          json={"status": "completed", "outcome": "Word problems up to 73%."}).json()
    assert closed["status"] == "completed" and closed["closed_on"]
    assert client.patch(f"/api/improvement-plans/{plan.id}", json={"status": "retired"}).status_code == 409


def test_a_draft_waiting_for_approval_blocks_another(db, clean):
    _pending(db, {k: GOOD[k] for k in GOOD})
    with pytest.raises(ToolError) as e:
        T.propose_class_plan(db, {"proposals": []}, **GOOD)
    assert "waiting for approval" in str(e.value)


def test_improvement_endpoints(client, db, clean):
    rows = client.get("/api/improvement").json()
    assert len(rows) == 14 and rows[0]["status"] == "needs-plan"
    assert client.get("/api/courses/XXX-999/improvement").status_code == 404
    _pending(db, {k: GOOD[k] for k in GOOD})
    body = client.get("/api/courses/MAT-150/improvement").json()
    assert len(body["drafts"]) == 1 and body["performance"]["code"] == "MAT-150"


def test_drafting_refuses_while_a_run_for_that_class_is_in_flight(client, db):
    run = AgentRun(agent="classes", model="m", prompt="p", status="running", transcript=[],
                   subject="course:MAT-150", started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    try:
        r = client.post("/api/courses/MAT-150/improvement/draft", json={})
        assert r.status_code == 409 and "already being drafted" in r.json()["detail"]
    finally:
        db.delete(run)
        db.commit()


def test_a_count_borrowed_from_another_measure_is_sent_back(db):
    """Observed live on MAT-150: "15 of 28 students below the 72% line". 15 of 28 is the
    word-problems strand (and, by coincidence, the students declining); the class is 13 of 28."""
    from app.class_plans import miscounted
    p = performance(db, "MAT-150")
    wrong = "The class average is 70%, with 15 of 28 students below the 72% line, and recent work has declined."
    assert miscounted(wrong, p) == ["15 of 28"]
    assert miscounted(f"{p.below_line} of {p.students} students are below the line.", p) == []
    strand = p.strands[0]
    assert miscounted(f"In {strand.strand}, {strand.below_line} of {strand.cohort} are below the line.", p) == []
    with pytest.raises(ToolError) as e:
        T.propose_class_plan(db, {"proposals": []}, **(GOOD | {"diagnosis": wrong}))
    assert "do not match" in str(e.value)
