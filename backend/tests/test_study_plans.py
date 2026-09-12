"""Study plans, without calling Ollama.

The model drafts; everything around the draft is deterministic and tested here:
the class-work reading and its findings, the checks that send a bad draft back,
scoping a run to one student in one class, adopting a plan with its baseline,
and closing it.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai import tools as T
from app.ai.agents import FLEET
from app.ai.executor import ApplyError, apply_proposal
from app.ai.toolkit import ToolError
from app.models import Proposal, StudyPlan
from app.study_plans import class_work, miscounted, students_needing_plans

SID, CODE = "S-1507", "MAT-150"


def good(w) -> dict:
    """A draft built only from the reading, the way a well-behaved agent would write it."""
    weak = w.strands[0]
    return dict(
        student_sid=SID, course_code=CODE, title=f"Catch up and relearn {weak.strand}",
        diagnosis=f"{weak.strand} is {weak.pct:.0f}% in the gradebook. "
                  f"{len(w.missing)} of {len(w.assignments)} assignments are not handed in.",
        focus_strands=[weak.strand],
        sessions=[f"Mon week 1, 30 min with the teacher: hand in the missing work, starting with {w.missing[0].title}",
                  f"Wed week 1, 25 min: redo two {weak.strand} problems from the project with worked examples",
                  f"Mon week 2, 20 min: timed practice quiz on {weak.strand}, checked by the teacher",
                  "Fri week 3, 15 min: review the week's corrections and write down the one step still unclear"],
        catch_up_assignments=[a.id for a in w.missing],
        goal=f"{weak.strand} to 72% and no missing work by the review",
    )


def wrong_count(w) -> int:
    """A count that is neither the missing nor the handed-in total, whatever other tests did to the gradebook."""
    real = {len(w.missing), len(w.assignments) - len(w.missing)}
    return next(n for n in range(len(w.assignments) + 1) if n not in real)


@pytest.fixture
def work(db):
    return class_work(db, SID, CODE)


@pytest.fixture
def clean(db):
    yield
    db.rollback()
    for plan in db.scalars(select(StudyPlan)).all():
        db.delete(plan)
    for p in db.scalars(select(Proposal).where(Proposal.kind == "study_plan")).all():
        db.delete(p)
    db.commit()


# --- the reading ------------------------------------------------------------
def test_reading_lists_every_assignment_and_the_missing_ones(work):
    assert work.assignments and work.strands and work.kinds
    assert work.missing and all(a.pct is None for a in work.missing)
    assert work.strands == sorted(work.strands, key=lambda s: s.pct)
    assert any(f.code == "missing-work" for f in work.findings)


def test_missing_work_is_told_apart_from_not_understanding(work):
    """A strand low only because pieces were never handed in is not a reteach."""
    for s in work.strands:
        codes = {f.code for f in work.findings if f.strand == s.strand}
        if "strand-missing" in codes:
            assert s.missing and s.handed_in_pct >= 72 > s.pct
            assert not codes & {"strand-gap", "class-gap"}


def test_students_needing_plans_are_worst_first(db):
    rows = students_needing_plans(db)
    assert rows and rows == sorted(rows, key=lambda w: (w.pct, -w.struggle))
    assert all(w.needs_plan for w in rows)


def test_study_agent_is_in_the_fleet_and_opens_on_real_data():
    agent = FLEET["study"]
    assert agent.opening[0] == "list_students_for_study_plans"
    assert any(t.proposes == "study_plan" for t in agent.tools)


# --- checks on a draft ------------------------------------------------------
def test_a_well_formed_draft_is_recorded_not_written(db, work, clean):
    ctx: dict = {"proposals": []}
    before = db.query(StudyPlan).count()
    T.propose_study_plan(db, ctx, **good(work))
    assert len(ctx["proposals"]) == 1 and ctx["proposals"][0]["kind"] == "study_plan"
    assert db.query(StudyPlan).count() == before


@pytest.mark.parametrize("change, message", [
    (lambda d, w: {"diagnosis": "Word problems average 41%."}, "not in the student's class data"),
    (lambda d, w: {"focus_strands": ["photosynthesis"]}, "does not assess"),
    (lambda d, w: {"sessions": d["sessions"][:3] + ["Study more"]}, "Too vague"),
    (lambda d, w: {"sessions": [s.replace("min", "") for s in d["sessions"]]}, "how long"),
    (lambda d, w: {"catch_up_assignments": []}, "catch_up_assignments"),
    (lambda d, w: {"catch_up_assignments": [999999]}, "not missing"),
    (lambda d, w: {"goal": "do better"}, "measurable"),
    (lambda d, w: {"diagnosis": f"{wrong_count(w)} of {len(w.assignments)} assignments are missing."},
     "counts do not match"),
])
def test_a_bad_draft_is_sent_back_with_what_to_fix(db, work, change, message):
    draft = good(work)
    with pytest.raises(ToolError) as e:
        T.propose_study_plan(db, {"proposals": []}, **(draft | change(draft, work)))
    assert message in str(e.value)


def test_counts_are_checked_against_what_they_count(work):
    weak = work.strands[0]
    assert miscounted(f"{len(work.missing)} of {len(work.assignments)} assignments missing.", work) == []
    assert miscounted(f"{weak.strand}: {weak.missing} of {weak.graded} missing.", work) == []
    assert miscounted(f"{wrong_count(work)} of {len(work.assignments)} assignments missing.", work)


def test_a_scoped_run_cannot_propose_for_another_student(db, work):
    with pytest.raises(ToolError) as e:
        T.propose_study_plan(db, {"proposals": [], "only_student": "S-0000", "only_course": CODE}, **good(work))
    assert "only for S-0000" in str(e.value)


# --- adopting and closing ---------------------------------------------------
def test_approving_adopts_a_plan_with_its_baseline(db, work, clean):
    ctx: dict = {"proposals": []}
    T.propose_study_plan(db, ctx, **good(work))
    raw = ctx["proposals"][0]
    p = Proposal(agent="study", kind="study_plan", summary=raw["summary"], reason=raw["reason"],
                 payload=raw["payload"], evidence=raw["evidence"], status="pending")
    db.add(p)
    db.commit()

    apply_proposal(db, p)
    plan = db.scalar(select(StudyPlan).where(StudyPlan.student_sid == SID, StudyPlan.course_code == CODE))
    assert plan.status == "active" and plan.owner == work.teacher
    assert plan.baseline["pct"] == work.pct and len(plan.catch_up) == len(work.missing)

    # A second plan for the same student and class is refused at every step.
    with pytest.raises(ToolError):
        T.propose_study_plan(db, {"proposals": []}, **good(work))
    dup = Proposal(agent="study", kind="study_plan", summary="x", payload=raw["payload"], status="pending")
    db.add(dup)
    db.commit()
    with pytest.raises(ApplyError):
        apply_proposal(db, dup)
    db.rollback()


def test_api_shows_classes_plans_and_closes_a_plan(client, db, work, clean):
    ctx: dict = {"proposals": []}
    T.propose_study_plan(db, ctx, **good(work))
    raw = ctx["proposals"][0]
    p = Proposal(agent="study", kind="study_plan", summary=raw["summary"], payload=raw["payload"],
                 evidence=raw["evidence"], status="pending")
    db.add(p)
    db.commit()

    out = client.get(f"/api/students/{SID}/study").json()
    row = next(c for c in out["classes"] if c["code"] == CODE)
    assert row["needs_plan"] and row["findings"] and row["drafts_waiting"] == 1
    assert out["drafts"][0]["payload"]["course_code"] == CODE

    assert client.post(f"/api/agents/proposals/{p.id}/approve").status_code == 200
    out = client.get(f"/api/students/{SID}/study").json()
    plan = out["plans"][0]
    assert plan["status"] == "active" and plan["sessions"]
    assert {r["measure"] for r in plan["progress"]} >= {"Class grade", "Assignments missing"}
    assert client.post(f"/api/students/{SID}/classes/{CODE}/study-plan/draft", json={}).status_code == 409

    closed = client.patch(f"/api/study-plans/{plan['id']}", json={"status": "completed", "outcome": "caught up"})
    assert closed.status_code == 200 and closed.json()["status"] == "completed"

    work_out = client.get(f"/api/students/{SID}/classes/{CODE}/work").json()
    assert work_out["assignments"] and work_out["findings"]
    assert client.get(f"/api/students/{SID}/classes/NOPE-000/work").status_code == 404
