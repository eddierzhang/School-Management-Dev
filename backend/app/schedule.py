"""The timetable, read two ways: the whole school by period, and one student's day.

Both are derived from the same rows — a section's period and room, and who is
enrolled or waiting in it — so the master schedule and a student's timetable
cannot disagree.

A conflict is reported, never resolved here. Two sections in one room or one
teacher in two rooms at once is a timetable error; a student enrolled in two
classes in the same period is a registration error. Both need a person to decide
which one gives way, and hiding either behind a tidy grid would be worse than
showing it.

Period 0 means "outside the timetable" (before school, lunch, extra periods) and
never clashes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .demand import base_code
from .models import Course, Enrollment, Student

SCHOOL_DAY_PERIODS = 7


@dataclass
class SectionSlot:
    code: str
    title: str
    dept: str
    teacher: str
    room: str
    period: int
    length: str
    credits: float
    enrolled: int
    capacity: int
    waitlist: int
    base_code: str


@dataclass
class TimetableClash:
    kind: str          # room | teacher
    who: str
    period: int
    sections: list[str]


@dataclass
class StudentClash:
    sid: str
    name: str
    grade: int
    period: int
    sections: list[str]


@dataclass
class SchoolSchedule:
    periods: list[int]
    sections: list[SectionSlot]
    rooms: list[str]
    teachers: list[str]
    clashes: list[TimetableClash]
    student_clashes: list[StudentClash]
    students_with_clashes: int


@dataclass
class StudentPeriod:
    period: int
    enrolled: list[SectionSlot] = field(default_factory=list)
    waitlisted: list[SectionSlot] = field(default_factory=list)

    @property
    def clash(self) -> bool:
        return self.period > 0 and len(self.enrolled) > 1


@dataclass
class StudentSchedule:
    sid: str
    name: str
    grade: int
    homeroom: str
    periods: list[StudentPeriod]
    classes: int
    credits: float
    free_periods: list[int]
    clashes: int
    waitlisted: int


def _slots(db: Session) -> dict[int, SectionSlot]:
    enrolled: dict[int, int] = defaultdict(int)
    waiting: dict[int, int] = defaultdict(int)
    for course_id, status in db.execute(select(Enrollment.course_id, Enrollment.status)).all():
        if status == "enrolled":
            enrolled[course_id] += 1
        elif status == "waitlist":
            waiting[course_id] += 1
    return {c.id: SectionSlot(code=c.code, title=c.title, dept=c.dept, teacher=c.teacher, room=c.room,
                              period=c.period or 0, length=c.length or "year", credits=c.credits or 0.0,
                              enrolled=enrolled[c.id], capacity=c.capacity, waitlist=waiting[c.id],
                              base_code=base_code(c.code))
            for c in db.scalars(select(Course).order_by(Course.period, Course.code)).all()}


def _periods(slots) -> list[int]:
    """Every period of the school day, plus any later or out-of-timetable slot in use."""
    used = {s.period for s in slots}
    last = max([SCHOOL_DAY_PERIODS, *used])
    return list(range(1, last + 1)) + ([0] if 0 in used else [])


def _timetable_clashes(slots: list[SectionSlot]) -> list[TimetableClash]:
    by: dict[tuple[str, str, int], list[str]] = defaultdict(list)
    for s in slots:
        if s.period <= 0:
            continue
        by[("room", s.room, s.period)].append(s.code)
        by[("teacher", s.teacher, s.period)].append(s.code)
    return [TimetableClash(kind=k, who=w, period=p, sections=codes)
            for (k, w, p), codes in sorted(by.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1]))
            if len(codes) > 1]


def school_schedule(db: Session) -> SchoolSchedule:
    slots = _slots(db)
    sections = list(slots.values())

    per_student: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for student_id, course_id in db.execute(
            select(Enrollment.student_id, Enrollment.course_id).where(Enrollment.status == "enrolled")).all():
        s = slots.get(course_id)
        if s and s.period > 0:
            per_student[student_id][s.period].append(s.code)
    students = {st.id: st for st in db.scalars(select(Student)).all()}
    student_clashes = sorted(
        (StudentClash(sid=students[sid].sid, name=students[sid].name, grade=students[sid].grade,
                      period=p, sections=sorted(codes))
         for sid, by_period in per_student.items() for p, codes in by_period.items() if len(codes) > 1),
        key=lambda c: (c.period, c.name))

    return SchoolSchedule(
        periods=_periods(sections), sections=sections,
        rooms=sorted({s.room for s in sections}), teachers=sorted({s.teacher for s in sections}),
        clashes=_timetable_clashes(sections), student_clashes=student_clashes,
        students_with_clashes=len({c.sid for c in student_clashes}),
    )


def student_schedule(db: Session, sid: str) -> StudentSchedule | None:
    st = db.scalar(select(Student).where(Student.sid == sid))
    if st is None:
        return None
    slots = _slots(db)
    mine = db.execute(select(Enrollment.course_id, Enrollment.status)
                      .where(Enrollment.student_id == st.id)).all()
    enrolled = [slots[cid] for cid, status in mine if status == "enrolled" and cid in slots]
    waiting = [slots[cid] for cid, status in mine if status == "waitlist" and cid in slots]

    periods = {p: StudentPeriod(period=p) for p in _periods(slots.values())}
    for s in enrolled:
        periods[s.period].enrolled.append(s)
    for s in waiting:
        periods[s.period].waitlisted.append(s)
    rows = list(periods.values())
    return StudentSchedule(
        sid=st.sid, name=st.name, grade=st.grade, homeroom=st.homeroom, periods=rows,
        classes=len(enrolled), credits=round(sum(s.credits for s in enrolled), 2),
        free_periods=[r.period for r in rows if r.period > 0 and not r.enrolled],
        clashes=sum(1 for r in rows if r.clash), waitlisted=len(waiting),
    )
