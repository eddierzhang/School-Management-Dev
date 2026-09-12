"""Class improvement plans: read a class, have the agent draft a plan, adopt or close it.

Drafting is an ordinary agent run — scoped to one class, opened on that class's
performance — so a draft is a pending proposal like any other, with its whole
transcript kept, and nothing becomes a plan until a person approves it.
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import ollama
from ..ai.runner import run_in_background
from ..class_plans import active_plan, all_performance, performance, progress
from ..config import get_settings
from ..db import get_db
from ..models import AgentRun, ClassPlan, Proposal
from ..schemas import (ClassImprovementOut, ClassNeedRow, ClassPlanOut, ClassPlanPatch, DraftRequest,
                       DraftRunOut, PlanDraftOut)

router = APIRouter(tags=["improvement"])
settings = get_settings()
AGENT = "classes"


def _subject(code: str) -> str:
    return f"course:{code}"


def _plan_out(plan: ClassPlan, now) -> ClassPlanOut:
    return ClassPlanOut(
        id=plan.id, course_code=plan.course_code, title=plan.title, diagnosis=plan.diagnosis,
        focus_strands=plan.focus_strands or [], actions=plan.actions or [], goal=plan.goal, owner=plan.owner,
        status=plan.status, outcome=plan.outcome, opened_on=plan.opened_on, review_on=plan.review_on,
        closed_on=plan.closed_on, run_id=plan.run_id, progress=progress(plan, now))


def _run_out(r: AgentRun | None) -> DraftRunOut | None:
    if r is None:
        return None
    return DraftRunOut(id=r.id, status=r.status, summary=r.summary or "", error=r.error,
                       steps_used=r.steps_used, duration_ms=r.duration_ms,
                       proposals=len(r.proposals), started_at=r.started_at)


@router.get("/improvement", response_model=list[ClassNeedRow])
def every_class(db: Session = Depends(get_db)) -> list[ClassNeedRow]:
    """Every class, the ones that most need a plan first, with what they already have."""
    drafts = [p for p in db.scalars(select(Proposal).where(Proposal.kind == "class_plan",
                                                           Proposal.status == "pending")).all()]
    rows = []
    for p in all_performance(db):
        plan = active_plan(db, p.code)
        rows.append(ClassNeedRow(
            code=p.code, title=p.title, teacher=p.teacher, status=p.status, mean=p.mean, issues=p.issues,
            active_plan=plan.title if plan else None,
            drafts_waiting=sum(1 for d in drafts if (d.payload or {}).get("course_code") == p.code)))
    return rows


@router.get("/courses/{code}/improvement", response_model=ClassImprovementOut)
def class_improvement(code: str, db: Session = Depends(get_db)) -> ClassImprovementOut:
    now = performance(db, code)
    if now is None:
        raise HTTPException(404, f"No course with code {code}")
    plans = db.scalars(select(ClassPlan).where(ClassPlan.course_code == code)
                       .order_by(ClassPlan.id.desc())).all()
    drafts = [p for p in db.scalars(select(Proposal).where(Proposal.kind == "class_plan")
                                    .order_by(Proposal.id.desc())).all()
              if (p.payload or {}).get("course_code") == code and p.status == "pending"]
    latest = db.scalar(select(AgentRun).where(AgentRun.subject == _subject(code))
                       .order_by(AgentRun.id.desc()).limit(1))
    return ClassImprovementOut(
        performance=now.as_dict(),
        plans=[_plan_out(p, now) for p in plans],
        drafts=[PlanDraftOut(id=p.id, run_id=p.run_id, summary=p.summary, payload=p.payload,
                             created_at=p.created_at) for p in drafts],
        latest_run=_run_out(latest),
    )


@router.post("/courses/{code}/improvement/draft", response_model=DraftRunOut, status_code=202)
def draft_plan(code: str, body: DraftRequest, background: BackgroundTasks,
               db: Session = Depends(get_db)) -> DraftRunOut:
    """Start the class improvement agent on this one class. Runs take a minute or three."""
    p = performance(db, code)
    if p is None:
        raise HTTPException(404, f"No course with code {code}")
    if p.status == "no-data":
        raise HTTPException(409, f"{code} has no graded work yet, so there is nothing to plan from.")
    if active_plan(db, code):
        raise HTTPException(409, f"{code} already has an active plan. Complete or retire it first.")
    if db.scalar(select(AgentRun).where(AgentRun.subject == _subject(code), AgentRun.status == "running")):
        raise HTTPException(409, f"A plan for {code} is already being drafted.")
    h = ollama.health()
    if not h["reachable"]:
        raise HTTPException(503, h["error"] or "Ollama is not reachable.")
    if not h.get("can_run_agents"):
        raise HTTPException(503, f"{settings.ollama_model} cannot call tools, so it cannot draft a plan.")

    task = (f"Draft one improvement plan for {p.title} ({code}), taught by {p.teacher}. Its performance "
            f"is above. Find the main cause and call propose_class_plan once for {code}.")
    if body.note and body.note.strip():
        task += f"\nThe person asking adds: {body.note.strip()}"
    run = AgentRun(agent=AGENT, model=settings.ollama_model, prompt=task, status="running", transcript=[],
                   subject=_subject(code), started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    background.add_task(run_in_background, run.id, AGENT, task,
                        opening=("get_class_performance", {"course_code": code}),
                        scope={"only_course": code})
    return _run_out(run)


@router.patch("/improvement-plans/{plan_id}", response_model=ClassPlanOut)
def close_plan(plan_id: int, body: ClassPlanPatch, db: Session = Depends(get_db)) -> ClassPlanOut:
    plan = db.get(ClassPlan, plan_id)
    if plan is None:
        raise HTTPException(404, f"No improvement plan {plan_id}")
    if plan.status != "active":
        raise HTTPException(409, f"This plan is already {plan.status}.")
    plan.status = body.status
    plan.outcome = (body.outcome or "").strip() or None
    plan.closed_on = settings.today
    db.commit()
    return _plan_out(plan, performance(db, plan.course_code))
