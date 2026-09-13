"""A student's indices over time, and what was done about them.

The indices are recomputed from the gradebook on every read, which keeps them
honest but forgets yesterday. A snapshot records what they read on one day, so a
counselor can see whether a plan moved anything: the struggle index before the
tutoring started, and after.

    take_snapshots(db)            today's reading for every student (the worker runs this daily)
    backfill(db, start, end)      one reading a week across a past stretch, from the gradebook as it was
    student_history(db, sid)      the readings, plus plans opened and closed and overrides, in date order
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .analytics import build_signals
from .config import get_settings
from .models import FlagOverride, Intervention, Student, StudentSnapshot, StudyPlan

settings = get_settings()


def take_snapshots(db: Session, on: date | None = None) -> int:
    """Record every student's reading for `on` (default today), replacing any already taken that day.

    `build_signals(on=...)` only counts work due and attendance recorded by that
    date, so a past date reads the record as it stood then, apart from scores
    entered late.
    """
    on = on or settings.today
    sigs = build_signals(db, on)
    ids = dict(db.execute(select(Student.sid, Student.id)).all())
    db.execute(delete(StudentSnapshot).where(StudentSnapshot.taken_on == on))
    for sig in sigs.values():
        db.add(StudentSnapshot(
            student_id=ids[sig.sid], taken_on=on, struggle_index=sig.struggle_index, excel_index=sig.excel_index,
            band=sig.computed_band, absence_rate=sig.absence_rate, open_interventions=sig.open_interventions,
            courses=[{"code": c.course_code, "pct": c.pct, "struggle": c.struggle_index, "excel": c.excel_index}
                     for c in sig.courses],
            reasons=[r.label for r in sig.reasons]))
    db.commit()
    return len(sigs)


def backfill(db: Session, start: date, end: date | None = None, every_days: int = 7) -> list[date]:
    end = end or settings.today
    taken, day = [], start
    while day <= end:
        take_snapshots(db, day)
        taken.append(day)
        day += timedelta(days=every_days)
    if taken and taken[-1] != end:
        take_snapshots(db, end)
        taken.append(end)
    return taken


def student_history(db: Session, sid: str) -> dict | None:
    st = db.scalar(select(Student).where(Student.sid == sid))
    if st is None:
        return None
    snaps = db.scalars(select(StudentSnapshot).where(StudentSnapshot.student_id == st.id)
                       .order_by(StudentSnapshot.taken_on)).all()
    events: list[dict] = []
    for iv in db.scalars(select(Intervention).where(Intervention.student_id == st.id)).all():
        events.append({"on": iv.opened_on.isoformat(), "kind": "plan-opened", "label": iv.title,
                       "detail": f"{iv.kind} · {iv.owner}"})
        if iv.status != "active" and iv.review_on:
            # Interventions record no closing date; the review date is the nearest honest marker.
            events.append({"on": iv.review_on.isoformat(), "kind": f"plan-{iv.status}", "label": iv.title,
                           "detail": iv.outcome or ""})
    for p in db.scalars(select(StudyPlan).where(StudyPlan.student_sid == sid)).all():
        events.append({"on": p.opened_on.isoformat(), "kind": "study-plan-opened", "label": p.title,
                       "detail": p.course_code})
        if p.closed_on:
            events.append({"on": p.closed_on.isoformat(), "kind": f"study-plan-{p.status}", "label": p.title,
                           "detail": p.outcome or ""})
    overrides = db.scalars(select(FlagOverride).where(FlagOverride.student_id == st.id)
                           .order_by(FlagOverride.id.desc())).all()
    for o in overrides:
        events.append({"on": o.created_at.date().isoformat() if o.created_at else settings.today.isoformat(),
                       "kind": "override", "label": _override_label(o), "detail": o.note})
    events.sort(key=lambda e: e["on"])

    return {
        "sid": sid,
        "snapshots": [{"on": s.taken_on.isoformat(), "struggle_index": s.struggle_index, "excel_index": s.excel_index,
                       "band": s.band, "absence_rate": s.absence_rate, "open_interventions": s.open_interventions,
                       "courses": s.courses or [], "reasons": s.reasons or []} for s in snaps],
        "events": events,
        "overrides": [override_out(o) for o in overrides],
    }


def _override_label(o: FlagOverride) -> str:
    return ("Marked as known and in hand" if o.kind == "acknowledge"
            else f"Band set to {o.band} (index said {o.computed_band})")


def override_out(o: FlagOverride) -> dict:
    active = o.revoked_at is None and o.expires_on >= settings.today
    return {"id": o.id, "kind": o.kind, "band": o.band, "computed_band": o.computed_band, "note": o.note,
            "expires_on": o.expires_on.isoformat(), "created_by": o.created_by,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "revoked_at": o.revoked_at.isoformat() if o.revoked_at else None, "revoked_by": o.revoked_by,
            "active": active, "label": _override_label(o)}
