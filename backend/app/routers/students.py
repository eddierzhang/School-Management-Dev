from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import StudentSignal
from ..auth.deps import Principal, require
from ..auth.scope import ensure_student, visible_students
from ..config import get_settings
from ..db import get_db
from ..deps import signals
from ..history import override_out, student_history
from ..models import FlagOverride, Intervention, Student
from ..schemas import InterventionOut, StudentDetail, StudentRow

router = APIRouter(prefix="/students", tags=["students"])
settings = get_settings()

SORTS = {"struggle": lambda s: -s.struggle_index, "excel": lambda s: -s.excel_index,
         "standing": lambda s: s.standing,
         "name": lambda s: s.name, "grade": lambda s: (s.grade, s.name)}


@router.get("", response_model=list[StudentRow])
def list_students(
    band: str | None = Query(None, pattern="^(needs-plan|watch|excelling|steady)$"),
    grade: int | None = Query(None, ge=9, le=12),
    course: str | None = None,
    q: str | None = None,
    sort: str = Query("struggle", pattern="^(struggle|excel|standing|name|grade)$"),
    limit: int = Query(500, ge=1, le=500),
    sigs: dict[str, StudentSignal] = Depends(signals),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("students.read")),
) -> list[StudentRow]:
    allowed = visible_students(db, user)
    rows = [s for s in sigs.values() if allowed is None or s.sid in allowed]
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
            computed_band=s.computed_band, acknowledged=s.acknowledged,
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
    user: Principal = Depends(require("students.read")),
) -> StudentDetail:
    ensure_student(db, user, sid)
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


# ---- history and overrides ----------------------------------------------------------
class OverrideIn(BaseModel):
    kind: str = Field(pattern="^(acknowledge|set-band)$")
    band: str | None = Field(default=None, pattern="^(needs-plan|watch|excelling|steady)$")
    note: str = Field(min_length=10, max_length=2000)
    expires_on: date


MAX_OVERRIDE_DAYS = 90


@router.get("/{sid}/history")
def history(sid: str, db: Session = Depends(get_db), user: Principal = Depends(require("students.read"))) -> dict:
    """The student's indices over the term, with plans and overrides marked on the same dates."""
    ensure_student(db, user, sid)
    out = student_history(db, sid)
    if out is None:
        raise HTTPException(404, f"No student with SID {sid}")
    return out


@router.post("/{sid}/overrides", status_code=201)
def create_override(sid: str, body: OverrideIn, db: Session = Depends(get_db),
                    sigs: dict[str, StudentSignal] = Depends(signals),
                    user: Principal = Depends(require("plans.write"))) -> dict:
    """Overrule the index for one student, with a reason and an end date.

    A new override replaces the student's current one. It never changes the
    computed indices, which stay visible beside it.
    """
    ensure_student(db, user, sid)
    st = db.scalar(select(Student).where(Student.sid == sid))
    sig = sigs.get(sid)
    if st is None or sig is None:
        raise HTTPException(404, f"No student with SID {sid}")
    today = settings.today
    if not today < body.expires_on <= today + timedelta(days=MAX_OVERRIDE_DAYS):
        raise HTTPException(422, f"An override must end within {MAX_OVERRIDE_DAYS} days, so it gets looked at again.")
    if body.kind == "set-band":
        if not body.band:
            raise HTTPException(422, "Say which band to set.")
        if body.band == sig.computed_band:
            raise HTTPException(422, f"The index already reads {body.band}.")
    if body.kind == "acknowledge" and sig.computed_band not in ("needs-plan", "watch"):
        raise HTTPException(422, "Only a flagged student (needs a plan, or watch) can be marked as known and in hand.")

    now = datetime.utcnow()
    for old in db.scalars(select(FlagOverride).where(FlagOverride.student_id == st.id,
                                                     FlagOverride.revoked_at.is_(None))).all():
        old.revoked_at, old.revoked_by = now, user.email
    o = FlagOverride(student_id=st.id, kind=body.kind, band=body.band if body.kind == "set-band" else None,
                     computed_band=sig.computed_band, note=body.note.strip(), expires_on=body.expires_on,
                     created_by=user.email, created_at=now)
    db.add(o)
    db.commit()
    return override_out(o)


@router.delete("/{sid}/overrides/{override_id}")
def revoke_override(sid: str, override_id: int, db: Session = Depends(get_db),
                    user: Principal = Depends(require("plans.write"))) -> dict:
    ensure_student(db, user, sid)
    o = db.get(FlagOverride, override_id)
    if o is None or o.student_id != db.scalar(select(Student.id).where(Student.sid == sid)):
        raise HTTPException(404, f"No override {override_id} for {sid}")
    if o.revoked_at is None:
        o.revoked_at, o.revoked_by = datetime.utcnow(), user.email
        db.commit()
    return override_out(o)
