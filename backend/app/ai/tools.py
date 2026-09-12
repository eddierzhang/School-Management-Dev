"""What each agent can see and what it can propose.

Two rules shape every tool here.

**Results are small.** A 4B model handed 60 rows of JSON loses the thread. Every
list tool caps its output and returns only the fields the decision needs. The cap
is reported in the payload so the agent knows it is looking at a slice.

**No tool writes.** The `propose_*` tools record an intent on the run and return a
receipt. Nothing reaches the database until a person approves it.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import build_signals, skill_gaps
from ..config import get_settings
from ..models import Course, Enrollment, InventoryItem, Intervention, Student
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
    return {"sku": i.sku, "name": i.name, "category": i.category, "on_hand": i.on_hand,
            "reorder_point": i.reorder_point, "par": i.par, "unit": i.unit,
            "short_by": max(0, i.par - i.on_hand), "unit_cost": round(i.unit_cost, 2),
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
    cost = sum(max(0, i.par - i.on_hand) * i.unit_cost for i in found)
    return _propose(ctx, "requisition",
                    f"Order {len(found)} item(s) to par — about ${cost:,.2f}", reason,
                    {"skus": [i.sku for i in found]},
                    [{"sku": i.sku, "name": i.name, "on_hand": i.on_hand,
                      "reorder_point": i.reorder_point, "to_par": max(0, i.par - i.on_hand)} for i in found])


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
    clash = [c.code for c in db.scalars(select(Course)).all() if c.period == period and c.room == room]
    if clash:
        raise ToolError(f"Room {room} is already used in period {period} by {', '.join(clash)}. "
                        f"Call find_open_rooms(period={period}) for a free room.")
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
