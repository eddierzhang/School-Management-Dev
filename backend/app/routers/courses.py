import statistics

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import StudentSignal, course_distribution, skill_gaps
from ..config import get_settings
from ..db import get_db
from ..deps import signals
from ..models import Course, Enrollment
from ..schemas import (CourseDetail, CourseRow, CourseStudentRow, DistributionBucket, SkillGapOut)

router = APIRouter(prefix="/courses", tags=["courses"])
settings = get_settings()


def _course_row(c: Course, enrolled: int, sigs: dict[str, StudentSignal],
                gaps: list) -> CourseRow:
    pcts = [cs.pct for s in sigs.values() for cs in s.courses if cs.course_code == c.code]
    mine = [g for g in gaps if g.course_code == c.code]
    weakest = min(mine, key=lambda g: g.class_mean) if mine else None
    return CourseRow(
        code=c.code, title=c.title, dept=c.dept, teacher=c.teacher, period=c.period,
        room=c.room, enrolled=enrolled, capacity=c.capacity,
        class_mean=round(statistics.fmean(pcts), 1) if pcts else None,
        below_support=sum(1 for p in pcts if p < settings.support_threshold),
        excelling=sum(1 for s in sigs.values() for cs in s.courses
                      if cs.course_code == c.code and cs.excel_index >= 70),
        weakest_skill=weakest.skill if weakest else None,
        weakest_skill_mean=weakest.class_mean if weakest else None,
    )


@router.get("", response_model=list[CourseRow])
def list_courses(db: Session = Depends(get_db),
                 sigs: dict[str, StudentSignal] = Depends(signals)) -> list[CourseRow]:
    gaps = skill_gaps(db)
    counts: dict[int, int] = {}
    for e in db.scalars(select(Enrollment).where(Enrollment.status == "enrolled")).all():
        counts[e.course_id] = counts.get(e.course_id, 0) + 1
    rows = [_course_row(c, counts.get(c.id, 0), sigs, gaps)
            for c in db.scalars(select(Course).order_by(Course.code)).all()]
    rows.sort(key=lambda r: (r.class_mean if r.class_mean is not None else 999))
    return rows


@router.get("/{code}", response_model=CourseDetail)
def course_detail(code: str, db: Session = Depends(get_db),
                  sigs: dict[str, StudentSignal] = Depends(signals)) -> CourseDetail:
    c = db.scalar(select(Course).where(Course.code == code))
    if c is None:
        raise HTTPException(404, f"No course with code {code}")
    enrolled = len(db.scalars(
        select(Enrollment).where(Enrollment.course_id == c.id, Enrollment.status == "enrolled")
    ).all())
    gaps = skill_gaps(db)

    students = []
    for s in sigs.values():
        for cs in s.courses:
            if cs.course_code != code:
                continue
            students.append(CourseStudentRow(
                sid=s.sid, name=s.name, grade=s.grade, pct=cs.pct, delta=cs.delta,
                missing=cs.missing, graded_items=cs.graded_items,
                struggle_index=cs.struggle_index, excel_index=cs.excel_index))
    students.sort(key=lambda r: r.pct)

    return CourseDetail(
        course=_course_row(c, enrolled, sigs, gaps),
        students=students,
        skills=[SkillGapOut.model_validate(g) for g in gaps if g.course_code == code],
        distribution=[DistributionBucket(**b) for b in course_distribution(sigs, code)],
    )
