import statistics

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import StudentSignal, course_distribution, skill_gaps
from ..auth.deps import Principal, require
from ..auth.scope import ensure_course
from ..config import get_settings
from ..db import get_db
from ..demand import BANDS, FORMULA, class_demand
from ..deps import signals
from ..models import Assessment, Course, Enrollment, Intervention, InventoryItem, Score, Student
from ..stock import status_of
from ..schemas import (ClassCreate, ClassDemandOut, CourseAssessmentRow, CourseDetail, CoursePlanRow,
                       CourseRow, CourseStats, CourseStudentRow, CourseSupplyRow, CourseTeacher,
                       TeacherSectionRow,
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


@router.get("", response_model=list[CourseRow], dependencies=[Depends(require("courses.read"))])
def list_courses(db: Session = Depends(get_db),
                 sigs: dict[str, StudentSignal] = Depends(signals)) -> list[CourseRow]:
    gaps = skill_gaps(db)
    enrolled, waiting = _counts(db, "enrolled"), _counts(db, "waitlist")
    rows = [_course_row(c, enrolled.get(c.id, 0), sigs, gaps, waiting.get(c.id, 0))
            for c in db.scalars(select(Course).order_by(Course.code)).all()]
    rows.sort(key=lambda r: (r.class_mean if r.class_mean is not None else 999))
    return rows


@router.get("/demand", response_model=DemandReport, dependencies=[Depends(require("courses.read"))])
def demand(db: Session = Depends(get_db)) -> DemandReport:
    """Every class ranked by the demand index, most wanted first."""
    return DemandReport(
        formula=FORMULA,
        bands=[DemandBandOut(min=m, kind=k, label=l) for m, k, l in BANDS],
        classes=[ClassDemandOut.model_validate(d) for d in class_demand(db)],
    )


@router.get("/openings", response_model=Openings, dependencies=[Depends(require("courses.read"))])
def free_in_period(period: int, db: Session = Depends(get_db)) -> Openings:
    """Rooms and teachers not already booked in a period."""
    return Openings(**openings(db, period))


@router.post("", response_model=OpenedOut, status_code=201, dependencies=[Depends(require("courses.write"))])
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


@router.post("/{code}/sections", response_model=OpenedOut, status_code=201,
             dependencies=[Depends(require("courses.write"))])
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
                  sigs: dict[str, StudentSignal] = Depends(signals),
                  user: Principal = Depends(require("students.read"))) -> CourseDetail:
    ensure_course(db, user, code)
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

    assessments = _course_assessments(db, c)
    stats = _course_stats(c, sigs, students)
    handed = sum(a.submitted for a in assessments)
    stats.late_rate = round(sum(a.late for a in assessments) / handed, 3) if handed else None

    return CourseDetail(
        course=_course_row(c, enrolled, sigs, gaps, waiting),
        students=students,
        skills=[SkillGapOut.model_validate(g) for g in gaps if g.course_code == code],
        distribution=[DistributionBucket(**b) for b in course_distribution(sigs, code)],
        stats=stats,
        assessments=assessments,
        teacher=_course_teacher(db, c, sigs),
        plans=_course_plans(db, c),
        supplies=_course_supplies(db, c),
    )


# ---- the class page ----------------------------------------------------------
def _course_stats(c: Course, sigs: dict[str, StudentSignal], students: list[CourseStudentRow]) -> CourseStats:
    code = c.code
    enrolled = [s for s in sigs.values() if any(cs.course_code == code for cs in s.courses)]
    mine = [cs for s in enrolled for cs in s.courses if cs.course_code == code]
    graded = sum(cs.graded_items for cs in mine)
    missing = sum(cs.missing for cs in mine)
    pcts = [r.pct for r in students]
    deltas = [cs.delta for cs in mine]
    return CourseStats(
        students=len(students),
        median=round(statistics.median(pcts), 1) if pcts else None,
        completion_rate=round(1 - missing / graded, 3) if graded else None,
        mean_trend=round(statistics.fmean(deltas), 1) if deltas else None,
        improving=sum(1 for d in deltas if d >= 3),
        declining=sum(1 for d in deltas if d <= -3),
        absence_rate=round(statistics.fmean(s.absence_rate for s in enrolled), 3) if enrolled else None,
        needs_plan=sum(1 for r in students if r.struggle_index >= 55),
        watch=sum(1 for r in students if 35 <= r.struggle_index < 55),
    )


def _course_assessments(db: Session, c: Course) -> list[CourseAssessmentRow]:
    enrolled_ids = set(db.scalars(select(Enrollment.student_id).where(
        Enrollment.course_id == c.id, Enrollment.status == "enrolled")).all())
    rows = []
    for a in db.scalars(select(Assessment).where(Assessment.course_id == c.id, Assessment.due_on <= settings.today)
                        .order_by(Assessment.due_on, Assessment.id)).all():
        scores = [s for s in db.scalars(select(Score).where(Score.assessment_id == a.id)).all()
                  if s.student_id in enrolled_ids]
        handed = [s for s in scores if s.points is not None]
        mean = (statistics.fmean(s.points / a.max_points * 100 for s in handed)
                if handed and a.max_points else None)
        rows.append(CourseAssessmentRow(
            id=a.id, title=a.title, kind=a.kind, skill=a.skill, due_on=a.due_on,
            class_mean=round(mean, 1) if mean is not None else None,
            submitted=len(handed), missing=len(scores) - len(handed), late=sum(1 for s in handed if s.late)))
    return rows


def _course_teacher(db: Session, c: Course, sigs: dict[str, StudentSignal]) -> CourseTeacher:
    sections = db.scalars(select(Course).where(Course.teacher == c.teacher).order_by(Course.period)).all()
    rows, taught = [], set()
    for s in sections:
        ids = db.scalars(select(Enrollment.student_id).where(
            Enrollment.course_id == s.id, Enrollment.status == "enrolled")).all()
        taught.update(ids)
        pcts = [cs.pct for sig in sigs.values() for cs in sig.courses if cs.course_code == s.code]
        rows.append(TeacherSectionRow(code=s.code, title=s.title, period=s.period, room=s.room,
                                      enrolled=len(ids),
                                      class_mean=round(statistics.fmean(pcts), 1) if pcts else None))
    return CourseTeacher(name=c.teacher, sections=rows, students_taught=len(taught))


def _course_plans(db: Session, c: Course) -> list[CoursePlanRow]:
    out = []
    for iv in db.scalars(select(Intervention).where(Intervention.course_id == c.id)
                         .order_by(Intervention.status, Intervention.id.desc())).all():
        st = db.get(Student, iv.student_id)
        out.append(CoursePlanRow(id=iv.id, sid=st.sid if st else "", student_name=st.name if st else "",
                                 kind=iv.kind, title=iv.title, owner=iv.owner, status=iv.status))
    return out


def _course_supplies(db: Session, c: Course) -> list[CourseSupplyRow]:
    out = []
    for item in db.scalars(select(InventoryItem)).all():
        if c.code.split(".")[0] in (item.linked_courses or []):
            st = status_of(item)
            out.append(CourseSupplyRow(sku=item.sku, name=item.name, on_hand=item.on_hand, par=item.par,
                                       status=st.kind, status_label=st.label, requisitioned=item.requisitioned))
    return sorted(out, key=lambda r: r.on_hand / max(1, r.par))
