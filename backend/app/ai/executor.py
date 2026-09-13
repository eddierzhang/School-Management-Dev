"""Applying an approved proposal.

The agent proposed it; a person approved it; this code performs it. Every handler
re-validates against current state rather than trusting the payload, because time
passes between a proposal and its approval — a seat fills, a plan is opened, an
item is counted. A proposal that has gone stale is refused, not forced through.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..class_plans import adopt
from .. import study_plans
from ..config import get_settings
from ..models import Course, Enrollment, InventoryItem, Intervention, Proposal, Student
from ..stock import add_item, new_item_problem
from ..timetable import SchedulingError, open_section

settings = get_settings()


class ApplyError(RuntimeError):
    """The proposal can no longer be applied. The reason is shown to the user."""


def _by(p: Proposal) -> str:
    """The approver's name, for records that say who owns or authorised a change."""
    return getattr(p, "_approver_name", None) or p.decided_by or "Staff"


def _apply_requisition(db: Session, p: Proposal) -> str:
    skus = p.payload.get("skus") or []
    items = db.scalars(select(InventoryItem).where(InventoryItem.sku.in_(skus))).all()
    if not items:
        raise ApplyError("None of the proposed SKUs are in the stockroom any more.")
    already = [i.sku for i in items if i.requisitioned]
    for i in items:
        i.requisitioned = True
    cost = sum(max(0, i.par - i.on_hand) * i.unit_cost for i in items)
    note = f"{len(items)} item(s) added to the open requisition (~${cost:,.2f} to par)."
    return note + (f" {len(already)} were already on it." if already else "")


def _apply_reorder_point(db: Session, p: Proposal) -> str:
    item = db.scalar(select(InventoryItem).where(InventoryItem.sku == p.payload.get("sku")))
    if item is None:
        raise ApplyError("That stockroom item no longer exists.")
    new = int(p.payload.get("new_reorder_point", item.reorder_point))
    if not 0 <= new <= item.par:
        raise ApplyError(f"Reorder point {new} is outside 0–{item.par} (the par level) for {item.sku}.")
    old, item.reorder_point = item.reorder_point, new
    return f"{item.name}: reorder point {old} → {new}."


def _apply_new_item(db: Session, p: Proposal) -> str:
    d = p.payload
    problem = new_item_problem(db, d["sku"], d["name"], int(d["reorder_point"]), int(d["par"]),
                               d.get("linked_courses") or [])
    if problem:
        raise ApplyError(problem.message + " The stockroom changed since this was proposed.")
    # A new item starts with an empty shelf, so it goes straight onto the requisition.
    item = add_item(db, sku=d["sku"], name=d["name"], category=d["category"], unit=d.get("unit") or "unit",
                    on_hand=0, reorder_point=int(d["reorder_point"]), par=int(d["par"]),
                    supplier=d["supplier"], unit_cost=float(d["unit_cost"]),
                    linked_courses=d.get("linked_courses") or [], requisitioned=True)
    return (f"Added {item.name} ({item.sku}) to the stockroom and put {item.par} on the requisition "
            f"(~${item.par * item.unit_cost:,.2f}).")


def _apply_new_section(db: Session, p: Proposal) -> str:
    code = p.payload["course_code"]
    try:
        section, moved = open_section(
            db, code, period=int(p.payload["period"]), room=p.payload["room"],
            teacher=p.payload.get("teacher"), capacity=p.payload.get("seats"),
            move_from_waitlist=int(p.payload.get("move_from_waitlist") or 0))
    except SchedulingError as e:
        raise ApplyError(f"{e} The timetable may have changed since this was proposed.") from e
    return (f"Created {section.code} in {section.room}, period {section.period}, "
            f"{section.capacity} seats — {moved} moved off the waitlist.")


