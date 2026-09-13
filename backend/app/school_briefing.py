"""The whole school on one page, computed rather than generated.

The general manager agent answers questions about the school, and a 4B model
summarising six screens of raw data will drop or invent numbers. So the numbers
are assembled here, deterministically, from the same modules every screen reads —
analytics, stock, finance, demand — and the model is handed a compact, already
correct digest to talk about. The home page shows the same digest directly.

Each section carries a short list of `attention` lines: the handful of things a
person would want raised first. Those are rules, not judgment.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics import build_signals, skill_gaps
from .config import get_settings
from .models import AgentRun, Course, Enrollment, Intervention, InventoryItem, Proposal
from .stock import cost_to_par, status_of

settings = get_settings()


def _students(db: Session) -> dict:
    sigs = build_signals(db)
    bands: dict[str, int] = {}
    for s in sigs.values():
        bands[s.band] = bands.get(s.band, 0) + 1
    planned = {iv.student.sid for iv in db.scalars(select(Intervention).where(Intervention.status == "active")).all()}
    unaddressed = sorted((s for s in sigs.values()
                          if s.band == "needs-plan" and s.sid not in planned and not s.acknowledged),
                         key=lambda s: -s.struggle_index)
    rates = [s.absence_rate for s in sigs.values() if s.days_counted]
    attention = []
    if unaddressed:
        names = ", ".join(f"{s.name} ({s.sid})" for s in unaddressed[:3])
        attention.append(f"{len(unaddressed)} students need a support plan and have none — worst: {names}.")
    return {
        "total": len(sigs),
        "needs_plan": bands.get("needs-plan", 0), "watch": bands.get("watch", 0),
        "excelling": bands.get("excelling", 0), "steady": bands.get("steady", 0),
        "open_plans": db.query(Intervention).filter(Intervention.status == "active").count(),
        "needs_plan_without_one": len(unaddressed),
        "attendance_pct": round((1 - statistics.fmean(rates)) * 100, 1) if rates else None,
        "most_urgent": [{"sid": s.sid, "name": s.name, "grade": s.grade, "struggle_index": s.struggle_index,
                         "why": f"{s.reasons[0].label}: {s.reasons[0].detail}" if s.reasons else ""} for s in unaddressed[:5]],
        "attention": attention,
    }


def _classes(db: Session) -> dict:
    sigs = build_signals(db)
    by_code: dict[str, list[float]] = {}
    for s in sigs.values():
        for cs in s.courses:
            by_code.setdefault(cs.course_code, []).append(cs.pct)
    courses = db.scalars(select(Course).order_by(Course.code)).all()
    rows = []
    for c in courses:
        pcts = by_code.get(c.code, [])
        waiting = db.query(Enrollment).filter(Enrollment.course_id == c.id, Enrollment.status == "waitlist").count()
        rows.append({"code": c.code, "title": c.title, "teacher": c.teacher,
                     "average": round(statistics.fmean(pcts), 1) if pcts else None,
                     "enrolled": len(pcts), "capacity": c.capacity, "waitlist": waiting})
    graded = [r for r in rows if r["average"] is not None]
    weakest = sorted(graded, key=lambda r: r["average"])[:3]
    strongest = sorted(graded, key=lambda r: -r["average"])[:3]
    gaps = [{"course": g.course_code, "skill": g.skill, "class_mean": round(g.class_mean, 1),
             "share_below": round(g.share_below, 2)} for g in skill_gaps(db)[:4]]
    waitlisted = sorted((r for r in rows if r["waitlist"] > 0), key=lambda r: -r["waitlist"])
    attention = []
    for r in weakest:
        if r["average"] < settings.support_threshold:
            attention.append(f"{r['title']} ({r['code']}, {r['teacher']}) averages {r['average']}%, "
                             f"below the {settings.support_threshold}% support line.")
    if waitlisted and waitlisted[0]["waitlist"] >= waitlisted[0]["capacity"] * 0.5:
        w = waitlisted[0]
        attention.append(f"{w['title']} ({w['code']}) has {w['waitlist']} waiting for {w['capacity']} seats.")
    demand = []
    try:
        from .demand import class_demand
        demand = [{"code": d.code, "title": d.title, "score": d.score, "label": d.label, "action": d.action}
                  for d in class_demand(db)[:4]]
    except Exception:          # the demand module is optional; the briefing must still build
        demand = []
    return {"sections": len(rows), "weakest": weakest, "strongest": strongest, "skill_gaps": gaps,
            "waitlists": waitlisted[:4], "most_wanted": demand, "attention": attention}


def _stockroom(db: Session) -> dict:
    items = db.scalars(select(InventoryItem)).all()
    low = sorted((i for i in items if status_of(i).needs_attention), key=lambda i: i.on_hand - i.reorder_point)
    unordered = [i for i in low if not i.requisitioned]
    attention = []
    if unordered:
        attention.append(f"{len(unordered)} low items are not on order — worst: "
                         + ", ".join(f"{i.name} ({i.on_hand} left)" for i in unordered[:3]) + ".")
    return {"items": len(items), "needs_attention": len(low), "not_on_order": len(unordered),
            "on_requisition": sum(1 for i in items if i.requisitioned),
            "requisition_cost": round(sum(cost_to_par(i) for i in items if i.requisitioned), 2),
            "lowest": [{"sku": i.sku, "name": i.name, "on_hand": i.on_hand, "par": i.par,
                        "status": status_of(i).label, "on_order": i.requisitioned} for i in low[:5]],
            "attention": attention}


def _finance(db: Session) -> dict:
    try:
        from .finance import FISCAL_YEAR, anomalies, elapsed_fraction, positions
    except Exception:
        return {"available": False, "attention": []}
    ps = positions(db)
    if not ps:
        return {"available": False, "attention": []}
    found = [a for a in anomalies(db) if a["review_status"] == "clear"]
    budget = sum(p.budget for p in ps)
    spent = sum(p.spent for p in ps)
    committed = sum(p.committed for p in ps)
    troubled = [p for p in ps if p.status in ("critical", "serious")]
    attention = [f"{p.name} ({p.code}) is {p.status_label.lower()}: {p.note}" for p in troubled[:3]]
    if found:
        attention.append(f"{len(found)} charge(s) need review, e.g. {found[0]['vendor']} "
                         f"${found[0]['amount']:,.2f} — {found[0]['rule']}.")
    return {"available": True, "fiscal_year": FISCAL_YEAR, "year_elapsed_pct": round(elapsed_fraction() * 100, 1),
            "budget": round(budget, 2), "spent": round(spent, 2), "committed": round(committed, 2),
            "available_funds": round(budget - spent - committed, 2),
            "over_budget": sum(1 for p in ps if p.status == "critical"),
            "at_risk": sum(1 for p in ps if p.status == "serious"),
            "charges_to_review": len(found),
            "lines_in_trouble": [{"code": p.code, "name": p.name, "status": p.status_label, "note": p.note}
                                 for p in troubled[:5]],
            "attention": attention}


def _fleet(db: Session) -> dict:
    pending = db.scalars(select(Proposal).where(Proposal.status == "pending").order_by(Proposal.id.desc())).all()
    since = datetime.utcnow() - timedelta(days=7)
    runs = db.scalars(select(AgentRun).where(AgentRun.started_at >= since).order_by(AgentRun.id.desc())).all()
    by_agent: dict[str, int] = {}
    for p in pending:
        by_agent[p.agent] = by_agent.get(p.agent, 0) + 1
    attention = []
    if pending:
        attention.append(f"{len(pending)} agent proposal(s) are waiting for approval.")
    return {"pending_proposals": len(pending), "pending_by_agent": by_agent,
            "pending": [{"id": p.id, "agent": p.agent, "summary": p.summary} for p in pending[:6]],
            "running": [{"id": r.id, "agent": r.agent} for r in runs if r.status == "running"],
            "runs_this_week": len(runs), "attention": attention}


def build_briefing(db: Session) -> dict:
    sections = {
        "students": _students(db),
        "classes": _classes(db),
        "stockroom": _stockroom(db),
        "finance": _finance(db),
        "fleet": _fleet(db),
    }
    attention = [line for key in ("students", "classes", "finance", "stockroom", "fleet")
                 for line in sections[key]["attention"]]
    return {"school": settings.school_name, "term": settings.term, "as_of": settings.today.isoformat(),
            "attention": attention, **sections}
