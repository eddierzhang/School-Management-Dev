import statistics

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..ai import ollama
from ..analytics import StudentSignal, skill_gaps
from ..auth.deps import Principal, require
from ..auth.scope import visible_courses, visible_students
from ..config import get_settings
from ..db import SessionLocal, engine, get_db, schema_status
from ..jobs import queue_status
from ..deps import signals
from ..models import Assessment, Course, Intervention
from ..schemas import BandCount, SkillGapOut, Summary

router = APIRouter(tags=["meta"])
settings = get_settings()


@router.get("/health")
def health() -> dict:
    """Liveness: the process is up and answering. Touches nothing else."""
    return {"status": "ok", "term": settings.term, "today": settings.today.isoformat()}


@router.get("/ready")
def ready(response: Response) -> dict:
    """Readiness: the database answers and its schema is the one this code expects.

    The local model is reported but never makes the app unready: everything except
    the AI features works without it.
    """
    checks: dict[str, dict] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as e:
        checks["database"] = {"ok": False, "error": type(e).__name__}
    if checks["database"]["ok"]:
        s = schema_status()
        checks["schema"] = {"ok": s["up_to_date"], "current": s["current"], "head": s["head"]}
    else:
        checks["schema"] = {"ok": False, "error": "database unreachable"}
    if checks["schema"]["ok"]:
        # Reported, not required: without a worker the app still serves everything but
        # agent runs, document reads and history snapshots, which wait in the queue.
        with SessionLocal() as db:
            q = queue_status(db)
        checks["worker"] = {"ok": q["worker_alive"], "required": False, **q}
    try:
        installed = settings.ollama_model in ollama.installed_models()
        checks["model"] = {"ok": installed, "required": False, "model": settings.ollama_model,
                           **({} if installed else {"error": "model not installed"})}
    except ollama.OllamaError:
        checks["model"] = {"ok": False, "required": False, "model": settings.ollama_model,
                           "error": "Ollama unreachable"}

    ok = all(c["ok"] for c in checks.values() if c.get("required", True))
    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "not ready", "checks": checks}


@router.get("/summary", response_model=Summary)
def summary(db: Session = Depends(get_db), sigs: dict[str, StudentSignal] = Depends(signals),
            user: Principal = Depends(require("students.read"))) -> Summary:
    """The headline numbers, over the students and classes this person may see: a
    teacher's figures are their own sections', so they agree with the lists beside them."""
    seen, seen_courses = visible_students(db, user), visible_courses(db, user)
    sigs = {sid: s for sid, s in sigs.items() if seen is None or sid in seen}
    counts: dict[str, int] = {"needs-plan": 0, "watch": 0, "excelling": 0, "steady": 0}
    for s in sigs.values():
        counts[s.band] = counts.get(s.band, 0) + 1

    active = [iv for iv in db.scalars(select(Intervention).where(Intervention.status == "active")).all()
              if iv.student.sid in sigs]
    with_plan = {iv.student.sid for iv in active}
    unaddressed = sum(1 for s in sigs.values()
                      if s.band == "needs-plan" and s.sid not in with_plan and not s.acknowledged)
    graded_q = select(func.count()).select_from(Assessment).join(Course, Course.id == Assessment.course_id) \
        .where(Assessment.due_on <= settings.today)
    courses_q = select(func.count()).select_from(Course)
    if seen_courses is not None:
        graded_q = graded_q.where(Course.code.in_(seen_courses))
        courses_q = courses_q.where(Course.code.in_(seen_courses))
    rates = [s.absence_rate for s in sigs.values() if s.days_counted]

    return Summary(
        school=settings.school_name, term=settings.term, today=settings.today,
        students=len(sigs),
        courses=db.scalar(courses_q) or 0,
        graded_assessments=db.scalar(graded_q) or 0,
        bands=[BandCount(band=b, count=c) for b, c in counts.items()],
        needs_plan=counts["needs-plan"], watch=counts["watch"],
        excelling=counts["excelling"], steady=counts["steady"],
        open_interventions=len(active), unaddressed=unaddressed,
        mean_attendance=round(1 - statistics.fmean(rates), 4) if rates else 1.0,
        top_skill_gaps=[SkillGapOut.model_validate(g) for g in skill_gaps(db)
                        if seen_courses is None or g.course_code in seen_courses][:6],
    )