def _apply_capacity_change(db: Session, p: Proposal) -> str:
    c = db.scalar(select(Course).where(Course.code == p.payload.get("course_code")))
    if c is None:
        raise ApplyError("That class is no longer in the catalogue.")
    new = int(p.payload["new_capacity"])
    enrolled = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == c.id, Enrollment.status == "enrolled")).all())
    if new < enrolled:
        raise ApplyError(f"{c.code} now has {enrolled} students enrolled, so the cap cannot drop to {new}.")
    old, c.capacity = c.capacity, new
    return f"{c.code} capacity {old} → {new}."


def _apply_support_plan(db: Session, p: Proposal) -> str:
    sid = p.payload["student_sid"]
    st = db.scalar(select(Student).where(Student.sid == sid))
    if st is None:
        raise ApplyError(f"{sid} is no longer on the roll.")
    kind = p.payload["kind"]
    if db.scalar(select(Intervention).where(Intervention.student_id == st.id,
                                            Intervention.kind == kind,
                                            Intervention.status == "active")):
        raise ApplyError(f"{st.name} already has an active {kind} plan — opened since this was proposed.")
    course = None
    if p.payload.get("course_code"):
        course = db.scalar(select(Course).where(Course.code == p.payload["course_code"]))
    db.add(Intervention(student_id=st.id, course_id=course.id if course else None, kind=kind,
                        title=p.payload["title"], rationale=p.payload.get("rationale", ""),
                        owner=f"{_by(p)} (from an agent proposal)", status="active",
                        opened_on=settings.today, review_on=settings.today + timedelta(days=14)))
    return f"Opened a {kind} plan for {st.name}."


def _apply_budget_transfer(db: Session, p: Proposal) -> str:
    from ..finance import transfer_problem
    from ..models import BudgetLine, BudgetTransfer

    src, dst, amount = p.payload["from_line"], p.payload["to_line"], float(p.payload["amount"])
    problem = transfer_problem(db, src, dst, amount)
    if problem:
        raise ApplyError(problem + " The budget changed since this was proposed.")
    lines = {ln.code: ln for ln in db.scalars(select(BudgetLine).where(BudgetLine.code.in_([src, dst]))).all()}
    db.add(BudgetTransfer(from_line_id=lines[src].id, to_line_id=lines[dst].id, amount=amount,
                          reason=p.reason or "", approved_by=f"{_by(p)} (agent proposal)"))
    return f"Moved ${amount:,.2f} from {src} to {dst}."


def _apply_transaction_review(db: Session, p: Proposal) -> str:
    from ..models import Transaction

    t = db.get(Transaction, int(p.payload["transaction_id"]))
    if t is None:
        raise ApplyError("That transaction no longer exists.")
    if t.review_status != "clear":
        raise ApplyError(f"Transaction #{t.id} is already {t.review_status}.")
    t.review_status = "flagged"
    t.review_note = p.payload.get("concern", "")
    return f"Transaction #{t.id} ({t.vendor}, ${t.amount:,.2f}) is held for review."


def _apply_budget_line(db: Session, p: Proposal) -> str:
    from ..finance import FISCAL_YEAR, new_line_problem
    from ..models import BudgetLine, BudgetTransfer

    d = p.payload
    problem = new_line_problem(db, d["code"], d["name"], d["department"], d["category"],
                               d["from_line"], float(d["amount"]))
    if problem:
        raise ApplyError(problem + " The budget changed since this was proposed.")
    src = db.scalar(select(BudgetLine).where(BudgetLine.code == d["from_line"]))
    owner = next((ln.owner for ln in db.scalars(select(BudgetLine).where(
        BudgetLine.department == d["department"])).all() if ln.owner), "Business office")
    # Opened at zero and funded by a transfer, so the approved allocations stay untouched.
    line = BudgetLine(code=d["code"], name=d["name"], department=d["department"], category=d["category"],
                      fiscal_year=FISCAL_YEAR, allocated=0.0, owner=owner)
    db.add(line)
    db.flush()
    db.add(BudgetTransfer(from_line_id=src.id, to_line_id=line.id, amount=float(d["amount"]),
                          reason=f"Opening {d['code']}: {p.reason or ''}".strip(),
                          approved_by=f"{_by(p)} (agent proposal)"))
    return f"Opened {d['code']} ({d['name']}) with ${float(d['amount']):,.2f} from {d['from_line']}."


