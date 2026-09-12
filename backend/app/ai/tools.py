"""What each agent can see and what it can propose.

Two rules shape every tool here.

**Results are small.** A 4B model handed 60 rows of JSON loses the thread. Every
list tool caps its output and returns only the fields the decision needs. The cap
is reported in the payload so the agent knows it is looking at a slice.

**No tool writes.** The `propose_*` tools record an intent on the run and return a
receipt. Nothing reaches the database until a person approves it.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import build_signals, skill_gaps
from ..class_plans import (active_plan, all_performance, canonical_strands, performance,
                           miscounted, unaddressed_causes, uncited_percentages, unknown_strands)
from .. import study_plans as SP
from ..config import get_settings
from ..models import Course, Enrollment, InventoryItem, Intervention, Proposal, Student
from ..stock import cost_to_par, short_by, status_of
from ..timetable import clashes
from .toolkit import Tool, ToolError

settings = get_settings()
LIST_CAP = 12


def _capped(rows: list, cap: int = LIST_CAP) -> dict:
    out = {"items": rows[:cap], "returned": min(len(rows), cap), "total": len(rows)}
    if len(rows) > cap:
        out["note"] = f"Showing the {cap} most important of {len(rows)}."
    return out


def _propose(ctx: dict, kind: str, summary: str, reason: str, payload: dict, evidence: list) -> dict:
    ctx.setdefault("proposals", []).append(
        {"kind": kind, "summary": summary, "reason": reason, "payload": payload, "evidence": evidence}
    )
    return {"recorded": True, "kind": kind, "summary": summary,
            "note": "Proposal recorded for human approval. Nothing has been changed. "
                    "If you have no further proposals, give your final summary."}


# ===================== stockroom =====================================
def _item_row(i: InventoryItem) -> dict:
    """Same status rule the API and the interface use — see app/stock.py."""
    st = status_of(i)
    return {"sku": i.sku, "name": i.name, "category": i.category, "on_hand": i.on_hand,
            "reorder_point": i.reorder_point, "par": i.par, "unit": i.unit,
            "status": st.label, "short_by": short_by(i), "unit_cost": round(i.unit_cost, 2),
            "for_courses": list(i.linked_courses or []), "already_requisitioned": i.requisitioned}


def list_low_stock(db: Session, ctx: dict, category: str | None = None) -> dict:
    stmt = select(InventoryItem).where(InventoryItem.on_hand <= InventoryItem.reorder_point)
    if category and category.lower() not in ("all", "any", "*"):
        stmt = stmt.where(InventoryItem.category == category)
    rows = sorted(db.scalars(stmt).all(), key=lambda i: i.on_hand - i.reorder_point)
    return _capped([_item_row(i) for i in rows])


def get_item(db: Session, ctx: dict, sku: str) -> dict:
    item = db.scalar(select(InventoryItem).where(InventoryItem.sku == sku.strip().upper()))
    if item is None:
        known = [i.sku for i in db.scalars(select(InventoryItem).limit(8)).all()]
        raise ToolError(f"No stockroom item with SKU {sku!r}. Examples of real SKUs: {', '.join(known)}.")
    return _item_row(item)


def list_items_for_course(db: Session, ctx: dict, course_code: str) -> dict:
    code = course_code.strip().upper()
    course = db.scalar(select(Course).where(Course.code == code))
    if course is None:
        raise ToolError(f"No class with code {course_code!r}. Use list_sections to see real course codes.")
    enrolled = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == course.id, Enrollment.status == "enrolled")).all())
    rows = [_item_row(i) | {"enrolled_in_class": enrolled,
                            "covers_students": i.on_hand if i.on_hand < enrolled else enrolled,
                            "short_for_class": max(0, enrolled - i.on_hand)}
            for i in db.scalars(select(InventoryItem)).all()
            if code in (i.linked_courses or [])]
    return {"course": code, "title": course.title, "enrolled": enrolled} | _capped(rows)


def propose_requisition(db: Session, ctx: dict, skus: list, reason: str) -> dict:
    found, missing = [], []
    for raw in skus:
        sku = str(raw).strip().upper()
        item = db.scalar(select(InventoryItem).where(InventoryItem.sku == sku))
        (found.append(item) if item else missing.append(sku))
    if missing:
        raise ToolError(f"These SKUs do not exist: {', '.join(missing)}. "
                        "Call list_low_stock or get_item first and use exact SKUs.")
    if not found:
        raise ToolError("No SKUs given. Pass at least one real SKU.")
    cost = sum(cost_to_par(i) for i in found)
    return _propose(ctx, "requisition",
                    f"Order {len(found)} item(s) to par — about ${cost:,.2f}", reason,
                    {"skus": [i.sku for i in found]},
                    [{"sku": i.sku, "name": i.name, "on_hand": i.on_hand,
                      "reorder_point": i.reorder_point, "to_par": short_by(i)} for i in found])


def propose_reorder_point(db: Session, ctx: dict, sku: str, new_reorder_point: int, reason: str) -> dict:
    item = db.scalar(select(InventoryItem).where(InventoryItem.sku == sku.strip().upper()))
    if item is None:
        raise ToolError(f"No stockroom item with SKU {sku!r}.")
    if not 0 <= new_reorder_point <= item.par:
        raise ToolError(f"Reorder point must be between 0 and the par level ({item.par}). Got {new_reorder_point}.")
    return _propose(ctx, "reorder_point",
                    f"{item.name}: reorder point {item.reorder_point} → {new_reorder_point}", reason,
                    {"sku": item.sku, "new_reorder_point": int(new_reorder_point)},
                    [_item_row(item)])


# ===================== registrar (scheduling) =========================
def _section_row(db: Session, c: Course) -> dict:
    enrolled = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == c.id, Enrollment.status == "enrolled")).all())
    waiting = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == c.id, Enrollment.status == "waitlist")).all())
    return {"code": c.code, "title": c.title, "teacher": c.teacher, "period": c.period,
            "room": c.room, "enrolled": enrolled, "capacity": c.capacity,
            "length": c.length, "prerequisite": c.prerequisite,
            "seats_open": max(0, c.capacity - enrolled), "waitlist": waiting}


def list_sections(db: Session, ctx: dict, only_problems: bool = False) -> dict:
    rows = [_section_row(db, c) for c in db.scalars(select(Course).order_by(Course.code)).all()]
    if only_problems:
        rows = [r for r in rows if r["waitlist"] > 0 or r["enrolled"] < r["capacity"] * 0.55]
    rows.sort(key=lambda r: -r["waitlist"])
    return _capped(rows)


def find_schedule_conflicts(db: Session, ctx: dict) -> dict:
    """Deterministic. The model is told the answer, never asked to work it out."""
    by_teacher: dict[tuple, list[str]] = defaultdict(list)
    by_room: dict[tuple, list[str]] = defaultdict(list)
    for c in db.scalars(select(Course)).all():
        if not c.period:
            continue
        by_teacher[(c.teacher, c.period)].append(c.code)
        by_room[(c.room, c.period)].append(c.code)
    clashes = [{"type": "teacher", "who": t, "period": p, "sections": codes}
               for (t, p), codes in sorted(by_teacher.items()) if len(codes) > 1]
    clashes += [{"type": "room", "who": r, "period": p, "sections": codes}
                for (r, p), codes in sorted(by_room.items()) if len(codes) > 1]
    return _capped(clashes)


def list_waitlist_pressure(db: Session, ctx: dict) -> dict:
    rows = [r for r in (_section_row(db, c) for c in db.scalars(select(Course)).all()) if r["waitlist"] > 0]
    for r in rows:
        r["waitlist_vs_capacity"] = round(r["waitlist"] / max(1, r["capacity"]), 2)
        r["fills_a_section"] = r["waitlist"] >= r["capacity"] * 0.5
    rows.sort(key=lambda r: -r["waitlist"])
    return _capped(rows)


def find_open_rooms(db: Session, ctx: dict, period: int) -> dict:
    used, rooms = set(), set()
    for c in db.scalars(select(Course)).all():
        rooms.add(c.room)
        if c.period == period:
            used.add(c.room)
    free = sorted(rooms - used)
    return {"period": period, "free_rooms": free[:LIST_CAP], "rooms_in_use": sorted(used)[:LIST_CAP]}


def propose_new_section(db: Session, ctx: dict, course_code: str, period: int, room: str,
                        seats: int, reason: str, teacher: str | None = None,
                        move_from_waitlist: int = 0) -> dict:
    code = course_code.strip().upper()
    src = db.scalar(select(Course).where(Course.code == code))
    if src is None:
        raise ToolError(f"No class with code {course_code!r}. Call list_sections for real codes.")
    waiting = len(db.scalars(select(Enrollment).where(
        Enrollment.course_id == src.id, Enrollment.status == "waitlist")).all())
    if waiting == 0:
        raise ToolError(f"{code} has nobody on its waitlist, so a second section has no one to take. "
                        "Call list_waitlist_pressure to find sections that do.")
    found = clashes(db, int(period), room, teacher or src.teacher)
    if found:
        raise ToolError("; ".join(found) + f". Call find_open_rooms(period={period}) for a free room, "
                        "or pass a different teacher or period.")
    move = max(0, min(int(move_from_waitlist), waiting, int(seats)))
    return _propose(ctx, "new_section",
                    f"Open a second section of {src.title} ({code}) in {room}, period {period}", reason,
                    {"course_code": code, "period": int(period), "room": room, "seats": int(seats),
                     "teacher": teacher or src.teacher, "move_from_waitlist": move},
                    [_section_row(db, src)])


def propose_capacity_change(db: Session, ctx: dict, course_code: str, new_capacity: int, reason: str) -> dict:
    code = course_code.strip().upper()
    c = db.scalar(select(Course).where(Course.code == code))
    if c is None:
        raise ToolError(f"No class with code {course_code!r}.")
    row = _section_row(db, c)
    if new_capacity < row["enrolled"]:
        raise ToolError(f"Capacity cannot go below the {row['enrolled']} students already enrolled in {code}.")
    if new_capacity == c.capacity:
        raise ToolError(f"{code} already has a capacity of {c.capacity}. Propose a different number or nothing.")
    return _propose(ctx, "capacity_change",
                    f"{code} capacity {c.capacity} → {new_capacity}", reason,
                    {"course_code": code, "new_capacity": int(new_capacity)}, [row])


# ===================== student support ================================
def list_flagged_students(db: Session, ctx: dict, band: str | None = None) -> dict:
    sigs = build_signals(db)
    wanted = {"needs-plan", "watch"} if band in (None, "", "all") else {band}
    rows = []
    for s in sorted(sigs.values(), key=lambda s: -s.struggle_index):
        if s.band not in wanted:
            continue
        worst = s.courses[0] if s.courses else None
        rows.append({"sid": s.sid, "grade": s.grade, "band": s.band,
                     "struggle": s.struggle_index, "excelling": s.excel_index,
                     "open_plans": s.open_interventions,
                     "worst_class": worst.course_code if worst else None,
                     "worst_grade_pct": worst.pct if worst else None,
                     "top_reason": s.reasons[0].label if s.reasons else None})
    return _capped(rows)


def get_student(db: Session, ctx: dict, sid: str) -> dict:
    sigs = build_signals(db)
    s = sigs.get(sid.strip().upper())
    if s is None:
        raise ToolError(f"No student with ID {sid!r}. Call list_flagged_students for real student IDs.")
    return {
        "sid": s.sid, "grade": s.grade, "band": s.band,
        "struggle": s.struggle_index, "excelling": s.excel_index,
        "absent_days": s.absences, "school_days": s.days_counted,
        "open_plans": s.open_interventions,
        "classes": [{"code": c.course_code, "pct": c.pct, "trend": c.delta,
                     "missing": c.missing, "of": c.graded_items} for c in s.courses[:6]],
        "weakest_strands": [{"strand": k.skill, "pct": k.pct, "class": k.course_code}
                            for k in s.weakest_skills[:3]],
        "strongest_strands": [{"strand": k.skill, "pct": k.pct, "class": k.course_code}
                              for k in s.strongest_skills[:2]],
        "reasons": [r.label for r in s.reasons[:5]],
        "suggested": [{"title": r.title, "kind": r.kind, "class": r.course_code}
                      for r in s.recommendations[:3]],
    }


def list_skill_gaps(db: Session, ctx: dict, course_code: str | None = None) -> dict:
    gaps = skill_gaps(db)
    if course_code and course_code.lower() not in ("all", "any"):
        code = course_code.strip().upper()
        gaps = [g for g in gaps if g.course_code == code]
        if not gaps:
            raise ToolError(f"No strands found for {course_code!r}. Use a real course code, or omit it.")
    return _capped([{"class": g.course_code, "strand": g.skill, "class_mean": g.class_mean,
                     "below_line": g.students_below, "cohort": g.cohort,
                     "reteach": g.share_below >= 0.4} for g in gaps])


PLAN_KINDS = ["tutoring", "homework-recovery", "check-in", "attendance-plan", "family-contact", "enrichment"]


def propose_support_plan(db: Session, ctx: dict, student_sid: str, kind: str, title: str,
                         rationale: str, course_code: str | None = None) -> dict:
    sid = student_sid.strip().upper()
    st = db.scalar(select(Student).where(Student.sid == sid))
    if st is None:
        raise ToolError(f"No student with ID {student_sid!r}. Call list_flagged_students first.")
    if kind not in PLAN_KINDS:
        raise ToolError(f"kind must be one of: {', '.join(PLAN_KINDS)}. Got {kind!r}.")
    if course_code:
        code = course_code.strip().upper()
        if db.scalar(select(Course).where(Course.code == code)) is None:
            raise ToolError(f"No class with code {course_code!r}. Omit course_code or use a real one.")
        course_code = code
    existing = db.scalar(select(Intervention).where(
        Intervention.student_id == st.id, Intervention.kind == kind, Intervention.status == "active"))
    if existing is not None:
        raise ToolError(f"{sid} already has an active {kind} plan ('{existing.title}'). "
                        "Propose a different kind of support, or move on to another student.")
    sig = build_signals(db).get(sid)
    return _propose(ctx, "support_plan", f"{kind} for {sid}: {title}", rationale,
                    {"student_sid": sid, "kind": kind, "title": title,
                     "rationale": rationale, "course_code": course_code},
                    [{"sid": sid, "band": sig.band if sig else None,
                      "struggle": sig.struggle_index if sig else None,
                      "reasons": [r.label for r in sig.reasons[:3]] if sig else []}])


# ===================== finance =======================================
def _position_row(p) -> dict:
    return {"code": p.code, "name": p.name, "department": p.department, "status": p.status_label,
            "budget": p.budget, "spent": p.spent, "committed": p.committed, "available": p.available,
            "projected_year_end": p.projected, "note": p.note}


def _lines_with_room(everything, limit: int = 4) -> list[dict]:
    from ..finance import max_giveable

    rows = [{"code": p.code, "name": p.name, "can_give_up_to": max_giveable(p)} for p in everything]
    rows = [r for r in rows if r["can_give_up_to"] > 0]
    return sorted(rows, key=lambda r: -r["can_give_up_to"])[:limit]


def list_budget_status(db: Session, ctx: dict, only_problems: bool = True) -> dict:
    from ..finance import elapsed_fraction, positions

    everything = positions(db)
    rows = [p for p in everything if p.status != "good"] if only_problems else everything
    out = _capped([_position_row(p) for p in rows])
    # Observed: shown only the problem lines, the model tried four transfers from
    # lines that were themselves at risk. It needs to see where the room is.
    out["lines_with_room"] = _lines_with_room(everything)
    # Where money is necessary, and how much: overruns and low stock nobody has ordered.
    from ..finance import needs
    out["lines_needing_money"] = [{"code": n.code, "needs": round(n.need), "why": n.reasons}
                                  for n in needs(db)[:6]]
    out["year_elapsed_pct"] = round(elapsed_fraction() * 100, 1)
    out["how_to_read"] = ("lines_needing_money says where money is necessary and how much. "
                          "lines_with_room says which lines can give, and the most each can give.")
    return out


def get_budget_line(db: Session, ctx: dict, code: str) -> dict:
    from ..finance import positions
    from ..models import BudgetLine, Transaction

    code = str(code).strip().upper()
    pos = next((p for p in positions(db) if p.code == code), None)
    if pos is None:
        raise ToolError(f"No budget line {code}. Call list_budget_status for real codes.")
    ln = db.scalar(select(BudgetLine).where(BudgetLine.code == code))
    txns = db.scalars(select(Transaction).where(Transaction.line_id == ln.id)
                      .order_by(Transaction.posted_on.desc())).all()
    return _position_row(pos) | {
        "commitments": pos.commitments[:6],
        "recent_transactions": [{"id": t.id, "posted_on": t.posted_on.isoformat(), "vendor": t.vendor,
                                 "description": t.description, "amount": t.amount,
                                 "one_time": t.one_time, "review": t.review_status}
                                for t in txns[:8]],
    }


def find_spending_anomalies(db: Session, ctx: dict) -> dict:
    from ..finance import anomalies

    rows = [a for a in anomalies(db) if a["review_status"] == "clear"]
    return _capped([{k: a[k] for k in ("transaction_id", "rule", "line", "vendor", "amount", "posted_on", "detail")}
                    for a in rows])


def propose_budget_transfer(db: Session, ctx: dict, from_line: str, to_line: str, amount: float,
                            reason: str) -> dict:
    from ..finance import positions, transfer_problem

    src, dst = str(from_line).strip().upper(), str(to_line).strip().upper()
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ToolError("amount must be a number of dollars, e.g. 1200.") from None
    problem = transfer_problem(db, src, dst, amount)
    if problem:
        donors = [d for d in _lines_with_room(positions(db)) if d["code"] != dst]
        hint = (" Lines that can give: " + "; ".join(f"{d['code']} up to ${d['can_give_up_to']:,.0f}" for d in donors)
                + ".") if donors else ""
        raise ToolError(problem + hint)
    by_code = {p.code: p for p in positions(db)}
    if by_code[dst].status not in ("critical", "serious"):
        raise ToolError(f"{dst} is {by_code[dst].status_label.lower()}. Transfers go to lines that are "
                        "Over budget or At risk — call list_budget_status to find them.")
    need = max(0.0, by_code[dst].projected - by_code[dst].budget)
    if amount > max(need * 1.25, 250):
        raise ToolError(f"{dst} needs about ${need:,.0f} to cover its projection. Propose no more than "
                        f"${max(need * 1.25, 250):,.0f}.")
    for p in ctx.get("proposals", []):
        if p["kind"] == "budget_transfer" and p["payload"]["to_line"] == dst:
            raise ToolError(f"You already proposed a transfer into {dst} in this run.")
    return _propose(ctx, "budget_transfer",
                    f"Move ${amount:,.2f} from {src} to {dst}", reason,
                    {"from_line": src, "to_line": dst, "amount": amount},
                    [_position_row(by_code[src]), _position_row(by_code[dst])])


def propose_transaction_review(db: Session, ctx: dict, transaction_id: int, concern: str,
                               reason: str) -> dict:
    from ..finance import anomalies
    from ..models import Transaction

    try:
        tid = int(transaction_id)
    except (TypeError, ValueError):
        raise ToolError("transaction_id must be a number from find_spending_anomalies.") from None
    t = db.get(Transaction, tid)
    if t is None:
        raise ToolError(f"No transaction {tid}. Use an id from find_spending_anomalies.")
    if t.review_status != "clear":
        raise ToolError(f"Transaction {tid} is already {t.review_status}.")
    if not str(concern).strip():
        raise ToolError("concern must say what looks wrong, in one sentence.")
    rules = [a for a in anomalies(db) if a["transaction_id"] == tid]
    return _propose(ctx, "transaction_review",
                    f"Hold #{tid} for review: {t.vendor}, ${t.amount:,.2f}", reason,
                    {"transaction_id": tid, "concern": str(concern).strip()[:300]},
                    [{"id": t.id, "line": t.line.code, "vendor": t.vendor, "amount": t.amount,
                      "posted_on": t.posted_on.isoformat(), "reference": t.reference,
                      "rules": [r["rule"] + ": " + r["detail"] for r in rules]}])


DOLLARS = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")


def _uncited_dollars(text: str, figures: list[float], allowed: list[float]) -> list[str]:
    """Dollar amounts in `text` that match no figure the tools returned, and none
    the proposal itself moves. Tolerance: $1, or 2% of the figure."""
    pool = [abs(f) for f in figures + allowed if f is not None]
    bad = []
    for m in DOLLARS.finditer(text):
        v = float(m.group(1).replace(",", ""))
        if not any(abs(v - f) <= max(1.0, 0.02 * f) for f in pool):
            bad.append(m.group(0))
    return bad


def _finance_figures(db: Session) -> list[float]:
    from ..finance import max_giveable, needs, positions
    ps = positions(db)
    out: list[float] = []
    for p in ps:
        out += [p.budget, p.spent, p.committed, p.available, p.projected, p.projected - p.budget,
                p.spent + p.committed - p.budget, max_giveable(p)]
    for n in needs(db):
        out += [n.need, n.overrun, n.unfunded_stock]
    return out


def propose_new_budget_line(db: Session, ctx: dict, code: str, name: str, department: str, category: str,
                            from_line: str, amount: float, reason: str) -> dict:
    from ..finance import new_line_problem, positions
    from ..models import BudgetLine

    code, src = str(code).strip().upper(), str(from_line).strip().upper()
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ToolError("amount must be a number of dollars, e.g. 1500.") from None
    problem = new_line_problem(db, code, name, department, category, src, amount)
    if problem:
        donors = _lines_with_room(positions(db))
        hint = (" Lines that can give: " + "; ".join(f"{d['code']} up to ${d['can_give_up_to']:,.0f}" for d in donors)
                + ".") if donors and ("give" in problem or "risk" in problem) else ""
        raise ToolError(problem + hint)
    categories = sorted({ln.category for ln in db.scalars(select(BudgetLine)).all()})
    if category.strip() not in categories:
        raise ToolError(f"No category called {category!r}. Categories: {', '.join(categories)}.")
    if len(str(reason).strip()) < 30:
        raise ToolError("reason must say what the new line pays for and why it cannot come from an existing line.")
    invented = _uncited_dollars(reason, _finance_figures(db), [amount])
    if invented:
        raise ToolError(f"These amounts are not in the budget data: {', '.join(invented)}. "
                        "Cite only figures from list_budget_status or get_budget_line.")
    for p in ctx.get("proposals", []):
        if p["kind"] == "budget_line" and p["payload"]["code"] == code:
            raise ToolError(f"You already proposed opening {code} in this run.")
    by_code = {p.code: p for p in positions(db)}
    return _propose(ctx, "budget_line",
                    f"Open {code} ({name.strip()}) with ${amount:,.2f} from {src}", reason,
                    {"code": code, "name": name.strip()[:120], "department": department.strip(),
                     "category": category.strip(), "from_line": src, "amount": amount},
                    [_position_row(by_code[src])])


def propose_budget_revision(db: Session, ctx: dict, moves: list, reason: str) -> dict:
    from ..finance import needs, positions, revision_problem

    clean = []
    for i, m in enumerate(moves, 1):
        if not isinstance(m, dict):
            raise ToolError(f"Move {i} must be an object with from_line, to_line and amount.")
        missing = [k for k in ("from_line", "to_line", "amount") if m.get(k) in (None, "")]
        if missing:
            raise ToolError(f"Move {i} is missing {', '.join(missing)}. Each move needs from_line, to_line and amount.")
        try:
            amount = round(float(m["amount"]), 2)
        except (TypeError, ValueError):
            raise ToolError(f"Move {i}: amount must be a number of dollars.") from None
        clean.append({"from_line": str(m["from_line"]).strip().upper(),
                      "to_line": str(m["to_line"]).strip().upper(), "amount": amount})
    if not clean:
        raise ToolError("A revision needs at least one move: from_line, to_line and amount.")
    problem = revision_problem(db, clean)
    if problem:
        short = "; ".join(f"{n.code} needs ${n.need:,.0f}" for n in needs(db)[:6])
        donors = "; ".join(f"{d['code']} up to ${d['can_give_up_to']:,.0f}" for d in _lines_with_room(positions(db), 6))
        raise ToolError(problem + (f" Where money is needed: {short}." if short else "")
                        + (f" Lines that can give: {donors}." if donors else ""))
    invented = _uncited_dollars(reason, _finance_figures(db), [m["amount"] for m in clean])
    if invented:
        raise ToolError(f"These amounts are not in the budget data: {', '.join(invented)}. "
                        "Cite only figures from list_budget_status or get_budget_line.")
    if any(p["kind"] == "budget_revision" for p in ctx.get("proposals", [])):
        raise ToolError("You already proposed a revision in this run. Put every move in one revision.")
    total = sum(m["amount"] for m in clean)
    by_code = {p.code: p for p in positions(db)}
    involved = sorted({m["from_line"] for m in clean} | {m["to_line"] for m in clean})
    return _propose(ctx, "budget_revision",
                    f"Revise the budget: move ${total:,.2f} across {len(clean)} transfers into "
                    f"{', '.join(sorted({m['to_line'] for m in clean}))}", reason,
                    {"moves": clean}, [_position_row(by_code[c]) for c in involved])


# ===================== class improvement ===============================
def _pct_int(v: float | None) -> int | None:
    return round(v) if v is not None else None


def _class_row(p) -> dict:
    """Whole numbers throughout: a model cites what it is shown, so show it numbers
    that the plan checks in app/class_plans.py will recognise."""
    return {"code": p.code, "title": p.title, "teacher": p.teacher, "status": p.status,
            "class_average": _pct_int(p.mean), "students": p.students,
            "work_handed_in_pct": _pct_int(100 * p.completion) if p.completion is not None else None,
            "trend_points": p.trend, "weakest_strands": [s.strand for s in p.strands[:2]],
            "issues": p.issues[:3]}


def list_classes_by_need(db: Session, ctx: dict) -> dict:
    rows = []
    for p in all_performance(db):
        if p.status == "no-data":
            continue
        plan = active_plan(db, p.code)
        rows.append(_class_row(p) | {"has_active_plan": plan is not None})
    return _capped(rows) | {"note_on_status": "needs-plan first, then watch, then strong. "
                                              "A class with has_active_plan=true already has one."}


def get_class_performance(db: Session, ctx: dict, course_code: str) -> dict:
    code = course_code.strip().upper()
    p = performance(db, code)
    if p is None:
        raise ToolError(f"No class with code {course_code!r}. Call list_classes_by_need for real codes.")
    if p.status == "no-data":
        raise ToolError(f"{code} has no graded work yet, so there is nothing to plan from.")
    plan = active_plan(db, code)
    return _class_row(p) | {
        "median": _pct_int(p.median),
        "below_the_72_line": f"{p.below_line} of {p.students}",
        "improving_students": p.improving, "declining_students": p.declining,
        "students_needing_individual_plans": p.needs_plan,
        "strands": [{"strand": s.strand, "average": _pct_int(s.mean),
                     "below_line": f"{s.below_line} of {s.cohort}",
                     "share_below_pct": _pct_int(100 * s.share_below)} for s in p.strands],
        "by_kind_of_work": [{"kind": k.kind, "average": _pct_int(k.mean),
                             "handed_in_pct": _pct_int(100 * k.handed_in)} for k in p.kinds],
        "active_plan": plan.title if plan else None,
    }


def propose_class_plan(db: Session, ctx: dict, course_code: str, title: str, diagnosis: str,
                       focus_strands: list, actions: list, goal: str) -> dict:
    code = course_code.strip().upper()
    scope = ctx.get("only_course")
    if scope and code != scope:
        raise ToolError(f"This run is only for {scope}. Propose a plan for {scope}, not {code}.")
    p = performance(db, code)
    if p is None:
        raise ToolError(f"No class with code {course_code!r}. Call list_classes_by_need for real codes.")
    if p.status == "no-data":
        raise ToolError(f"{code} has no graded work yet, so there is nothing to plan from.")
    if active_plan(db, code):
        raise ToolError(f"{code} already has an active improvement plan. Choose another class, or stop.")
    if any(x["kind"] == "class_plan" and x["payload"]["course_code"] == code for x in ctx.get("proposals", [])):
        raise ToolError(f"You already proposed a plan for {code} in this run. Do not propose a second.")
    waiting = [x for x in db.scalars(select(Proposal).where(Proposal.kind == "class_plan",
                                                            Proposal.status == "pending")).all()
               if (x.payload or {}).get("course_code") == code]
    if waiting:
        raise ToolError(f"A draft plan for {code} is already waiting for approval. Stop, or choose another class.")

    strands = [str(s).strip() for s in focus_strands if str(s).strip()]
    if not 1 <= len(strands) <= 2:
        raise ToolError("focus_strands must name one or two strands from get_class_performance.")
    wrong = unknown_strands(strands, p)
    if wrong:
        raise ToolError(f"{code} does not teach: {', '.join(wrong)}. "
                        f"Its strands are: {', '.join(s.strand for s in p.strands)}.")

    steps = [str(a).strip() for a in actions if str(a).strip()]
    if not 2 <= len(steps) <= 5:
        raise ToolError("actions must list two to five separate, concrete steps.")
    short = [a for a in steps if len(a) < 20]
    if short:
        raise ToolError(f"Each action must say what happens, who does it and when. Too vague: {short[0]!r}.")
    if len({a.lower() for a in steps}) < len(steps):
        raise ToolError("Two of the actions are the same. Give distinct steps.")
    if not re.search(r"\d", goal):
        raise ToolError("The goal must be measurable: name a number to reach, e.g. 'word problems average to 72%'.")

    ignored = unaddressed_causes(steps, p)
    if ignored:
        raise ToolError(f"The plan misses a cause in the data: {ignored[0]}. Add an action for it and "
                        "propose again.")

    wrong_counts = miscounted(diagnosis, p)
    if wrong_counts:
        raise ToolError(f"These counts do not match the class data: {', '.join(wrong_counts)}. "
                        f"The class has {p.below_line} of {p.students} below the line overall; each strand "
                        "has its own below_line count in get_class_performance. Use the one for what you name.")

    invented = uncited_percentages(" ".join([diagnosis, *steps]), p)
    if invented:
        raise ToolError(f"These figures are not in the class data: {', '.join(invented)}. "
                        "Cite only numbers returned by get_class_performance.")

    focus = canonical_strands(strands, p)
    return _propose(ctx, "class_plan", f"{p.title} ({code}): {title.strip()[:120]}", diagnosis.strip()[:600],
                    {"course_code": code, "title": title.strip()[:200], "diagnosis": diagnosis.strip()[:1200],
                     "focus_strands": focus, "actions": [a[:300] for a in steps], "goal": goal.strip()[:300]},
                    [_class_row(p)])


# ===================== study plans (one student, one class) ==============
def _work_row(w: "SP.ClassWork") -> dict:
    return {"sid": w.sid, "class": w.course_code, "grade_pct": round(w.pct), "class_average_pct":
            round(w.class_pct) if w.class_pct is not None else None, "missing": len(w.missing),
            "findings": [f.code for f in w.findings][:4]}


def list_students_for_study_plans(db: Session, ctx: dict) -> dict:
    rows = [_work_row(w) for w in SP.students_needing_plans(db)]
    return _capped(rows) | {"how_to_read": "Each row is one student in one class with no study plan yet, "
                                           "lowest grade first. Open one with get_student_class_work."}


def _r(v: float | None) -> int | None:
    return round(v) if v is not None else None


def get_student_class_work(db: Session, ctx: dict, sid: str, course_code: str) -> dict:
    """Whole numbers, and only what a plan needs: a 4B model cites what it is shown."""
    sid, code = sid.strip().upper(), course_code.strip().upper()
    w = SP.class_work(db, sid, code)
    if w is None:
        raise ToolError(f"{sid} has no graded work in {code}. Call list_students_for_study_plans for real pairs.")
    return {
        "sid": w.sid, "class": w.course_code, "title": w.course_title, "teacher": w.teacher,
        "grade_pct": _r(w.pct), "class_average_pct": _r(w.class_pct), "trend_points": round(w.trend),
        "findings": [{"code": f.code, "what": f.text} for f in w.findings],
        "strands": [{"strand": s.strand, "gradebook_pct": _r(s.pct), "on_work_handed_in_pct": _r(s.handed_in_pct),
                     "class_average_pct": _r(s.class_pct), "missing": s.missing} for s in w.strands],
        "by_kind_of_work": [{"kind": k.kind, "average_pct": _r(k.pct), "handed_in": f"{k.handed_in} of {k.due}"}
                            for k in w.kinds],
        "missing_assignments": [{"id": a.id, "title": a.title, "strand": a.strand, "due": a.due_on}
                                for a in w.missing[:8]],
        "recent_assignments": [{"id": a.id, "title": a.title, "kind": a.kind, "strand": a.strand,
                                "pct": _r(a.pct), "class_pct": _r(a.class_pct)}
                               for a in w.assignments[-8:] if a.pct is not None],
        "has_active_study_plan": SP.active_plan(db, sid, code) is not None,
    }


def propose_study_plan(db: Session, ctx: dict, student_sid: str, course_code: str, title: str,
                       diagnosis: str, focus_strands: list, sessions: list, goal: str,
                       catch_up_assignments: list | None = None) -> dict:
    sid, code = student_sid.strip().upper(), course_code.strip().upper()
    for key, want in (("only_student", sid), ("only_course", code)):
        if ctx.get(key) and ctx[key] != want:
            raise ToolError(f"This run is only for {ctx['only_student']} in {ctx['only_course']}. Propose for that.")
    w = SP.class_work(db, sid, code)
    if w is None:
        raise ToolError(f"{sid} has no graded work in {code}. Call list_students_for_study_plans for real pairs.")
    if SP.active_plan(db, sid, code):
        raise ToolError(f"{sid} already has an active study plan for {code}. Choose another student, or stop.")
    if any(x["kind"] == "study_plan" and (x["payload"]["student_sid"], x["payload"]["course_code"]) == (sid, code)
           for x in ctx.get("proposals", [])):
        raise ToolError(f"You already proposed a study plan for {sid} in {code} in this run.")
    if any((x.payload or {}).get("student_sid") == sid and (x.payload or {}).get("course_code") == code
           for x in db.scalars(select(Proposal).where(Proposal.kind == "study_plan",
                                                      Proposal.status == "pending")).all()):
        raise ToolError(f"A draft study plan for {sid} in {code} is already waiting for approval.")

    strands = [str(s).strip() for s in focus_strands if str(s).strip()]
    steps = [str(s).strip() for s in sessions if str(s).strip()]
    try:
        catch_up = [int(i) for i in (catch_up_assignments or [])]
    except (TypeError, ValueError):
        raise ToolError("catch_up_assignments must be assignment ids (numbers) from missing_assignments.") from None
    problems = SP.problems_with(w, focus_strands=strands, sessions=steps, catch_up=catch_up,
                                goal=goal, diagnosis=diagnosis)
    if problems:
        raise ToolError(" ".join(problems) + " Fix these and propose again.")

    return _propose(ctx, "study_plan", f"{sid} in {code}: {title.strip()[:120]}", diagnosis.strip()[:600],
                    {"student_sid": sid, "course_code": code, "title": title.strip()[:200],
                     "diagnosis": diagnosis.strip()[:1200], "focus_strands": SP.canonical_strands(strands, w),
                     "sessions": [s[:300] for s in steps], "catch_up_assignments": catch_up,
                     "goal": goal.strip()[:300]},
                    [_work_row(w) | {"findings": [f.text for f in w.findings]}])
