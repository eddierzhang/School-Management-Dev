"""The stockroom.

Counts are the point of this module, so every write is explicit about what it
means: `PATCH` nudges a number, `POST /count` records that somebody physically
counted the shelf and stamps the date. Conflating the two loses the distinction
between "we think there are six" and "I counted six this morning".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import module, require_by_method
from ..config import get_settings
from ..db import get_db
from ..models import Course, InventoryItem
from ..schemas import (CountIn, InventoryCreate, InventoryDetail, InventoryRow, InventoryUpdate,
                       LinkedCourse, Requisition, RequisitionSupplier, StockroomSummary)
from ..stock import (add_item, cost_to_par, enrolment_by_course, new_item_problem, short_by, status_of,
                     students_depending_on)

router = APIRouter(prefix="/inventory", tags=["inventory"],
                   dependencies=[Depends(module("stockroom")),
                                 Depends(require_by_method(read="inventory.read", write="inventory.write"))])
settings = get_settings()


def _row(item: InventoryItem, enrolment: dict[str, int]) -> InventoryRow:
    st = status_of(item)
    ago = (settings.today - item.last_counted).days if item.last_counted else None
    return InventoryRow(
        sku=item.sku, name=item.name, category=item.category, unit=item.unit,
        on_hand=item.on_hand, reorder_point=item.reorder_point, par=item.par,
        location=item.location, supplier=item.supplier, unit_cost=round(item.unit_cost, 2),
        last_counted=item.last_counted, linked_courses=list(item.linked_courses or []),
        requisitioned=item.requisitioned,
        status=st.kind, status_label=st.label, ratio=round(st.ratio, 4),
        short_by=short_by(item), cost_to_par=cost_to_par(item),
        students_affected=students_depending_on(item, enrolment),
        days_since_count=ago,
    )


def _get(db: Session, sku: str) -> InventoryItem:
    item = db.scalar(select(InventoryItem).where(InventoryItem.sku == sku.strip().upper()))
    if item is None:
        raise HTTPException(404, f"No stockroom item with SKU {sku}")
    return item


@router.get("", response_model=list[InventoryRow])
def list_items(
    category: str | None = None,
    needs_attention: bool = False,
    requisitioned: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> list[InventoryRow]:
    enrolment = enrolment_by_course(db)
    rows = [_row(i, enrolment) for i in db.scalars(select(InventoryItem)).all()]
    if category and category != "all":
        rows = [r for r in rows if r.category == category]
    if needs_attention:
        rows = [r for r in rows if r.status in ("critical", "serious")]
    if requisitioned is not None:
        rows = [r for r in rows if r.requisitioned is requisitioned]
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in
                f"{r.name} {r.sku} {r.location} {r.supplier} {' '.join(r.linked_courses)}".lower()]
    # Worst first: how far under the reorder point, then how many students it touches.
    rows.sort(key=lambda r: (r.on_hand - r.reorder_point, -r.students_affected))
    return rows


@router.get("/summary", response_model=StockroomSummary)
def summary(db: Session = Depends(get_db)) -> StockroomSummary:
    items = db.scalars(select(InventoryItem)).all()
    flagged = [i for i in items if status_of(i).needs_attention]
    return StockroomSummary(
        items=len(items),
        needs_attention=len(flagged),
        below_reorder=sum(1 for i in items if i.on_hand <= i.reorder_point),
        on_requisition=sum(1 for i in items if i.requisitioned),
        value_on_hand=round(sum((i.on_hand or 0) * (i.unit_cost or 0) for i in items), 2),
        cost_to_par=round(sum(cost_to_par(i) for i in flagged), 2),
        categories=sorted({i.category for i in items}),
    )


@router.get("/requisition", response_model=Requisition)
def requisition(db: Session = Depends(get_db)) -> Requisition:
    """What is on order, grouped the way it gets sent: one list per supplier."""
    enrolment = enrolment_by_course(db)
    rows = [_row(i, enrolment) for i in
            db.scalars(select(InventoryItem).where(InventoryItem.requisitioned)).all()]
    by: dict[str, list[InventoryRow]] = {}
    for r in rows:
        by.setdefault(r.supplier, []).append(r)
    groups = [
        RequisitionSupplier(supplier=name, lines=lines,
                            cost=round(sum(line.cost_to_par for line in lines), 2))
        for name, lines in sorted(by.items())
    ]
    return Requisition(lines=len(rows), cost=round(sum(g.cost for g in groups), 2), by_supplier=groups)


@router.post("/requisition/low", response_model=Requisition, status_code=201)
def requisition_everything_low(db: Session = Depends(get_db)) -> Requisition:
    for item in db.scalars(select(InventoryItem)).all():
        if status_of(item).needs_attention:
            item.requisitioned = True
    db.commit()
    return requisition(db)


@router.get("/{sku}", response_model=InventoryDetail)
def item_detail(sku: str, db: Session = Depends(get_db)) -> InventoryDetail:
    item = _get(db, sku)
    enrolment = enrolment_by_course(db)
    base = _row(item, enrolment)
    classes = []
    for code in item.linked_courses or []:
        course = db.scalar(select(Course).where(Course.code == code))
        if course is not None:
            classes.append(LinkedCourse(code=course.code, title=course.title,
                                        enrolled=enrolment.get(code, 0)))
    return InventoryDetail(
        **base.model_dump(),
        value_on_hand=round((item.on_hand or 0) * (item.unit_cost or 0), 2),
        classes=classes,
    )


@router.patch("/{sku}", response_model=InventoryDetail)
def update_item(sku: str, body: InventoryUpdate, db: Session = Depends(get_db)) -> InventoryDetail:
    item = _get(db, sku)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(422, "Nothing to change.")
    par = fields.get("par", item.par)
    reorder = fields.get("reorder_point", item.reorder_point)
    if reorder > par:
        raise HTTPException(
            422, f"Reorder point ({reorder}) cannot be above the par level ({par}) — "
                 "an item would be flagged the moment it was fully stocked.")
    for key, value in fields.items():
        setattr(item, key, value)
    db.commit()
    return item_detail(item.sku, db)


@router.post("/{sku}/count", response_model=InventoryDetail)
def record_count(sku: str, body: CountIn, db: Session = Depends(get_db)) -> InventoryDetail:
    item = _get(db, sku)
    item.on_hand = body.on_hand
    item.last_counted = settings.today
    db.commit()
    return item_detail(item.sku, db)


@router.post("", response_model=InventoryDetail, status_code=201)
def create_item(body: InventoryCreate, db: Session = Depends(get_db)) -> InventoryDetail:
    fields = body.model_dump() | {"linked_courses": [c.strip().upper() for c in body.linked_courses]}
    problem = new_item_problem(db, fields["sku"], fields["name"], fields["reorder_point"],
                               fields["par"], fields["linked_courses"])
    if problem:
        raise HTTPException(problem.status, problem.message)
    item = add_item(db, **fields)
    db.commit()
    return item_detail(item.sku, db)


@router.delete("/{sku}", status_code=204)
def delete_item(sku: str, db: Session = Depends(get_db)):  # no return annotation:
    # `from __future__ import annotations` makes `-> None` a string that FastAPI
    # resolves into a response model, which a 204 may not have.
    db.delete(_get(db, sku))
    db.commit()
