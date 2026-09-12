"""The academic record.

Shape worth noting: `Assessment.skill` is what makes "struggling on what"
answerable. A course grade says a student is behind; a skill tag says they are
behind on *linear equations* while fine on *graphing*, which is the difference
between a useful referral and a shrug. A missing Score row for a past-due
assessment is meaningful data, not absent data — it counts as a zero toward
mastery and is tracked separately as missing work.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    sid: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    grade: Mapped[int] = mapped_column(Integer)
    homeroom: Mapped[str] = mapped_column(String(16))
    guardian_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guardian_email: Mapped[str | None] = mapped_column(String(160), nullable=True)

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student", cascade="all, delete-orphan")
    scores: Mapped[list[Score]] = relationship(back_populates="student", cascade="all, delete-orphan")
    attendance: Mapped[list[AttendanceDay]] = relationship(back_populates="student", cascade="all, delete-orphan")
    interventions: Mapped[list[Intervention]] = relationship(back_populates="student", cascade="all, delete-orphan")
    documents: Mapped[list[StudentDocument]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    dept: Mapped[str] = mapped_column(String(60))
    teacher: Mapped[str] = mapped_column(String(120))
    period: Mapped[int] = mapped_column(Integer, default=0)
    room: Mapped[str] = mapped_column(String(32), default="TBD")
    capacity: Mapped[int] = mapped_column(Integer, default=24)
    term: Mapped[str] = mapped_column(String(32), default="Fall 2026")
    # From the course of study (app/catalog.py).
    description: Mapped[str] = mapped_column(Text, default="")
    length: Mapped[str] = mapped_column(String(16), default="year")
    credits: Mapped[float] = mapped_column(Float, default=1.0)
    prerequisite: Mapped[str] = mapped_column(String(200), default="")
    uc_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_period: Mapped[bool] = mapped_column(Boolean, default=False)
    graded: Mapped[bool] = mapped_column(Boolean, default=True)
    catalog_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_title: Mapped[str] = mapped_column(String(120), default="")

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="course", cascade="all, delete-orphan")
    assessments: Mapped[list[Assessment]] = relationship(back_populates="course", cascade="all, delete-orphan")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_enrollment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="enrolled")  # enrolled | waitlist | dropped

    student: Mapped[Student] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship(back_populates="enrollments")


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(24))          # homework | quiz | lab | project | test
    skill: Mapped[str] = mapped_column(String(80), index=True)
    max_points: Mapped[float] = mapped_column(Float, default=100.0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    assigned_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date, index=True)

    course: Mapped[Course] = relationship(back_populates="assessments")
    scores: Mapped[list[Score]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("assessment_id", "student_id", name="uq_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    points: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = not submitted
    late: Mapped[bool] = mapped_column(default=False)
    recorded_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="scores")
    student: Mapped[Student] = relationship(back_populates="scores")


class AttendanceDay(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "day", name="uq_attendance"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16))  # present | absent | tardy | excused

    student: Mapped[Student] = relationship(back_populates="attendance")


class Intervention(Base):
    """A support plan someone owns. Recommendations are computed; these are chosen."""

    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))    # tutoring | homework-recovery | check-in | attendance-plan | family-contact | enrichment
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="Support office")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed | declined
    opened_on: Mapped[date] = mapped_column(Date)
    review_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student: Mapped[Student] = relationship(back_populates="interventions")
    course: Mapped[Course | None] = relationship()

class InventoryItem(Base):
    """The stockroom. Mirrors the registrar console's inventory so the fleet has
    one substrate to act on rather than two disagreeing copies."""

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60), index=True)
    unit: Mapped[str] = mapped_column(String(24), default="unit")
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0)
    par: Mapped[int] = mapped_column(Integer, default=1)
    location: Mapped[str] = mapped_column(String(120), default="Main supply room")
    supplier: Mapped[str] = mapped_column(String(120), default="Central District Warehouse")
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    last_counted: Mapped[date | None] = mapped_column(Date, nullable=True)
    linked_courses: Mapped[list] = mapped_column(JSON, default=list)
    requisitioned: Mapped[bool] = mapped_column(default=False)


class AgentRun(Base):
    """One execution of one agent, with the whole transcript kept.

    The transcript is the point: a local 4B model gets things wrong, and the only
    way to trust a proposal is to be able to read exactly which tools the agent
    called, what they returned, and what it did with that.
    """

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(60))
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    summary: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[list] = mapped_column(JSON, default=list)
    steps_used: Mapped[int] = mapped_column(Integer, default=0)
    tool_errors: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    proposals: Mapped[list["Proposal"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Proposal(Base):
    """What an agent wants to do. It cannot do it.

    Agents never write to the record. They emit a proposal of a known kind with a
    schema-validated payload; a person approves it; deterministic code applies it.
    That boundary is what makes a small local model safe to run against a school's
    data at all.
    """

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | rejected | failed
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[AgentRun | None] = relationship(back_populates="proposals")


class StudentDocument(Base):
    """A document about one student, and what was found in it.

    Only the extracted text is kept, never the uploaded file: the text is all the
    analysis needs, and a school should hold as little of a child's paperwork as it
    can. Deleting the row deletes everything that was read.
    """

    __tablename__ = "student_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(32), default="other")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="processing")  # processing | done | failed
    summary: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list] = mapped_column(JSON, default=list)
    rejected: Mapped[list] = mapped_column(JSON, default=list)
    notices: Mapped[list] = mapped_column(JSON, default=list)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(60), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    analysed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    student: Mapped[Student] = relationship(back_populates="documents")
