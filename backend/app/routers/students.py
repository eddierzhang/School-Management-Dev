from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import StudentSignal
from ..db import get_db
from ..deps import signals
from ..models import Intervention, Student
from ..schemas import InterventionOut, StudentDetail, StudentRow

router = APIRouter(prefix="/students", tags=["students"])

SORTS = {"struggle": lambda s: -s.struggle_index, "excel": lambda s: -s.excel_index,
         "standing": lambda s: s.standing,
         "name": lambda s: s.name, "grade": lambda s: (s.grade, s.name)}


@router.get("", response_model=list[StudentRow])
def list_students(
    band: str | None = Query(None, pattern="^(needs-plan|watch|excelling|steady)$"),
    grade: int | None = Query(None, ge=6, le=8),
    course: str | None = None,
    q: str | None = None,
    sort: str = Query("struggle", pattern="^(struggle|excel|standing|name|grade)$"),
    limit: int = Query(500, ge=1, le=500),
    sigs: dict[str, StudentSignal] = Depends(signals),
) -> list[StudentRow]:
    rows = list(sigs.values())
    if band:
        rows = [s for s in rows if s.band == band]
    if grade:
        rows = [s for s in rows if s.grade == grade]
    if course:
        rows = [s for s in rows if any(c.course_code == course for c in s.courses)]
    if q:
        needle = q.strip().lower()
        rows = [s for s in rows if needle in s.name.lower() or needle in s.sid.lower()
                or needle in s.homeroom.lower()]
    rows.sort(key=SORTS[sort])

    out = []
    for s in rows[:limit]:
        worst = s.courses[0] if s.courses else None
        best = max(s.courses, key=lambda c: (c.excel_index, c.pct), default=None)
        concerns = [r for r in s.reasons if r.kind == "concern"]
        strengths = [r for r in s.reasons if r.kind == "strength"]
        head = concerns[0] if concerns else (strengths[0] if strengths else None)
        out.append(StudentRow(
            sid=s.sid, name=s.name, grade=s.grade, homeroom=s.homeroom,
            struggle_index=s.struggle_index, excel_index=s.excel_index,
            standing=s.standing, mixed=s.mixed, band=s.band,
            absence_rate=s.absence_rate, open_interventions=s.open_interventions,
            top_reason=head.label if head else None,
            course_count=len(s.courses),
            lowest_course=worst.course_code if worst else None,
            lowest_pct=min((c.pct for c in s.courses), default=None),
            strongest_course=best.course_code if best else None,
            strongest_pct=best.pct if best else None,
        ))
    return out


@router.get("/{sid}", response_model=StudentDetail)
def student_detail(
    sid: str, db: Session = Depends(get_db), sigs: dict[str, StudentSignal] = Depends(signals),
) -> StudentDetail:
    sig = sigs.get(sid)
    if sig is None:
        raise HTTPException(404, f"No student with SID {sid}")
    st = db.scalar(select(Student).where(Student.sid == sid))
    ivs = db.scalars(
        select(Intervention).where(Intervention.student_id == st.id).order_by(Intervention.opened_on.desc())
    ).all()
    detail = StudentDetail.model_validate(sig)
    detail.guardian_name = st.guardian_name
    detail.guardian_email = st.guardian_email
    detail.interventions = [
        InterventionOut(
            id=iv.id, student_sid=st.sid, student_name=st.name,
            course_code=iv.course.code if iv.course else None, kind=iv.kind, title=iv.title,
            rationale=iv.rationale, owner=iv.owner, status=iv.status,
            opened_on=iv.opened_on, review_on=iv.review_on, outcome=iv.outcome,
        ) for iv in ivs
    ]
    return detail
