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
from sqlalchemy import false as sa_false
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
    # Students signing up per week of the term, oldest first — the velocity term
    # of the demand index (app/demand.py).
    signups: Mapped[list] = mapped_column(JSON, default=list)

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
    # The student information system's id (OneRoster lineItem sourcedId), so a
    # re-import updates this assessment rather than adding a second one.
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

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
    # Excused from this piece: it counts neither as missing nor toward mastery.
    exempt: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
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

class StudentSnapshot(Base):
    """A student's indices on one day, kept so a plan's effect can be seen over time.

    The indices themselves are always recomputed from the gradebook; this is a
    record of what they read on `taken_on`, written once a day by the worker (and
    backfilled weekly for the demo term). Re-taking a day replaces that day.
    """

    __tablename__ = "student_snapshots"
    __table_args__ = (UniqueConstraint("student_id", "taken_on", name="uq_student_snapshot_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    taken_on: Mapped[date] = mapped_column(Date, index=True)
    struggle_index: Mapped[int] = mapped_column(Integer)
    excel_index: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(16))            # the computed band, before any override
    absence_rate: Mapped[float] = mapped_column(Float, default=0.0)
    open_interventions: Mapped[int] = mapped_column(Integer, default=0)
    courses: Mapped[list] = mapped_column(JSON, default=list)   # [{code, pct, struggle, excel}]
    reasons: Mapped[list] = mapped_column(JSON, default=list)   # concern and strength labels


class FlagOverride(Base):
    """A person overruling the index for one student, with a reason and an end date.

    `acknowledge` keeps the band but records that the concern is known and in hand,
    so the student stops counting as "needs a plan and has none". `set-band`
    replaces the band the index gave. Either way the computed band is still shown
    beside it, and the override lapses on `expires_on` so it is looked at again.
    """

    __tablename__ = "flag_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))             # acknowledge | set-band
    band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    computed_band: Mapped[str] = mapped_column(String(16))   # what the index said when it was made
    note: Mapped[str] = mapped_column(Text)
    expires_on: Mapped[date] = mapped_column(Date)
    created_by: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(160), nullable=True)


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
    # What a scoped run is about, e.g. "course:MAT-150"; None for a sweep.
    subject: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Set when the general manager dispatched this run.
    parent_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
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
    # Who approved or rejected it: the signed-in person's email, and why. A rejection
    # always carries a reason; read together, they show where the agents or the
    # indices are wrong.
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

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


# ---- background work ----------------------------------------------------------
class Job(Base):
    """A unit of background work, claimed and run by the worker process (app/worker.py).

    Jobs live in the database, not in a web process's memory, so a deploy or a
    crash loses nothing: a job whose worker stopped heartbeating is put back on the
    queue, and given up (with its run or document marked failed) only after
    `max_attempts`.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)     # agent_run | document_analysis | snapshot
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime, index=True)
    # Set for work that must happen once, e.g. "snapshot:2026-09-12".
    unique_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    locked_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkerBeat(Base):
    """The last time each worker process checked in, for the readiness report."""

    __tablename__ = "worker_beats"

    worker_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime)
    current_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---- people who use the system ---------------------------------------------
class User(Base):
    """A member of staff who can sign in. Never deleted, only deactivated, so the
    audit log always names a real account.

    `teacher_name` links a teacher to their sections: it must match
    `Course.teacher` exactly, and it is what limits a teacher to their own
    students (app/auth/scope.py).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(24))          # admin | counselor | teacher | registrar | business
    teacher_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # None for accounts that only sign in through the school's identity provider.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base):
    """A signed-in browser. Only a hash of the cookie's token is stored, so the
    table leaking does not hand anyone a session."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship()


class AuditEvent(Base):
    """Who did what, to which record, and when — including looking at a student.

    Written for every change made through the API (successful or refused), every
    read of an individual student's record or documents, and every sign-in
    attempt. Rows are only ever inserted. The actor is copied rather than joined,
    so the log reads the same after an account is renamed or deactivated.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(160), default="")
    actor_role: Mapped[str] = mapped_column(String(24), default="")
    action: Mapped[str] = mapped_column(String(80), index=True)
    method: Mapped[str] = mapped_column(String(8), default="")
    path: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str] = mapped_column(String(36), default="")


# ---- finance ---------------------------------------------------------------
class BudgetLine(Base):
    """One department's allocation for one purpose in one fiscal year."""

    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(60))
    fiscal_year: Mapped[str] = mapped_column(String(8), default="FY2027")
    allocated: Mapped[float] = mapped_column(Float, default=0.0)
    owner: Mapped[str] = mapped_column(String(120), default="")

    transactions: Mapped[list[Transaction]] = relationship(back_populates="line", cascade="all, delete-orphan")


class Transaction(Base):
    """Money that has actually left (or come back to) a budget line."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("budget_lines.id", ondelete="CASCADE"), index=True)
    posted_on: Mapped[date] = mapped_column(Date)
    vendor: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(240))
    amount: Mapped[float] = mapped_column(Float)          # positive = spent, negative = refund
    reference: Mapped[str] = mapped_column(String(40), default="")
    # A one-time purchase (an August laptop refresh) must not be extrapolated as a
    # monthly run rate, or every front-loaded line looks like it will overspend.
    one_time: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(16), default="clear")  # clear | flagged | cleared
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    line: Mapped[BudgetLine] = relationship(back_populates="transactions")


class BudgetTransfer(Base):
    """Moving allocation between lines. Allocations themselves are never edited,
    so the original budget stays readable next to every change made to it."""

    __tablename__ = "budget_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_line_id: Mapped[int] = mapped_column(ForeignKey("budget_lines.id", ondelete="CASCADE"))
    to_line_id: Mapped[int] = mapped_column(ForeignKey("budget_lines.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[str] = mapped_column(String(120), default="Business office")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClassPlan(Base):
    """An improvement plan for a class, adopted from an agent's draft.

    `baseline` is the class's performance snapshot on the day it was adopted
    (app/class_plans.py), so progress is read against real numbers rather than
    anyone's memory of how the class was doing.
    """

    __tablename__ = "class_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200))
    diagnosis: Mapped[str] = mapped_column(Text, default="")
    focus_strands: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    goal: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed | retired
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_on: Mapped[date] = mapped_column(Date)
    review_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StudyPlan(Base):
    """A study plan for one student in one class, adopted from an agent's draft.

    `baseline` is the student's class-work reading on the day it was adopted
    (app/study_plans.py): every assignment, strand and finding, so progress is
    read against what the plan was written from.
    """

    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_sid: Mapped[str] = mapped_column(String(16), index=True)
    course_code: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200))
    diagnosis: Mapped[str] = mapped_column(Text, default="")
    focus_strands: Mapped[list] = mapped_column(JSON, default=list)
    sessions: Mapped[list] = mapped_column(JSON, default=list)
    catch_up: Mapped[list] = mapped_column(JSON, default=list)   # [{id, title, due_on}]
    goal: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed | retired
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_on: Mapped[date] = mapped_column(Date)
    review_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
