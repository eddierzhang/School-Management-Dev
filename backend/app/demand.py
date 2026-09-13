"""Which classes students want, in one place.

The formula is the registrar console's, published so staff can argue with it
rather than trust a black box, and kept identical so the two halves of the
project rank the same classes the same way:

    demand = 100 × (0.40·fill + 0.35·pressure + 0.25·velocity)

    fill      enrolled ÷ capacity                              capped at 1
    pressure  waitlist ÷ capacity                              capped at 1
    velocity  signups in the last two weeks ÷ (capacity × 0.6) capped at 1

Demand is judged per *class*, not per section. A class is every section sharing a
base code (MAT-150, MAT-150.B, …), with seats, waitlists and signups pooled. Once
a second section absorbs a waitlist, the class reads as relieved rather than one
section still looking over-subscribed and the new one looking empty.

    over-subscribed  70+      the waitlist would fill another section
    high demand      52–69
    healthy          32–51
    seats to fill    below 32 promote it, or ask whether it should run again
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Course, Enrollment

W_FILL, W_PRESSURE, W_VELOCITY = 0.40, 0.35, 0.25
VELOCITY_SCALE = 0.6
RECENT_WEEKS = 2
FORMULA = "demand = 100 × (0.40·seats filled + 0.35·waitlist÷capacity + 0.25·signups in 2 wk÷(capacity×0.6))"

# (floor, kind, label) — highest first. Kinds are the interface's status vocabulary,
# coloured by what needs doing rather than by how popular a class is: a healthy
# class is the good outcome, and both extremes ask the registrar for something.
BANDS: list[tuple[int, str, str]] = [
    (70, "serious", "Over-subscribed"),
    (52, "accent", "High demand"),
    (32, "good", "Healthy"),
    (0, "warning", "Seats to fill"),
]
# A waitlist at least this share of a section is enough students to open another.
SECTION_WORTH_OPENING = 0.5
# Below this share of seats filled, a class is under-enrolled whatever its score.
UNDER_ENROLLED = 0.55


def base_code(code: str) -> str:
    return code.split(".")[0]


def band_of(score: int) -> tuple[str, str]:
    return next((kind, label) for floor, kind, label in BANDS if score >= floor)


@dataclass
class SectionCounts:
    code: str
    title: str
    teacher: str
    period: int
    room: str
    capacity: int
    enrolled: int
    waitlist: int
    signups: list[int]


@dataclass
class ClassDemand:
    code: str
    title: str
    dept: str
    sections: list[SectionCounts]
    enrolled: int
    capacity: int
    waitlist: int
    signups: list[int]
    recent_signups: int
    prior_signups: int
    fill: float
    pressure: float
    velocity: float
    score: int
    kind: str
    label: str
    action: str
    reasons: list[str] = field(default_factory=list)

    @property
    def trend(self) -> str:
        if self.recent_signups > self.prior_signups:
            return "rising"
        if self.recent_signups < self.prior_signups:
            return "falling"
        return "level"


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _pooled_signups(sections: list[SectionCounts]) -> list[int]:
    """Week-by-week sum, aligned on the most recent week."""
    weeks = max((len(s.signups) for s in sections), default=0)
    out = [0] * weeks
    for s in sections:
        offset = weeks - len(s.signups)
        for i, n in enumerate(s.signups):
            out[offset + i] += int(n or 0)
    return out


def score(enrolled: int, capacity: int, waitlist: int, signups: list[int]) -> tuple[int, float, float, float]:
    cap = max(1, capacity)
    recent = sum(signups[-RECENT_WEEKS:])
    fill = _clamp(enrolled / cap)
    pressure = _clamp(waitlist / cap)
    velocity = _clamp(recent / (cap * VELOCITY_SCALE))
    return round(100 * (W_FILL * fill + W_PRESSURE * pressure + W_VELOCITY * velocity)), fill, pressure, velocity


def _action(score: int, fill: float, waitlist: int, largest_section: int, trend: str) -> str:
    if waitlist and waitlist >= largest_section * SECTION_WORTH_OPENING:
        return "open-section"
    if waitlist:
        return "raise-capacity"
    if score < BANDS[-2][0] or fill < UNDER_ENROLLED:
        return "promote" if trend != "falling" else "review"
    return "none"


def _reasons(d: ClassDemand, largest_section: int) -> list[str]:
    out = []
    if d.waitlist:
        out.append(f"{d.waitlist} waiting — {round(100 * d.waitlist / max(1, largest_section))}% of a section")
    out.append(f"{d.enrolled} of {d.capacity} seats filled")
    if d.recent_signups or d.prior_signups:
        noun = "signup" if d.recent_signups == 1 else "signups"
        out.append(f"{d.recent_signups} {noun} in the last two weeks, {d.prior_signups} the two before")
    return out


def section_counts(db: Session) -> list[SectionCounts]:
    enrolled: dict[int, int] = {}
    waiting: dict[int, int] = {}
    for course_id, status in db.execute(select(Enrollment.course_id, Enrollment.status)).all():
        bucket = enrolled if status == "enrolled" else waiting if status == "waitlist" else None
        if bucket is not None:
            bucket[course_id] = bucket.get(course_id, 0) + 1
    return [SectionCounts(code=c.code, title=c.title, teacher=c.teacher, period=c.period, room=c.room,
                          capacity=c.capacity, enrolled=enrolled.get(c.id, 0),
                          waitlist=waiting.get(c.id, 0), signups=[int(n or 0) for n in (c.signups or [])])
            for c in db.scalars(select(Course).order_by(Course.code)).all()]


def class_demand(db: Session) -> list[ClassDemand]:
    """Every class, most wanted first."""
    groups: dict[str, list[SectionCounts]] = {}
    depts: dict[str, str] = {c.code: c.dept for c in db.scalars(select(Course)).all()}
    for s in section_counts(db):
        groups.setdefault(base_code(s.code), []).append(s)

    out = []
    for code, sections in groups.items():
        enrolled = sum(s.enrolled for s in sections)
        capacity = sum(s.capacity for s in sections)
        waitlist = sum(s.waitlist for s in sections)
        signups = _pooled_signups(sections)
        value, fill, pressure, velocity = score(enrolled, capacity, waitlist, signups)
        kind, label = band_of(value)
        recent = sum(signups[-RECENT_WEEKS:])
        prior = sum(signups[-2 * RECENT_WEEKS:-RECENT_WEEKS])
        largest = max(s.capacity for s in sections)
        d = ClassDemand(code=code, title=sections[0].title, dept=depts.get(sections[0].code, ""),
                        sections=sections, enrolled=enrolled, capacity=capacity, waitlist=waitlist,
                        signups=signups, recent_signups=recent, prior_signups=prior,
                        fill=round(fill, 3), pressure=round(pressure, 3), velocity=round(velocity, 3),
                        score=value, kind=kind, label=label, action="none")
        d.action = _action(value, fill, waitlist, largest, d.trend)
        d.reasons = _reasons(d, largest)
        out.append(d)
    out.sort(key=lambda d: (-d.score, d.code))
    return out
