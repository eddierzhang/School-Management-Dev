import statistics

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analytics import StudentSignal, skill_gaps
from ..config import get_settings
from ..db import get_db
from ..deps import signals
from ..models import Assessment, Course, Intervention, Student
from ..schemas import BandCount, SkillGapOut, Summary

router = APIRouter(tags=["meta"])
settings = get_settings()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "term": settings.term, "today": settings.today.isoformat()}


@router.get("/summary", response_model=Summary)
def summary(db: Session = Depends(get_db), sigs: dict[str, StudentSignal] = Depends(signals)) -> Summary:
    counts: dict[str, int] = {"needs-plan": 0, "watch": 0, "excelling": 0, "steady": 0}
    for s in sigs.values():
        counts[s.band] = counts.get(s.band, 0) + 1

    open_iv = db.scalar(select(func.count()).select_from(Intervention).where(Intervention.status == "active")) or 0
    with_plan = {
        iv.student.sid
        for iv in db.scalars(select(Intervention).where(Intervention.status == "active")).all()
    }
    unaddressed = sum(1 for s in sigs.values() if s.band == "needs-plan" and s.sid not in with_plan)
    graded = db.scalar(
        select(func.count()).select_from(Assessment).where(Assessment.due_on <= settings.today)
    ) or 0
    rates = [s.absence_rate for s in sigs.values() if s.days_counted]

    return Summary(
        school=settings.school_name, term=settings.term, today=settings.today,
        students=db.scalar(select(func.count()).select_from(Student)) or 0,
        courses=db.scalar(select(func.count()).select_from(Course)) or 0,
        graded_assessments=graded,
        bands=[BandCount(band=b, count=c) for b, c in counts.items()],
        needs_plan=counts["needs-plan"], watch=counts["watch"],
        excelling=counts["excelling"], steady=counts["steady"],
        open_interventions=open_iv, unaddressed=unaddressed,
        mean_attendance=round(1 - statistics.fmean(rates), 4) if rates else 1.0,
        top_skill_gaps=[SkillGapOut.model_validate(g) for g in skill_gaps(db)[:6]],
    )
