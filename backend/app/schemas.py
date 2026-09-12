"""Wire shapes. These mirror the analytics dataclasses so the frontend has one
contract to type against, and so an internal refactor cannot silently change
the API.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReasonOut(Base):
    code: str
    label: str
    detail: str
    kind: str


class SkillMasteryOut(Base):
    skill: str
    pct: float
    graded: int
    missing: int
    course_code: str = ""


class CourseSignalOut(Base):
    course_code: str
    course_title: str
    dept: str
    teacher: str
    pct: float
    recent_pct: float | None
    prior_pct: float | None
    delta: float
    graded_items: int
    missing: int
    missing_rate: float
    completion: float
    spread: float
    struggle_index: int
    excel_index: int
    skills: list[SkillMasteryOut] = []


class RecommendationOut(Base):
    code: str
    title: str
    rationale: str
    kind: str
    priority: int
    course_code: str | None = None
    suggested_owner: str


class StudentRow(Base):
    """List view: enough to rank and scan, not the whole record."""
    sid: str
    name: str
    grade: int
    homeroom: str
    struggle_index: int
    excel_index: int
    standing: int
    mixed: bool
    band: str
    absence_rate: float
    open_interventions: int
    top_reason: str | None = None
    course_count: int = 0
    lowest_course: str | None = None
    lowest_pct: float | None = None
    strongest_course: str | None = None
    strongest_pct: float | None = None


class StudentDetail(Base):
    sid: str
    name: str
    grade: int
    homeroom: str
    guardian_name: str | None = None
    guardian_email: str | None = None
    struggle_index: int
    excel_index: int
    standing: int
    mixed: bool
    band: str
    days_counted: int
    absences: int
    tardies: int
    absence_rate: float
    tardy_rate: float
    courses: list[CourseSignalOut] = []
    reasons: list[ReasonOut] = []
    weakest_skills: list[SkillMasteryOut] = []
    strongest_skills: list[SkillMasteryOut] = []
    recommendations: list[RecommendationOut] = []
    interventions: list[InterventionOut] = []


class CourseRow(Base):
    code: str
    title: str
    dept: str
    teacher: str
    period: int
    room: str
    enrolled: int
    capacity: int
    waitlist: int = 0
    class_mean: float | None = None
    below_support: int = 0
    excelling: int = 0
    weakest_skill: str | None = None
    weakest_skill_mean: float | None = None
    # from the course of study
    description: str = ""
    length: str = "year"
    credits: float = 1.0
    prerequisite: str = ""
    uc_approved: bool = False
    extra_period: bool = False
    graded: bool = True
    catalog_page: int | None = None
    legacy_title: str = ""


class CourseStudentRow(Base):
    sid: str
    name: str
    grade: int
    pct: float
    delta: float
    missing: int
    graded_items: int
    struggle_index: int
    excel_index: int


class SkillGapOut(Base):
    course_code: str
    course_title: str
    dept: str
    teacher: str
    skill: str
    class_mean: float
    students_below: int
    cohort: int
    share_below: float


class DistributionBucket(Base):
    label: str
    count: int


class CourseStats(Base):
    students: int
    median: float | None = None
    completion_rate: float | None = None      # share of graded work handed in
    late_rate: float | None = None
    mean_trend: float | None = None           # mean change, recent vs earlier work
    improving: int = 0
    declining: int = 0
    absence_rate: float | None = None         # mean over the enrolled students
    needs_plan: int = 0
    watch: int = 0


class CourseAssessmentRow(Base):
    id: int
    title: str
    kind: str
    skill: str
    due_on: date
    class_mean: float | None = None
    submitted: int
    missing: int
    late: int


class TeacherSectionRow(Base):
    code: str
    title: str
    period: int
    room: str
    enrolled: int
    class_mean: float | None = None


class CourseTeacher(Base):
    name: str
    sections: list[TeacherSectionRow]
    students_taught: int


class CoursePlanRow(Base):
    id: int
    sid: str
    student_name: str
    kind: str
    title: str
    owner: str
    status: str


class CourseSupplyRow(Base):
    sku: str
    name: str
    on_hand: int
    par: int
    status: str
    status_label: str
    requisitioned: bool


class CourseDetail(Base):
    course: CourseRow
    students: list[CourseStudentRow]
    skills: list[SkillGapOut]
    distribution: list[DistributionBucket]
    stats: CourseStats | None = None
    assessments: list[CourseAssessmentRow] = []
    teacher: CourseTeacher | None = None
    plans: list[CoursePlanRow] = []
    supplies: list[CourseSupplyRow] = []


# ---- demand and opening classes ---------------------------------------------
class SectionDemandOut(Base):
    code: str
    teacher: str
    period: int
    room: str
    capacity: int
    enrolled: int
    waitlist: int


class ClassDemandOut(Base):
    code: str
    title: str
    dept: str
    sections: list[SectionDemandOut]
    enrolled: int
    capacity: int
    waitlist: int
    signups: list[int]
    recent_signups: int
    prior_signups: int
    trend: str                  # rising | falling | level
    fill: float
    pressure: float
    velocity: float
    score: int
    kind: str                   # the interface's status vocabulary
    label: str                  # Over-subscribed | High demand | Healthy | Seats to fill
    action: str                 # open-section | raise-capacity | promote | review | none
    reasons: list[str]


class DemandBandOut(BaseModel):
    min: int
    kind: str
    label: str


class DemandReport(BaseModel):
    formula: str
    bands: list[DemandBandOut]
    classes: list[ClassDemandOut]


class Openings(BaseModel):
    period: int
    free_rooms: list[str]
    free_teachers: list[str]


class SectionCreate(BaseModel):
    period: int = Field(ge=0, le=8)
    room: str = Field(min_length=1, max_length=32)
    teacher: str | None = Field(default=None, max_length=120)
    capacity: int | None = Field(default=None, ge=1, le=120)
    move_from_waitlist: int = Field(default=0, ge=0)


class ClassCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z]{2,4}-\d{3}$")
    title: str = Field(min_length=3, max_length=120)
    dept: str = Field(min_length=2, max_length=60)
    teacher: str = Field(min_length=2, max_length=120)
    period: int = Field(ge=0, le=8)
    room: str = Field(min_length=1, max_length=32)
    capacity: int = Field(ge=1, le=120)
    description: str = Field(default="", max_length=2000)
    length: str = Field(default="semester", pattern="^(year|semester)$")
    credits: float = Field(default=0.5, ge=0, le=2)
    prerequisite: str = Field(default="None", max_length=200)


class OpenedOut(BaseModel):
    course: CourseRow
    moved_from_waitlist: int = 0
    message: str


class InterventionOut(Base):
    id: int
    student_sid: str
    student_name: str
    course_code: str | None = None
    kind: str
    title: str
    rationale: str
    owner: str
    status: str
    opened_on: date
    review_on: date | None = None
    outcome: str | None = None


class InterventionCreate(BaseModel):
    student_sid: str
    kind: str = Field(pattern="^(tutoring|homework-recovery|check-in|attendance-plan|family-contact|enrichment)$")
    title: str = Field(min_length=3, max_length=200)
    rationale: str = ""
    course_code: str | None = None
    owner: str = "Support office"
    review_on: date | None = None


class InterventionUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|completed|declined)$")
    outcome: str | None = None
    owner: str | None = None
    review_on: date | None = None


class ScoreIn(BaseModel):
    assessment_id: int
    student_sid: str
    points: float | None = None
    late: bool = False


# ---- stockroom ----------------------------------------------------------
class LinkedCourse(Base):
    code: str
    title: str
    enrolled: int


class InventoryRow(Base):
    sku: str
    name: str
    category: str
    unit: str
    on_hand: int
    reorder_point: int
    par: int
    location: str
    supplier: str
    unit_cost: float
    last_counted: date | None = None
    linked_courses: list[str] = []
    requisitioned: bool = False
    status: str
    status_label: str
    ratio: float
    short_by: int
    cost_to_par: float
    students_affected: int = 0
    days_since_count: int | None = None


class InventoryDetail(InventoryRow):
    value_on_hand: float
    classes: list[LinkedCourse] = []


class InventoryUpdate(BaseModel):
    on_hand: int | None = Field(default=None, ge=0, le=100000)
    reorder_point: int | None = Field(default=None, ge=0, le=100000)
    par: int | None = Field(default=None, ge=1, le=100000)
    requisitioned: bool | None = None


class CountIn(BaseModel):
    """A physical count replaces the running total and stamps the date."""
    on_hand: int = Field(ge=0, le=100000)


class InventoryCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    category: str = "Facilities"
    unit: str = "unit"
    on_hand: int = Field(default=0, ge=0, le=100000)
    reorder_point: int = Field(default=0, ge=0, le=100000)
    par: int = Field(default=1, ge=1, le=100000)
    location: str = "Main supply room"
    supplier: str = "Central District Warehouse"
    unit_cost: float = Field(default=0.0, ge=0)
    linked_courses: list[str] = []


class RequisitionSupplier(Base):
    supplier: str
    lines: list[InventoryRow]
    cost: float


class Requisition(Base):
    lines: int
    cost: float
    by_supplier: list[RequisitionSupplier]


class StockroomSummary(Base):
    items: int
    needs_attention: int
    below_reorder: int
    on_requisition: int
    value_on_hand: float
    cost_to_par: float
    categories: list[str]


class BandCount(Base):
    band: str
    count: int


class Summary(Base):
    school: str
    term: str
    today: date
    students: int
    courses: int
    graded_assessments: int
    bands: list[BandCount]
    needs_plan: int
    watch: int
    excelling: int
    steady: int
    open_interventions: int
    unaddressed: int
    mean_attendance: float
    top_skill_gaps: list[SkillGapOut]


StudentDetail.model_rebuild()


# ---- schedule ----------------------------------------------------------------
class SectionSlotOut(Base):
    code: str
    title: str
    dept: str
    teacher: str
    room: str
    period: int                 # 0 = outside the timetable
    length: str
    credits: float
    enrolled: int
    capacity: int
    waitlist: int
    base_code: str


class TimetableClashOut(Base):
    kind: str                   # room | teacher
    who: str
    period: int
    sections: list[str]


class StudentClashOut(Base):
    sid: str
    name: str
    grade: int
    period: int
    sections: list[str]


class SchoolScheduleOut(Base):
    periods: list[int]
    sections: list[SectionSlotOut]
    rooms: list[str]
    teachers: list[str]
    clashes: list[TimetableClashOut]
    student_clashes: list[StudentClashOut]
    students_with_clashes: int


class StudentPeriodOut(Base):
    period: int
    enrolled: list[SectionSlotOut]
    waitlisted: list[SectionSlotOut]
    clash: bool


class StudentScheduleOut(Base):
    sid: str
    name: str
    grade: int
    homeroom: str
    periods: list[StudentPeriodOut]
    classes: int
    credits: float
    free_periods: list[int]
    clashes: int
    waitlisted: int


# ---- class improvement plans -------------------------------------------------
class PlanProgressRow(BaseModel):
    measure: str
    baseline: float | None = None
    now: float | None = None
    change: float | None = None


class ClassPlanOut(BaseModel):
    id: int
    course_code: str
    title: str
    diagnosis: str
    focus_strands: list[str]
    actions: list[str]
    goal: str
    owner: str
    status: str                 # active | completed | retired
    outcome: str | None = None
    opened_on: date
    review_on: date | None = None
    closed_on: date | None = None
    run_id: int | None = None
    progress: list[PlanProgressRow]


class PlanDraftOut(BaseModel):
    id: int                     # the pending proposal
    run_id: int | None = None
    summary: str
    payload: dict
    created_at: datetime | None = None


class DraftRunOut(BaseModel):
    id: int
    status: str                 # running | done | failed
    summary: str = ""
    error: str | None = None
    steps_used: int = 0
    duration_ms: int = 0
    proposals: int = 0
    started_at: datetime | None = None


class ClassImprovementOut(BaseModel):
    performance: dict           # app/class_plans.ClassPerformance.as_dict()
    plans: list[ClassPlanOut]
    drafts: list[PlanDraftOut]
    latest_run: DraftRunOut | None = None


class ClassNeedRow(BaseModel):
    code: str
    title: str
    teacher: str
    status: str                 # needs-plan | watch | strong | no-data
    mean: float | None = None
    issues: list[str]
    active_plan: str | None = None
    drafts_waiting: int = 0


class DraftRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ClassPlanPatch(BaseModel):
    status: str = Field(pattern="^(completed|retired)$")
    outcome: str | None = Field(default=None, max_length=2000)


# ---- study plans (one student, one class) -------------------------------------
class StudyClassRow(BaseModel):
    code: str
    title: str
    teacher: str
    pct: float
    class_pct: float | None = None
    needs_plan: bool
    findings: list[str] = []
    active_plan_id: int | None = None
    drafts_waiting: int = 0
    latest_run: DraftRunOut | None = None


class StudyPlanOut(BaseModel):
    id: int
    student_sid: str
    course_code: str
    title: str
    diagnosis: str
    focus_strands: list[str]
    sessions: list[str]
    catch_up: list[dict]
    goal: str
    owner: str
    status: str
    outcome: str | None = None
    opened_on: date
    review_on: date | None = None
    closed_on: date | None = None
    run_id: int | None = None
    progress: list[dict] = []


class StudentStudyOut(BaseModel):
    sid: str
    classes: list[StudyClassRow]
    plans: list[StudyPlanOut]
    drafts: list[PlanDraftOut]
