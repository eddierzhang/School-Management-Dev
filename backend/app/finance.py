"""Budget position, in one place.

Like app/stock.py, this is the single definition the API, the interface and the
finance agent all read. Four numbers matter for every line:

    budget     allocation plus transfers in, minus transfers out
    spent      posted transactions (refunds net against them)
    committed  money promised but not yet spent — today, the stockroom's open
               requisition, costed to par and charged to the line that buys it
    available  budget − spent − committed

Status compares where a line is against how much of the year has gone:

    over           spent + committed already exceed the budget
    at risk        the year-end projection exceeds the budget
    under-spending under 35% of the expected pace, past the first six weeks —
                   money that may need moving before it lapses
    on track       everything else

The projection separates one-time purchases from recurring spend. An August
laptop refresh is spent once; extrapolating it across twelve months would flag
every front-loaded line as overspending.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import BudgetLine, BudgetTransfer, Course, InventoryItem, Transaction
from .stock import cost_to_par

settings = get_settings()

FY_START = date(2026, 7, 1)
FY_END = date(2027, 6, 30)
FISCAL_YEAR = "FY2027"
UNDERSPEND_PACE = 0.35
UNDERSPEND_GRACE_DAYS = 42
LARGE_SHARE = 0.25          # one transaction over a quarter of a line's budget
DUPLICATE_WINDOW_DAYS = 10

# Where each stockroom purchase is charged. A linked class charges its department;
# an unlinked item falls back to its stockroom category.
DEPARTMENT_SUPPLY_LINE = {
    "Science": "SCI-LAB", "Mathematics": "MAT-INS", "Computer Science": "CSC-ROB",
    "Visual Arts": "ART-STU", "Performing Arts": "PFA-MUS", "Physical Education": "PE-EQP",
    "English": "ENG-INS", "Modern and Classical Languages": "MCL-INS",
    "Speech and Debate": "SPD-TRV",
}
CATEGORY_SUPPLY_LINE = {
    "Science Lab": "SCI-LAB", "Mathematics": "MAT-INS", "Technology": "CSC-TEC",
    "Career & Tech": "FAC-MNT", "Arts": "ART-STU", "Athletics": "PE-EQP", "Facilities": "FAC-MNT",
}


def money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def elapsed_fraction(today: date | None = None) -> float:
    today = today or settings.today
    total = (FY_END - FY_START).days + 1
    return min(1.0, max(0.0, ((today - FY_START).days + 1) / total))


@dataclass
class LinePosition:
    code: str
    name: str
    department: str
    category: str
    owner: str
    allocated: float
    transfers_in: float
    transfers_out: float
    budget: float
    spent: float
    one_time: float
    committed: float
    available: float
    used_pct: float
    projected: float
    status: str
    status_label: str
    note: str
    transaction_count: int
    commitments: list[dict] = field(default_factory=list)


def charge_line_for(item: InventoryItem, course_dept: dict[str, str]) -> str:
    for code in item.linked_courses or []:
        dept = course_dept.get(code)
        if dept in DEPARTMENT_SUPPLY_LINE:
            return DEPARTMENT_SUPPLY_LINE[dept]
    return CATEGORY_SUPPLY_LINE.get(item.category, "FAC-MNT")


def commitments_by_line(db: Session) -> dict[str, list[dict]]:
    course_dept = {c.code: c.dept for c in db.scalars(select(Course)).all()}
    out: dict[str, list[dict]] = defaultdict(list)
    for item in db.scalars(select(InventoryItem).where(InventoryItem.requisitioned)).all():
        cost = cost_to_par(item)
        if cost > 0:
            out[charge_line_for(item, course_dept)].append(
                {"source": "stockroom requisition", "sku": item.sku, "name": item.name, "amount": cost})
    return out


def classify(budget: float, spent: float, one_time: float, committed: float,
             elapsed: float, today: date | None = None) -> tuple[str, str, float, str]:
    """(status, label, projected year-end, explanation). Pure — no database."""
    today = today or settings.today
    recurring = spent - one_time
    projected = one_time + committed + (recurring / elapsed if elapsed > 0 else recurring)
    projected = round(projected, 2)
    if budget <= 0:
        return "critical", "No budget", projected, "Spending against a line with nothing allocated."
    if spent + committed > budget:
        over = spent + committed - budget
        return "critical", "Over budget", projected, f"${over:,.0f} over, counting open commitments."
    if projected > budget:
        return ("serious", "At risk", projected,
                f"At this pace the line reaches ${projected:,.0f} by June — ${projected - budget:,.0f} over.")
    days_in = (today - FY_START).days
    expected = budget * elapsed
    if days_in >= UNDERSPEND_GRACE_DAYS and spent + committed < expected * UNDERSPEND_PACE:
        return ("warning", "Under-spending", projected,
                f"${spent + committed:,.0f} used against ${expected:,.0f} expected by now.")
    return "good", "On track", projected, ""


def positions(db: Session, today: date | None = None) -> list[LinePosition]:
    today = today or settings.today
    elapsed = elapsed_fraction(today)
    lines = db.scalars(select(BudgetLine).where(BudgetLine.fiscal_year == FISCAL_YEAR)).all()
    spent: dict[int, float] = defaultdict(float)
    one_time: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for t in db.scalars(select(Transaction).where(Transaction.posted_on <= today)).all():
        spent[t.line_id] += t.amount
        count[t.line_id] += 1
        if t.one_time:
            one_time[t.line_id] += t.amount
    t_in: dict[int, float] = defaultdict(float)
    t_out: dict[int, float] = defaultdict(float)
    for tr in db.scalars(select(BudgetTransfer)).all():
        t_in[tr.to_line_id] += tr.amount
        t_out[tr.from_line_id] += tr.amount
    commits = commitments_by_line(db)

    out = []
    for ln in lines:
        budget = round(ln.allocated + t_in[ln.id] - t_out[ln.id], 2)
        committed = round(sum(c["amount"] for c in commits.get(ln.code, [])), 2)
        s = round(spent[ln.id], 2)
        status, label, projected, note = classify(budget, s, one_time[ln.id], committed, elapsed, today)
        out.append(LinePosition(
            code=ln.code, name=ln.name, department=ln.department, category=ln.category, owner=ln.owner,
            allocated=round(ln.allocated, 2), transfers_in=round(t_in[ln.id], 2),
            transfers_out=round(t_out[ln.id], 2), budget=budget, spent=s,
            one_time=round(one_time[ln.id], 2), committed=committed,
            available=round(budget - s - committed, 2),
            used_pct=round((s + committed) / budget * 100, 1) if budget > 0 else 0.0,
            projected=projected, status=status, status_label=label, note=note,
            transaction_count=count[ln.id], commitments=commits.get(ln.code, []),
        ))
    rank = {"critical": 0, "serious": 1, "warning": 2, "good": 3}
    out.sort(key=lambda p: (rank[p.status], -(p.used_pct)))
    return out


def anomalies(db: Session, today: date | None = None) -> list[dict]:
    """Transactions a person should look at. Each carries the rule that caught it."""
    today = today or settings.today
    budgets = {p.code: p.budget for p in positions(db, today)}
    txns = db.scalars(select(Transaction).where(Transaction.posted_on <= today)
                      .order_by(Transaction.posted_on)).all()
    found: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()
    by_key: dict[tuple[str, float], list[Transaction]] = defaultdict(list)
    for t in txns:
        if t.amount <= 0 or t.review_status == "cleared":
            continue
        key = (t.vendor.strip().lower(), round(t.amount, 2))
        for earlier in by_key[key]:
            if (t.posted_on - earlier.posted_on) <= timedelta(days=DUPLICATE_WINDOW_DAYS) \
                    and (earlier.id, t.id) not in seen_pairs:
                seen_pairs.add((earlier.id, t.id))
                found.append({
                    "rule": "possible duplicate", "transaction_id": t.id, "related_id": earlier.id,
                    "line": t.line.code, "vendor": t.vendor, "amount": t.amount,
                    "posted_on": t.posted_on.isoformat(), "review_status": t.review_status,
                    "detail": f"Same vendor and amount as #{earlier.id} "
                              f"{(t.posted_on - earlier.posted_on).days} day(s) earlier "
                              f"({earlier.reference or 'no reference'} vs {t.reference or 'no reference'}).",
                })
        by_key[key].append(t)
        budget = budgets.get(t.line.code, 0)
        if budget > 0 and t.amount > budget * LARGE_SHARE:
            found.append({
                "rule": "large single charge", "transaction_id": t.id, "related_id": None,
                "line": t.line.code, "vendor": t.vendor, "amount": t.amount,
                "posted_on": t.posted_on.isoformat(), "review_status": t.review_status,
                "detail": f"{t.amount / budget:.0%} of the line's ${budget:,.0f} budget in one charge.",
            })
    found.sort(key=lambda a: (a["review_status"] != "flagged", a["posted_on"]), reverse=False)
    return found


def max_giveable(pos: LinePosition, today: date | None = None, step: float = 250.0) -> float:
    """The most a line can give away, in whole steps, and still be on track or
    under-spending afterwards. Used to point the agent at real donors."""
    if pos.status not in ("good", "warning"):
        return 0.0
    elapsed = elapsed_fraction(today)
    room = 0.0
    while room + step <= pos.available:
        status, _, _, _ = classify(pos.budget - room - step, pos.spent, pos.one_time, pos.committed, elapsed, today)
        if status in ("critical", "serious"):
            break
        room += step
    return room


def transfer_problem(db: Session, from_code: str, to_code: str, amount: float,
                     today: date | None = None) -> str | None:
    """Why a transfer should not happen, or None. Shared by the API, the agent's
    propose tool and the executor, so all three refuse the same things."""
    if from_code == to_code:
        return "A transfer needs two different lines."
    if amount <= 0:
        return "The amount must be more than zero."
    by_code = {p.code: p for p in positions(db, today)}
    src, dst = by_code.get(from_code), by_code.get(to_code)
    missing = [c for c, p in ((from_code, src), (to_code, dst)) if p is None]
    if missing:
        return f"No budget line with code: {', '.join(missing)}."
    assert src and dst
    if amount > src.available:
        return (f"{src.code} has {money(src.available)} available after spending and commitments; "
                f"it cannot give {money(amount)}.")
    elapsed = elapsed_fraction(today)
    status, _, _, _ = classify(src.budget - amount, src.spent, src.one_time, src.committed, elapsed, today)
    if status in ("critical", "serious"):
        return (f"Moving ${amount:,.2f} out of {src.code} would put that line at risk itself. "
                "Take less, or take it from a line with more room.")
    return None
