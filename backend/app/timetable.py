"""Opening classes and sections, in one place.

The registrar's screen and the registrar agent's approved proposals both open
sections. They share this code so they refuse the same clashes: a room already
used in that period, or a teacher already teaching in it. Period 0 is "outside
the timetable" (extra-period ensembles, clubs) and never clashes.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .demand import base_code
from .models import Course, Enrollment

SECTION_LETTERS = "BCDEFGH"


class SchedulingError(ValueError):
    """The change cannot be made as asked. The message says why, for a person."""


def clashes(db: Session, period: int, room: str, teacher: str) -> list[str]:
    if period <= 0:
        return []
    out = []
    for c in db.scalars(select(Course).where(Course.period == period)).all():
        if room and c.room.strip().lower() == room.strip().lower():
            out.append(f"{room} is already used in period {period} by {c.code}")
        if teacher and c.teacher.strip().lower() == teacher.strip().lower():
            out.append(f"{teacher} already teaches {c.code} in period {period}")
    return out


def openings(db: Session, period: int) -> dict:
    """Rooms and teachers free in a period, from the rooms and teachers the school already uses."""
    courses = db.scalars(select(Course)).all()
    busy = [c for c in courses if c.period == period] if period > 0 else []
    rooms = sorted({c.room for c in courses} - {c.room for c in busy})
    teachers = sorted({c.teacher for c in courses} - {c.teacher for c in busy})
    return {"period": period, "free_rooms": rooms, "free_teachers": teachers}


def _refuse_clashes(db: Session, period: int, room: str, teacher: str) -> None:
    found = clashes(db, period, room, teacher)
    if found:
        raise SchedulingError("; ".join(found) + ".")


def next_section_code(db: Session, code: str) -> str:
    base = base_code(code)
    taken = {c for c in db.scalars(select(Course.code)).all()}
    new = next((f"{base}.{l}" for l in SECTION_LETTERS if f"{base}.{l}" not in taken), None)
    if new is None:
        raise SchedulingError(f"{base} already has every section letter in use.")
    return new


def open_section(db: Session, code: str, *, period: int, room: str, teacher: str | None = None,
                 capacity: int | None = None, move_from_waitlist: int = 0) -> tuple[Course, int]:
    """Another section of an existing class, seeded from its waitlist in the order
    students joined it. Returns the new section and how many students moved.

    Flushes but does not commit; the caller owns the transaction.
    """
    src = db.scalar(select(Course).where(Course.code == code))
    if src is None:
        raise SchedulingError(f"No class with code {code}.")
    teacher = (teacher or "").strip() or src.teacher
    room = room.strip()
    if not room:
        raise SchedulingError("A section needs a room.")
    _refuse_clashes(db, period, room, teacher)

    section = Course(
        code=next_section_code(db, code), title=src.title, dept=src.dept, teacher=teacher,
        period=period, room=room, capacity=max(1, int(capacity or src.capacity)), term=src.term,
        description=src.description, length=src.length, credits=src.credits,
        prerequisite=src.prerequisite, uc_approved=src.uc_approved, extra_period=src.extra_period,
        graded=src.graded, catalog_page=src.catalog_page, legacy_title=src.legacy_title, signups=[],
    )
    db.add(section)
    db.flush()

    # The waitlist of the whole class, not just the section named: a student
    # waiting on MAT-150.B is as entitled to a seat in MAT-150.C as one on MAT-150.
    siblings = [c.id for c in db.scalars(select(Course)).all()
                if base_code(c.code) == base_code(code) and c.id != section.id]
    waiting = db.scalars(select(Enrollment).where(
        Enrollment.course_id.in_(siblings), Enrollment.status == "waitlist").order_by(Enrollment.id)).all()
    moved = 0
    for enr in waiting[:min(max(0, int(move_from_waitlist)), section.capacity)]:
        enr.course_id = section.id
        enr.status = "enrolled"
        moved += 1
    db.flush()
    return section, moved


def open_class(db: Session, *, code: str, title: str, dept: str, teacher: str, period: int, room: str,
               capacity: int, term: str, description: str = "", length: str = "semester",
               credits: float = 0.5, prerequisite: str = "None") -> Course:
    """A class the school has not run before. Flushes but does not commit."""
    code = code.strip().upper()
    if "." in code:
        raise SchedulingError("Use a base code such as ART-150; section letters are added when a section opens.")
    if any(base_code(c) == code for c in db.scalars(select(Course.code)).all()):
        raise SchedulingError(f"{code} already exists. Open another section of it instead.")
    _refuse_clashes(db, period, room, teacher)
    c = Course(code=code, title=title.strip(), dept=dept.strip(), teacher=teacher.strip(), period=period,
               room=room.strip(), capacity=capacity, term=term, description=description.strip(),
               length=length, credits=credits, prerequisite=prerequisite.strip() or "None", signups=[])
    db.add(c)
    db.flush()
    return c
