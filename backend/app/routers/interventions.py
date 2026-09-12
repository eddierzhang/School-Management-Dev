from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Course, Intervention, Student
from ..schemas import InterventionCreate, InterventionOut, InterventionUpdate

router = APIRouter(prefix="/interventions", tags=["interventions"])
settings = get_settings()


def _out(iv: Intervention) -> InterventionOut:
    return InterventionOut(
        id=iv.id, student_sid=iv.student.sid, student_name=iv.student.name,
        course_code=iv.course.code if iv.course else None, kind=iv.kind, title=iv.title,
        rationale=iv.rationale, owner=iv.owner, status=iv.status,
        opened_on=iv.opened_on, review_on=iv.review_on, outcome=iv.outcome,
    )


@router.get("", response_model=list[InterventionOut])
def list_interventions(status: str | None = None, db: Session = Depends(get_db)) -> list[InterventionOut]:
    stmt = select(Intervention).order_by(Intervention.opened_on.desc(), Intervention.id.desc())
    if status:
        stmt = stmt.where(Intervention.status == status)
    return [_out(iv) for iv in db.scalars(stmt).all()]


@router.post("", response_model=InterventionOut, status_code=201)
def create_intervention(body: InterventionCreate, db: Session = Depends(get_db)) -> InterventionOut:
    st = db.scalar(select(Student).where(Student.sid == body.student_sid))
    if st is None:
        raise HTTPException(404, f"No student with SID {body.student_sid}")
    course = None
    if body.course_code:
        course = db.scalar(select(Course).where(Course.code == body.course_code))
        if course is None:
            raise HTTPException(404, f"No course with code {body.course_code}")

    dupe = db.scalar(
        select(Intervention).where(
            Intervention.student_id == st.id, Intervention.kind == body.kind,
            Intervention.course_id == (course.id if course else None),
            Intervention.status == "active")
    )
    if dupe is not None:
        raise HTTPException(409, f"{st.name} already has an active {body.kind} plan for this course")

    iv = Intervention(
        student_id=st.id, course_id=course.id if course else None, kind=body.kind,
        title=body.title, rationale=body.rationale, owner=body.owner,
        status="active", opened_on=settings.today, review_on=body.review_on,
    )
    db.add(iv)
    db.commit()
    db.refresh(iv)
    return _out(iv)


@router.patch("/{iv_id}", response_model=InterventionOut)
def update_intervention(iv_id: int, body: InterventionUpdate,
                        db: Session = Depends(get_db)) -> InterventionOut:
    iv = db.get(Intervention, iv_id)
    if iv is None:
        raise HTTPException(404, f"No intervention {iv_id}")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(iv, field, value)
    db.commit()
    db.refresh(iv)
    return _out(iv)


@router.delete("/{iv_id}", status_code=204)
def delete_intervention(iv_id: int, db: Session = Depends(get_db)) -> None:
    iv = db.get(Intervention, iv_id)
    if iv is None:
        raise HTTPException(404, f"No intervention {iv_id}")
    db.delete(iv)
    db.commit()
