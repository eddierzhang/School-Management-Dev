from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.deps import Principal, require
from ..auth.scope import ensure_student, visible_students
from ..db import get_db
from ..schedule import school_schedule, student_schedule
from ..schemas import SchoolScheduleOut, StudentScheduleOut

router = APIRouter(tags=["schedule"])


@router.get("/schedule", response_model=SchoolScheduleOut)
def whole_school(db: Session = Depends(get_db), user: Principal = Depends(require("schedule.read"))) -> SchoolScheduleOut:
    """Every running section by period, with room, teacher and student clashes.

    Student clashes name students, so they are limited to the students the person
    may see.
    """
    s = school_schedule(db)
    allowed = visible_students(db, user) if user.can("students.read") else set()
    if allowed is not None:
        s.student_clashes = [c for c in s.student_clashes if c.sid in allowed]
        s.students_with_clashes = len({c.sid for c in s.student_clashes})
    return SchoolScheduleOut.model_validate(s)


@router.get("/students/{sid}/schedule", response_model=StudentScheduleOut)
def one_student(sid: str, db: Session = Depends(get_db),
                user: Principal = Depends(require("students.read"))) -> StudentScheduleOut:
    """One student's day, period by period, including waitlisted classes and clashes."""
    ensure_student(db, user, sid)
    s = student_schedule(db, sid)
    if s is None:
        raise HTTPException(404, f"No student with ID {sid}")
    return StudentScheduleOut.model_validate(s)
