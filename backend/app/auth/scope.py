"""Which students and classes a person may see.

Everyone with `students.read` sees every student, except a teacher, who sees the
students enrolled or waitlisted in their own sections: the sections whose
`Course.teacher` equals the account's `teacher_name`. A teacher account without a
`teacher_name` sees no students at all rather than all of them.

Refusals are 404, not 403, so a teacher cannot tell whether a student ID they
guessed exists.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, Enrollment, Student
from .deps import Principal


def visible_courses(db: Session, user: Principal) -> set[str] | None:
    """Course codes the person may see; None means all of them."""
    if not user.is_teacher:
        return None
    if not user.teacher_name:
        return set()
    return set(db.scalars(select(Course.code).where(Course.teacher == user.teacher_name)).all())


def visible_students(db: Session, user: Principal) -> set[str] | None:
    """Student IDs the person may see; None means all of them."""
    if not user.is_teacher:
        return None
    if not user.teacher_name:
        return set()
    return set(db.scalars(
        select(Student.sid).join(Enrollment, Enrollment.student_id == Student.id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Course.teacher == user.teacher_name, Enrollment.status.in_(["enrolled", "waitlist"]))).all())


def ensure_student(db: Session, user: Principal, sid: str) -> None:
    allowed = visible_students(db, user)
    if allowed is not None and sid not in allowed:
        raise HTTPException(404, f"No student with SID {sid}")


def ensure_course(db: Session, user: Principal, code: str) -> None:
    allowed = visible_courses(db, user)
    if allowed is not None and code not in allowed:
        raise HTTPException(404, f"No course with code {code}")
