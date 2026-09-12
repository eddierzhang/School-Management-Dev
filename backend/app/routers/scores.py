"""Recording a grade. The engine has no cached risk column, so a score entered
here changes every signal that depends on it on the next read — no rebuild step.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Assessment, Course, Score, Student
from ..schemas import ScoreIn

router = APIRouter(tags=["scores"])
settings = get_settings()


@router.get("/courses/{code}/assessments")
def course_assessments(code: str, db: Session = Depends(get_db)) -> list[dict]:
    course = db.scalar(select(Course).where(Course.code == code))
    if course is None:
        raise HTTPException(404, f"No course with code {code}")
    rows = db.scalars(
        select(Assessment).where(Assessment.course_id == course.id).order_by(Assessment.due_on)
    ).all()
    return [{
        "id": a.id, "title": a.title, "kind": a.kind, "skill": a.skill,
        "max_points": a.max_points, "weight": a.weight,
        "assigned_on": a.assigned_on.isoformat(), "due_on": a.due_on.isoformat(),
        "graded": a.due_on <= settings.today,
    } for a in rows]


@router.put("/scores", status_code=200)
def upsert_score(body: ScoreIn, db: Session = Depends(get_db)) -> dict:
    a = db.get(Assessment, body.assessment_id)
    if a is None:
        raise HTTPException(404, f"No assessment {body.assessment_id}")
    st = db.scalar(select(Student).where(Student.sid == body.student_sid))
    if st is None:
        raise HTTPException(404, f"No student with SID {body.student_sid}")
    if body.points is not None and not (0 <= body.points <= a.max_points):
        raise HTTPException(422, f"Points must be between 0 and {a.max_points:g} for this assessment")

    sc = db.scalar(select(Score).where(Score.assessment_id == a.id, Score.student_id == st.id))
    if sc is None:
        sc = Score(assessment_id=a.id, student_id=st.id)
        db.add(sc)
    sc.points = body.points
    sc.late = body.late
    sc.recorded_on = settings.today
    db.commit()
    return {"assessment_id": a.id, "student_sid": st.sid, "points": sc.points,
            "late": sc.late, "pct": round(100 * sc.points / a.max_points, 1) if sc.points is not None else None}
