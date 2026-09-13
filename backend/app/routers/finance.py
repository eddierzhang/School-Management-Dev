"""Budget, spending and transfers.

Transfers never edit an allocation; they are recorded next to it, so the budget
the board approved stays readable beside every change made to it.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth.deps import Principal, current_user, module, require_by_method
from ..config import get_settings
from ..db import get_db
from ..finance import (FISCAL_YEAR, FY_START, anomalies, elapsed_fraction, max_giveable, needs,
                       new_line_problem, positions, revision_problem, transfer_problem)
from ..models import BudgetLine, BudgetTransfer, Transaction

router = APIRouter(prefix="/finance", tags=["finance"],
                   dependencies=[Depends(module("finance")),
                                 Depends(require_by_method(read="finance.read", write="finance.write"))])
settings = get_settings()


class TransactionIn(BaseModel):
    line_code: str
    vendor: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=2, max_length=240)
    amount: float
    posted_on: date | None = None
    reference: str = Field(default="", max_length=40)
    one_time: bool = False


class ReviewIn(BaseModel):
    review_status: str = Field(pattern="^(clear|flagged|cleared)$")
    review_note: str = Field(default="", max_length=1000)


class TransferIn(BaseModel):
    from_line: str
    to_line: str
    amount: float
    reason: str = Field(min_length=4, max_length=1000)


class NewLineIn(BaseModel):
    code: str = Field(min_length=5, max_length=8)
    name: str = Field(min_length=4, max_length=120)
    department: str
    category: str = Field(min_length=2, max_length=60)
    owner: str = Field(default="", max_length=120)
    from_line: str
    amount: float
    reason: str = Field(min_length=4, max_length=1000)


class MoveIn(BaseModel):
    from_line: str
    to_line: str
    amount: float


class RevisionIn(BaseModel):
    moves: list[MoveIn] = Field(min_length=1, max_length=6)
    reason: str = Field(min_length=4, max_length=1000)


def _txn(t: Transaction) -> dict:
    return {"id": t.id, "line": t.line.code, "line_name": t.line.name, "posted_on": t.posted_on.isoformat(),
            "vendor": t.vendor, "description": t.description, "amount": round(t.amount, 2),
            "reference": t.reference, "one_time": t.one_time,
            "review_status": t.review_status, "review_note": t.review_note}


def _transfer(db: Session, tr: BudgetTransfer) -> dict:
    src, dst = db.get(BudgetLine, tr.from_line_id), db.get(BudgetLine, tr.to_line_id)
    return {"id": tr.id, "from_line": src.code if src else None, "to_line": dst.code if dst else None,
            "amount": round(tr.amount, 2), "reason": tr.reason, "approved_by": tr.approved_by,
            "created_at": tr.created_at.isoformat() if tr.created_at else None}


def _line(db: Session, code: str) -> BudgetLine:
    ln = db.scalar(select(BudgetLine).where(BudgetLine.code == code.strip().upper()))
    if ln is None:
        raise HTTPException(404, f"No budget line {code}")
    return ln


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    ps = positions(db)
    found = anomalies(db)
    budget = sum(p.budget for p in ps)
    spent = sum(p.spent for p in ps)
    committed = sum(p.committed for p in ps)
    return {
        "fiscal_year": FISCAL_YEAR, "as_of": settings.today.isoformat(),
        "elapsed_pct": round(elapsed_fraction() * 100, 1),
        "budget": round(budget, 2), "spent": round(spent, 2), "committed": round(committed, 2),
        "available": round(budget - spent - committed, 2),
        "projected": round(sum(p.projected for p in ps), 2),
        "lines": len(ps),
        "over": sum(1 for p in ps if p.status == "critical"),
        "at_risk": sum(1 for p in ps if p.status == "serious"),
        "underspending": sum(1 for p in ps if p.status == "warning"),
        "anomalies": sum(1 for a in found if a["review_status"] == "clear"),
        "flagged": db.query(Transaction).filter(Transaction.review_status == "flagged").count(),
        "needs_attention": sum(1 for p in ps if p.status in ("critical", "serious"))
                           + sum(1 for a in found if a["review_status"] == "clear"),
    }


@router.get("/lines")
def lines(db: Session = Depends(get_db)) -> list[dict]:
    return [asdict(p) for p in positions(db)]


@router.get("/lines/{code}")
def line_detail(code: str, db: Session = Depends(get_db)) -> dict:
    ln = _line(db, code)
    pos = next(p for p in positions(db) if p.code == ln.code)
    txns = db.scalars(select(Transaction).where(Transaction.line_id == ln.id)
                      .order_by(Transaction.posted_on.desc())).all()
    transfers = db.scalars(select(BudgetTransfer).where(
        or_(BudgetTransfer.from_line_id == ln.id, BudgetTransfer.to_line_id == ln.id))).all()
    return asdict(pos) | {"transactions": [_txn(t) for t in txns],
                          "transfers": [_transfer(db, tr) for tr in transfers]}


@router.get("/anomalies")
def list_anomalies(db: Session = Depends(get_db)) -> list[dict]:
    return anomalies(db)


@router.get("/transactions")
def list_transactions(line: str | None = None, review_status: str | None = None,
                      db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Transaction).order_by(Transaction.posted_on.desc())
    if line:
        stmt = stmt.where(Transaction.line_id == _line(db, line).id)
    if review_status:
        stmt = stmt.where(Transaction.review_status == review_status)
    return [_txn(t) for t in db.scalars(stmt).all()]


@router.post("/transactions", status_code=201)
def record_transaction(body: TransactionIn, db: Session = Depends(get_db)) -> dict:
    ln = _line(db, body.line_code)
    posted = body.posted_on or settings.today
    if posted > settings.today:
        raise HTTPException(422, "A transaction cannot be posted in the future — record it when it is spent.")
    if posted < FY_START:
        raise HTTPException(422, f"{posted} is before {FISCAL_YEAR} began on {FY_START}.")
    if body.amount == 0:
        raise HTTPException(422, "The amount cannot be zero. Use a negative amount for a refund.")
    t = Transaction(line_id=ln.id, posted_on=posted, vendor=body.vendor.strip(),
                    description=body.description.strip(), amount=round(body.amount, 2),
                    reference=body.reference.strip(), one_time=body.one_time)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _txn(t)


@router.patch("/transactions/{txn_id}")
def review_transaction(txn_id: int, body: ReviewIn, db: Session = Depends(get_db)) -> dict:
    t = db.get(Transaction, txn_id)
    if t is None:
        raise HTTPException(404, f"No transaction {txn_id}")
    t.review_status, t.review_note = body.review_status, body.review_note.strip()
    db.commit()
    return _txn(t)


@router.get("/transfers")
def list_transfers(db: Session = Depends(get_db)) -> list[dict]:
    return [_transfer(db, tr) for tr in db.scalars(select(BudgetTransfer).order_by(BudgetTransfer.id.desc())).all()]


@router.post("/transfers", status_code=201)
def make_transfer(body: TransferIn, db: Session = Depends(get_db), user: Principal = Depends(current_user)) -> dict:
    src, dst = body.from_line.strip().upper(), body.to_line.strip().upper()
    problem = transfer_problem(db, src, dst, round(body.amount, 2))
    if problem:
        raise HTTPException(409 if "available" in problem or "at risk" in problem else 422, problem)
    tr = BudgetTransfer(from_line_id=_line(db, src).id, to_line_id=_line(db, dst).id,
                        amount=round(body.amount, 2), reason=body.reason.strip(), approved_by=user.name)
    db.add(tr)
    db.commit()
    db.refresh(tr)
    return _transfer(db, tr)


@router.get("/needs")
def where_money_is_needed(db: Session = Depends(get_db)) -> dict:
    """Lines that need money and how much, beside the lines that can give and the most each can."""
    return {
        "needs": [asdict(n) for n in needs(db)],
        "room": sorted(({"code": p.code, "name": p.name, "can_give": g} for p in positions(db)
                        if (g := max_giveable(p)) > 0), key=lambda r: -r["can_give"]),
    }


@router.post("/lines", status_code=201)
def open_line(body: NewLineIn, db: Session = Depends(get_db), user: Principal = Depends(current_user)) -> dict:
    """Open a line at zero and fund it with a transfer, so no approved allocation is edited."""
    code, src = body.code.strip().upper(), body.from_line.strip().upper()
    amount = round(body.amount, 2)
    problem = new_line_problem(db, code, body.name, body.department, body.category, src, amount)
    if problem:
        raise HTTPException(409 if "available" in problem or "at risk" in problem or "exists" in problem
                            else 422, problem)
    line = BudgetLine(code=code, name=body.name.strip(), department=body.department.strip(),
                      category=body.category.strip(), fiscal_year=FISCAL_YEAR, allocated=0.0,
                      owner=body.owner.strip() or "Business office")
    db.add(line)
    db.flush()
    db.add(BudgetTransfer(from_line_id=_line(db, src).id, to_line_id=line.id, amount=amount,
                          reason=f"Opening {code}: {body.reason.strip()}", approved_by=user.name))
    db.commit()
    return next(asdict(p) for p in positions(db) if p.code == code)


@router.post("/revisions", status_code=201)
def revise(body: RevisionIn, db: Session = Depends(get_db), user: Principal = Depends(current_user)) -> dict:
    """Several transfers approved together, judged on their combined effect."""
    moves = [{"from_line": m.from_line.strip().upper(), "to_line": m.to_line.strip().upper(),
              "amount": round(m.amount, 2)} for m in body.moves]
    problem = revision_problem(db, moves)
    if problem:
        raise HTTPException(409, problem)
    made = []
    for m in moves:
        tr = BudgetTransfer(from_line_id=_line(db, m["from_line"]).id, to_line_id=_line(db, m["to_line"]).id,
                            amount=m["amount"], reason=f"Budget revision: {body.reason.strip()}", approved_by=user.name)
        db.add(tr)
        made.append(tr)
    db.commit()
    return {"moved": round(sum(m["amount"] for m in moves), 2), "transfers": [_transfer(db, tr) for tr in made]}
