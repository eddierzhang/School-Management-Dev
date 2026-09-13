"""Study plans: read a student's work in a class, have the agent draft a plan, adopt or close it.

Drafting is an ordinary agent run scoped to one student in one class and opened on
that class-work reading, so a draft is a pending proposal like any other, with its
transcript kept. Nothing becomes a plan until a person approves it.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import ollama
from ..analytics import build_signals
from ..auth.deps import Principal, require
from ..auth.scope import ensure_course, ensure_student
from ..config import get_settings
from ..db import get_db
from ..jobs import enqueue
from ..models import AgentRun, Proposal, Student, StudyPlan
from ..schemas import (ClassPlanPatch, DraftRequest, DraftRunOut, PlanDraftOut, StudentStudyOut,
                       StudyClassRow, StudyPlanOut)
from ..study_plans import active_plan, class_work, progress

router = APIRouter(tags=["study plans"])
settings = get_settings()
AGENT = "study"


def _subject(sid: str, code: str) -> str:
    return f"study:{sid}:{code}"


def _run_out(r: AgentRun | None) -> DraftRunOut | None:
    if r is None:
        return None
    return DraftRunOut(id=r.id, status=r.status, summary=r.summary or "", error=r.error,
                       steps_used=r.steps_used, duration_ms=r.duration_ms,
                       proposals=len(r.proposals), started_at=r.started_at)


def _plan_out(db: Session, plan: StudyPlan) -> StudyPlanOut:
    return StudyPlanOut(
        id=plan.id, student_sid=plan.student_sid, course_code=plan.course_code, title=plan.title,
        diagnosis=plan.diagnosis, focus_strands=plan.focus_strands or [], sessions=plan.sessions or [],
        catch_up=plan.catch_up or [], goal=plan.goal, owner=plan.owner, status=plan.status,
        outcome=plan.outcome, opened_on=plan.opened_on, review_on=plan.review_on, closed_on=plan.closed_on,
        run_id=plan.run_id, progress=progress(plan, class_work(db, plan.student_sid, plan.course_code)))


def _pending(db: Session, sid: str) -> list[Proposal]:
    return [p for p in db.scalars(select(Proposal).where(Proposal.kind == "study_plan", Proposal.status == "pending")
                                  .order_by(Proposal.id.desc())).all()
            if (p.payload or {}).get("student_sid") == sid]


@router.get("/students/{sid}/study", response_model=StudentStudyOut)
def student_study(sid: str, db: Session = Depends(get_db),
                  user: Principal = Depends(require("students.read"))) -> StudentStudyOut:
    """Every class the student takes with what its work shows, plus their plans and drafts."""
    ensure_student(db, user, sid)
    sigs = build_signals(db)
    sig = sigs.get(sid)
    if sig is None:
        raise HTTPException(404, f"No student with SID {sid}")
    drafts = _pending(db, sid)
    classes = []
    for c in sig.courses:
        w = class_work(db, sid, c.course_code, sigs)
        if w is None:
            continue
        plan = active_plan(db, sid, c.course_code)
        latest = db.scalar(select(AgentRun).where(AgentRun.subject == _subject(sid, c.course_code))
                           .order_by(AgentRun.id.desc()).limit(1))
        classes.append(StudyClassRow(
            code=w.course_code, title=w.course_title, teacher=w.teacher, pct=w.pct, class_pct=w.class_pct,
            needs_plan=w.needs_plan, findings=[f.text for f in w.findings],
            active_plan_id=plan.id if plan else None,
            drafts_waiting=sum(1 for d in drafts if d.payload.get("course_code") == c.course_code),
            latest_run=_run_out(latest)))
    classes.sort(key=lambda r: (not r.needs_plan, r.pct))
    plans = db.scalars(select(StudyPlan).where(StudyPlan.student_sid == sid).order_by(StudyPlan.id.desc())).all()
    return StudentStudyOut(
        sid=sid, classes=classes, plans=[_plan_out(db, p) for p in plans],
        drafts=[PlanDraftOut(id=p.id, run_id=p.run_id, summary=p.summary, payload=p.payload,
                             created_at=p.created_at) for p in drafts])


@router.get("/students/{sid}/classes/{code}/work")
def student_class_work(sid: str, code: str, db: Session = Depends(get_db),
                       user: Principal = Depends(require("students.read"))) -> dict:
    """The full reading the agent plans from: every assignment, strand, kind of work and finding."""
    ensure_student(db, user, sid)
    w = class_work(db, sid, code)
    if w is None:
        raise HTTPException(404, f"{sid} has no graded work in {code}")
    return w.as_dict()


@router.post("/students/{sid}/classes/{code}/study-plan/draft", response_model=DraftRunOut, status_code=202)
def draft_study_plan(sid: str, code: str, body: DraftRequest,
                     db: Session = Depends(get_db),
                     user: Principal = Depends(require("drafts.request"))) -> DraftRunOut:
    """Start the study plan agent on one student in one class. Runs take a minute or three.

    A teacher may ask for a draft only in their own class; approving it still needs plans.write.
    """
    ensure_student(db, user, sid)
    ensure_course(db, user, code)
    st = db.scalar(select(Student).where(Student.sid == sid))
    w = class_work(db, sid, code) if st else None
    if w is None:
        raise HTTPException(404, f"{sid} has no graded work in {code}")
    if active_plan(db, sid, code):
        raise HTTPException(409, f"{st.name} already has an active study plan for {code}. Close it first.")
    if any(p.payload.get("course_code") == code for p in _pending(db, sid)):
        raise HTTPException(409, f"A draft study plan for {code} is already waiting for approval.")
    if db.scalar(select(AgentRun).where(AgentRun.subject == _subject(sid, code),
                                        AgentRun.status.in_(["queued", "running"]))):
        raise HTTPException(409, f"A study plan for {st.name} in {code} is already being drafted.")
    h = ollama.health()
    if not h["reachable"]:
        raise HTTPException(503, h["error"] or "Ollama is not reachable.")
    if not h.get("can_run_agents"):
        raise HTTPException(503, f"{settings.ollama_model} cannot call tools, so it cannot draft a plan.")

    task = (f"Draft one detailed study plan for student {sid} in {w.course_title} ({code}), taught by "
            f"{w.teacher}. Their class work is above. Work out what exactly they struggle on from the "
            f"findings and call propose_study_plan once for {sid} in {code}.")
    if body.note and body.note.strip():
        task += f"\nThe person asking adds: {body.note.strip()}"
    run = AgentRun(agent=AGENT, model=settings.ollama_model, prompt=task, status="queued", transcript=[],
                   subject=_subject(sid, code), started_at=datetime.utcnow())
    db.add(run)
    db.flush()
    enqueue(db, "agent_run", {"run_id": run.id, "agent": AGENT, "task": task,
                              "opening": ["get_student_class_work", {"sid": sid, "course_code": code}],
                              "scope": {"only_student": sid, "only_course": code}}, max_attempts=2, commit=False)
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.patch("/study-plans/{plan_id}", response_model=StudyPlanOut)
def close_study_plan(plan_id: int, body: ClassPlanPatch, db: Session = Depends(get_db),
                     _: Principal = Depends(require("plans.write"))) -> StudyPlanOut:
    plan = db.get(StudyPlan, plan_id)
    if plan is None:
        raise HTTPException(404, f"No study plan {plan_id}")
    if plan.status != "active":
        raise HTTPException(409, f"This study plan is already {plan.status}.")
    plan.status = body.status
    plan.outcome = (body.outcome or "").strip() or None
    plan.closed_on = settings.today
    db.commit()
    return _plan_out(db, plan)
