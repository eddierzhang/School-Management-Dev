from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..schedule import school_schedule, student_schedule
from ..schemas import SchoolScheduleOut, StudentScheduleOut

router = APIRouter(tags=["schedule"])


@router.get("/schedule", response_model=SchoolScheduleOut)
def whole_school(db: Session = Depends(get_db)) -> SchoolScheduleOut:
    """Every running section by period, with room, teacher and student clashes."""
    return SchoolScheduleOut.model_validate(school_schedule(db))


@router.get("/students/{sid}/schedule", response_model=StudentScheduleOut)
def one_student(sid: str, db: Session = Depends(get_db)) -> StudentScheduleOut:
    """One student's day, period by period, including waitlisted classes and clashes."""
    s = student_schedule(db, sid)
    if s is None:
        raise HTTPException(404, f"No student with ID {sid}")
    return StudentScheduleOut.model_validate(s)
