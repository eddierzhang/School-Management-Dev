"""Stock status, in one place.

The API, the interface and the stockroom agent all need to agree on what "low"
means. Three copies of that rule would drift, and an agent proposing an order for
something the screen calls healthy is worse than either being wrong alone.

The bands mirror the registrar console's, so the two halves of the project
describe the same stockroom the same way:

    critical       at or below 55% of the reorder point — nearly out
    below reorder  at or below the reorder point — the flag that triggers ordering
    watch          within 25% above the reorder point — heading that way
    stocked        everything else
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Course, Enrollment, InventoryItem


@dataclass
class StockStatus:
    kind: str      # critical | serious | warning | good
    label: str
    ratio: float   # on hand as a fraction of par, for the meter
    needs_attention: bool


def status_of(item: InventoryItem) -> StockStatus:
    par = max(1, item.par or 1)
    on_hand, reorder = item.on_hand or 0, item.reorder_point or 0
    if on_hand <= reorder * 0.55:
        kind, label = "critical", "Nearly out"
    elif on_hand <= reorder:
        kind, label = "serious", "Below reorder"
    elif on_hand <= reorder * 1.25:
        kind, label = "warning", "Watch"
    else:
        kind, label = "good", "Stocked"
    return StockStatus(kind=kind, label=label,
                       ratio=min(1.0, max(0.0, on_hand / par)),
                       needs_attention=kind in ("critical", "serious"))


def short_by(item: InventoryItem) -> int:
    """Units needed to bring this item back up to par."""
    return max(0, (item.par or 0) - (item.on_hand or 0))


def cost_to_par(item: InventoryItem) -> float:
    return round(short_by(item) * (item.unit_cost or 0.0), 2)


def enrolment_by_course(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = db.execute(
        select(Course.code, Enrollment.id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.status == "enrolled")
    ).all()
    for code, _ in rows:
        counts[code] = counts.get(code, 0) + 1
    return counts


def students_depending_on(item: InventoryItem, enrolment: dict[str, int]) -> int:
    """How many students sit in a class that consumes this item.

    The link is what turns a stockroom into an operational signal: a spike in
    demand for Forensic Science is visible here before the class runs short.
    """
    return sum(enrolment.get(code, 0) for code in (item.linked_courses or []))