def _apply_budget_revision(db: Session, p: Proposal) -> str:
    from ..finance import revision_problem
    from ..models import BudgetLine, BudgetTransfer

    moves = p.payload["moves"]
    problem = revision_problem(db, moves)
    if problem:
        raise ApplyError(problem + " The budget changed since this was proposed, so none of it was applied.")
    ids = {ln.code: ln.id for ln in db.scalars(select(BudgetLine)).all()}
    for m in moves:
        db.add(BudgetTransfer(from_line_id=ids[m["from_line"]], to_line_id=ids[m["to_line"]],
                              amount=float(m["amount"]), reason=f"Budget revision #{p.id}: {p.reason or ''}".strip(),
                              approved_by=f"{_by(p)} (agent proposal)"))
    total = sum(float(m["amount"]) for m in moves)
    return f"Budget revised: ${total:,.2f} moved in {len(moves)} transfers."


def _apply_class_plan(db: Session, p: Proposal) -> str:
    try:
        plan = adopt(db, run_id=p.run_id, proposal_id=p.id, **{k: p.payload[k] for k in (
            "course_code", "title", "diagnosis", "focus_strands", "actions", "goal")})
    except ValueError as e:
        raise ApplyError(str(e)) from e
    return (f"Adopted an improvement plan for {plan.course_code}, owned by {plan.owner}; "
            f"review on {plan.review_on:%b} {plan.review_on.day}.")


def _apply_study_plan(db: Session, p: Proposal) -> str:
    try:
        plan = study_plans.adopt(db, run_id=p.run_id, proposal_id=p.id, **{k: p.payload.get(k) or [] if k in (
            "focus_strands", "sessions", "catch_up_assignments") else p.payload[k] for k in (
            "student_sid", "course_code", "title", "diagnosis", "focus_strands", "sessions",
            "catch_up_assignments", "goal")})
    except ValueError as e:
        raise ApplyError(str(e)) from e
    return (f"Adopted a study plan for {plan.student_sid} in {plan.course_code}, owned by {plan.owner}; "
            f"review on {plan.review_on:%b} {plan.review_on.day}.")


HANDLERS = {
    "requisition": _apply_requisition,
    "reorder_point": _apply_reorder_point,
    "new_item": _apply_new_item,
    "new_section": _apply_new_section,
    "capacity_change": _apply_capacity_change,
    "support_plan": _apply_support_plan,
    "budget_transfer": _apply_budget_transfer,
    "transaction_review": _apply_transaction_review,
    "class_plan": _apply_class_plan,
    "budget_line": _apply_budget_line,
    "budget_revision": _apply_budget_revision,
    "study_plan": _apply_study_plan,
}


def apply_proposal(db: Session, p: Proposal, by_email: str | None = None, by_name: str | None = None) -> str:
    if p.status != "pending":
        raise ApplyError(f"This proposal was already {p.status}.")
    handler = HANDLERS.get(p.kind)
    if handler is None:
        raise ApplyError(f"No way to apply a proposal of kind {p.kind!r}.")
    p.decided_by = by_email
    p._approver_name = by_name
    result = handler(db, p)
    p.status = "approved"
    p.result = result
    p.decided_at = datetime.utcnow()
    db.commit()
    return result


def reject_proposal(db: Session, p: Proposal, note: str | None = None, by_email: str | None = None) -> None:
    if p.status != "pending":
        raise ApplyError(f"This proposal was already {p.status}.")
    p.status = "rejected"
    p.result = note or "Rejected by a person."
    p.decided_at = datetime.utcnow()
    p.decided_by = by_email
    db.commit()
