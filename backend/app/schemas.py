"""Wire shapes. These mirror the analytics dataclasses so the frontend has one
contract to type against, and so an internal refactor cannot silently change
the API.
"""
from __future__ import annotations

from datetime import date

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
    band: str
    absence_rate: float
    open_interventions: int
    top_reason: str | None = None
    course_count: int = 0
    lowest_course: str | None = None
    lowest_pct: float | None = None


class StudentDetail(Base):
    sid: str
    name: str
    grade: int
    homeroom: str
    guardian_name: str | None = None
    guardian_email: str | None = None
    struggle_index: int
    excel_index: int
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
    class_mean: float | None = None
    below_support: int = 0
    excelling: int = 0
    weakest_skill: str | None = None
    weakest_skill_mean: float | None = None


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


class CourseDetail(Base):
    course: CourseRow
    students: list[CourseStudentRow]
    skills: list[SkillGapOut]
    distribution: list[DistributionBucket]


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
