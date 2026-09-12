import statistics

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import StudentSignal, course_distribution, skill_gaps
from ..config import get_settings
from ..db import get_db
from ..demand import BANDS, FORMULA, class_demand
from ..deps import signals
from ..models import Course, Enrollment
from ..schemas import (ClassCreate, ClassDemandOut, CourseDetail, CourseRow, CourseStudentRow,
                       DemandBandOut, DemandReport, DistributionBucket, OpenedOut, Openings,
                       SectionCreate, SkillGapOut)
from ..timetable import SchedulingError, open_class, open_section, openings

router = APIRouter(prefix="/courses", tags=["courses"])
settings = get_settings()


def _course_row(c: Course, enrolled: int, sigs: dict[str, StudentSignal],
                gaps: list, waitlist: int = 0) -> CourseRow:
    pcts = [cs.pct for s in sigs.values() for cs in s.courses if cs.course_code == c.code]
    mine = [g for g in gaps if g.course_code == c.code]
    weakest = min(mine, key=lambda g: g.class_mean) if mine else None
    return CourseRow(
        code=c.code, title=c.title, dept=c.dept, teacher=c.teacher, period=c.period,
        room=c.room, enrolled=enrolled, capacity=c.capacity, waitlist=waitlist,
        class_mean=round(statistics.fmean(pcts), 1) if pcts else None,
        below_support=sum(1 for p in pcts if p < settings.support_threshold),
        excelling=sum(1 for s in sigs.values() for cs in s.courses
                      if cs.course_code == c.code and cs.excel_index >= 70),
        weakest_skill=weakest.skill if weakest else None,
        weakest_skill_mean=weakest.class_mean if weakest else None,
        description=c.description or "", length=c.length or "year", credits=c.credits or 0.0,
        prerequisite=c.prerequisite or "", uc_approved=bool(c.uc_approved),
        extra_period=bool(c.extra_period), graded=c.graded is not False,
        catalog_page=c.catalog_page, legacy_title=c.legacy_title or "",
    )


def _counts(db: Session, status: str) -> dict[int, int]:
    counts: dict[int, int] = {}
    for e in db.scalars(select(Enrollment).where(Enrollment.status == status)).all():
        counts[e.course_id] = counts.get(e.course_id, 0) + 1
    return counts


@router.get("", response_model=list[CourseRow])
def list_courses(db: Session = Depends(get_db),
                 sigs: dict[str, StudentSignal] = Depends(signals)) -> list[CourseRow]:
    gaps = skill_gaps(db)
    enrolled, waiting = _counts(db, "enrolled"), _counts(db, "waitlist")
    rows = [_course_row(c, enrolled.get(c.id, 0), sigs, gaps, waiting.get(c.id, 0))
            for c in db.scalars(select(Course).order_by(Course.code)).all()]
    rows.sort(key=lambda r: (r.class_mean if r.class_mean is not None else 999))
    return rows


@router.get("/demand", response_model=DemandReport)
def demand(db: Session = Depends(get_db)) -> DemandReport:
    """Every class ranked by the demand index, most wanted first."""
    return DemandReport(
        formula=FORMULA,
        bands=[DemandBandOut(min=m, kind=k, label=l) for m, k, l in BANDS],
        classes=[ClassDemandOut.model_validate(d) for d in class_demand(db)],
    )


@router.get("/openings", response_model=Openings)
def free_in_period(period: int, db: Session = Depends(get_db)) -> Openings:
    """Rooms and teachers not already booked in a period."""
    return Openings(**openings(db, period))


@router.post("", response_model=OpenedOut, status_code=201)
def create_class(body: ClassCreate, db: Session = Depends(get_db)) -> OpenedOut:
    try:
        c = open_class(db, term=settings.term, **body.model_dump())
    except SchedulingError as e:
        db.rollback()
        raise HTTPException(409, str(e)) from e
    db.commit()
    return OpenedOut(course=_course_row(c, 0, {}, []),
                     message=f"Opened {c.title} ({c.code}) in {c.room}"
                             f"{f', period {c.period}' if c.period else ''} with {c.capacity} seats.")


@router.post("/{code}/sections", response_model=OpenedOut, status_code=201)
def create_section(code: str, body: SectionCreate, db: Session = Depends(get_db)) -> OpenedOut:
    if db.scalar(select(Course).where(Course.code == code)) is None:
        raise HTTPException(404, f"No course with code {code}")
    try:
        section, moved = open_section(db, code, **body.model_dump())
    except SchedulingError as e:
        db.rollback()
        raise HTTPException(409, str(e)) from e
    db.commit()
    return OpenedOut(course=_course_row(section, moved, {}, []), moved_from_waitlist=moved,
                     message=f"Opened {section.code} in {section.room}"
                             f"{f', period {section.period}' if section.period else ''}, "
                             f"{section.capacity} seats — {moved} moved off the waitlist.")


@router.get("/{code}", response_model=CourseDetail)
def course_detail(code: str, db: Session = Depends(get_db),
                  sigs: dict[str, StudentSignal] = Depends(signals)) -> CourseDetail:
    c = db.scalar(select(Course).where(Course.code == code))
    if c is None:
        raise HTTPException(404, f"No course with code {code}")
    enrolled = len(db.scalars(
        select(Enrollment).where(Enrollment.course_id == c.id, Enrollment.status == "enrolled")
    ).all())
    waiting = len(db.scalars(
        select(Enrollment).where(Enrollment.course_id == c.id, Enrollment.status == "waitlist")
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
        course=_course_row(c, enrolled, sigs, gaps, waiting),
        students=students,
        skills=[SkillGapOut.model_validate(g) for g in gaps if g.course_code == code],
        distribution=[DistributionBucket(**b) for b in course_distribution(sigs, code)],
    )
