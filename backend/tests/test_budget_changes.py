"""Opening budget lines and revising the budget — by a person or by the finance agent.

Neither edits an approved allocation: a new line opens at zero and is funded by a
recorded transfer, and a revision is several transfers approved together. Every
test removes what it made, since other tests read the seeded ledger.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app import finance as F
from app.ai import tools as T
from app.ai.agents import FLEET
from app.ai.executor import ApplyError, apply_proposal
from app.ai.toolkit import ToolError
from app.models import BudgetLine, BudgetTransfer, Proposal, Transaction


@pytest.fixture
def ledger(db):
    """Snapshot the ledger's transfers and lines; put it back afterwards."""
    transfers = {t.id for t in db.scalars(select(BudgetTransfer)).all()}
    lines = {ln.id for ln in db.scalars(select(BudgetLine)).all()}
    yield
    db.rollback()
    for t in db.scalars(select(BudgetTransfer)).all():
        if t.id not in transfers:
            db.delete(t)
    db.flush()
    for ln in db.scalars(select(BudgetLine)).all():
        if ln.id not in lines:
            db.delete(ln)
    for p in db.scalars(select(Proposal).where(Proposal.kind.in_(["budget_line", "budget_revision"]))).all():
        db.delete(p)
    db.commit()


def _room(db) -> list:
    return sorted(((p.code, F.max_giveable(p)) for p in F.positions(db) if F.max_giveable(p) > 0),
                  key=lambda r: -r[1])


# --- where money is needed --------------------------------------------------
def test_needs_are_the_short_lines_and_add_up(db):
    short = F.needs(db)
    assert short and short == sorted(short, key=lambda n: -n.need)
    by = {p.code: p for p in F.positions(db)}
    for n in short:
        assert by[n.code].status in ("critical", "serious") or n.unfunded_stock > 0
        assert n.need == pytest.approx(n.overrun + n.unfunded_stock, abs=0.01) and n.reasons
    assert "PE-EQP" in {n.code for n in short}, "the seeded over-budget line must show as needing money"


def test_needs_endpoint_lists_needs_and_room(client):
    body = client.get("/api/finance/needs").json()
    assert body["needs"] and body["room"]
    assert all(r["can_give"] > 0 for r in body["room"])


# --- revisions --------------------------------------------------------------
def test_a_revision_is_judged_on_its_combined_effect(db):
    short = F.needs(db)
    donor, room = min(((c, r) for c, r in _room(db) if r >= 500), key=lambda cr: cr[1])
    # Room is counted in $250 steps and one step more must break a rule, so two moves
    # of half the room plus a step fit alone but together overshoot by a full step.
    each = room / 2 + 250
    a, b = [n.code for n in short if n.need >= each][:2]
    one = [{"from_line": donor, "to_line": a, "amount": each}]
    assert F.revision_problem(db, one) is None, "each move fits on its own"
    both = one + [{"from_line": donor, "to_line": b, "amount": each}]
    problem = F.revision_problem(db, both)
    assert problem and donor in problem, "together they take more than the donor can give"


def test_a_revision_refuses_healthy_recipients_overshoots_and_two_way_lines(db):
    need = F.needs(db)[0]
    donor, _ = _room(db)[0]
    healthy = next(p.code for p in F.positions(db) if p.status == "good" and p.code != donor)
    assert "does not need money" in F.revision_problem(
        db, [{"from_line": donor, "to_line": healthy, "amount": 100}])
    assert "needs about" in F.revision_problem(
        db, [{"from_line": donor, "to_line": need.code, "amount": need.need * 3}])
    assert "both give and receive" in F.revision_problem(
        db, [{"from_line": donor, "to_line": need.code, "amount": 100},
             {"from_line": need.code, "to_line": F.needs(db)[1].code, "amount": 50}])


def test_agent_revision_is_recorded_then_applied_as_transfers(db, ledger):
    short = F.needs(db)[:2]
    donors = _room(db)
    moves = [{"from_line": donors[i][0], "to_line": n.code, "amount": round(min(n.need, donors[i][1]), 2)}
             for i, n in enumerate(short)]
    ctx: dict = {"proposals": []}
    T.propose_budget_revision(db, ctx, moves=moves, reason="Cover the two largest shortfalls.")
    spec = ctx["proposals"][0]
    assert spec["kind"] == "budget_revision" and len(spec["payload"]["moves"]) == 2

    allocated = {ln.code: ln.allocated for ln in db.scalars(select(BudgetLine)).all()}
    p = Proposal(agent="finance", kind=spec["kind"], summary=spec["summary"], reason=spec["reason"],
                 payload=spec["payload"], evidence=spec["evidence"], status="pending")
    db.add(p)
    db.commit()
    before = {x.code: x for x in F.positions(db)}
    apply_proposal(db, p)
    after = {x.code: x for x in F.positions(db)}
    for m in moves:
        assert after[m["to_line"]].budget == pytest.approx(before[m["to_line"]].budget + m["amount"])
    assert {ln.code: ln.allocated for ln in db.scalars(select(BudgetLine)).all()} == allocated, \
        "allocations are never edited"


def test_revision_is_refused_whole_if_the_budget_changed(db, ledger):
    n = F.needs(db)[0]
    donor, room = _room(db)[0]
    ctx: dict = {"proposals": []}
    T.propose_budget_revision(db, ctx, moves=[{"from_line": donor, "to_line": n.code,
                                               "amount": round(min(n.need, room), 2)}], reason="x" * 10)
    spec = ctx["proposals"][0]
    p = Proposal(agent="finance", kind=spec["kind"], summary="t", reason="t", payload=spec["payload"],
                 evidence=[], status="pending")
    db.add(p)
    db.commit()
    line = db.scalar(select(BudgetLine).where(BudgetLine.code == donor))
    drain = Transaction(line_id=line.id, posted_on=F.settings.today, vendor="Test", description="drain",
                        amount=F.positions(db)[[x.code for x in F.positions(db)].index(donor)].available)
    db.add(drain)
    db.commit()
    try:
        transfers = db.query(BudgetTransfer).count()
        with pytest.raises(ApplyError, match="none of it was applied"):
            apply_proposal(db, p)
        assert db.query(BudgetTransfer).count() == transfers
    finally:
        db.rollback()
        db.delete(db.get(Transaction, drain.id))
        db.commit()


def test_agent_revision_citing_invented_dollars_is_sent_back(db):
    n = F.needs(db)[0]
    donor, room = _room(db)[0]
    with pytest.raises(ToolError, match="not in the budget data"):
        T.propose_budget_revision(db, {"proposals": []}, moves=[
            {"from_line": donor, "to_line": n.code, "amount": round(min(n.need, room), 2)}],
            reason="The line is $48,211 short after the district audit.")


def test_a_refused_revision_says_where_money_is_needed_and_who_can_give(db):
    with pytest.raises(ToolError) as e:
        T.propose_budget_revision(db, {"proposals": []}, moves=[
            {"from_line": "PE-EQP", "to_line": "SPD-TRV", "amount": 100}], reason="x" * 10)
    assert "Where money is needed" in str(e.value) and "Lines that can give" in str(e.value)


# --- opening a line ---------------------------------------------------------
def test_new_line_rules(db):
    donor, room = _room(db)[0]
    ok = dict(code="MAT-WKS", name="Word-problems workshops", department="Mathematics",
              category="Programs", from_line=donor, amount=min(1500, room))
    assert F.new_line_problem(db, **ok) is None
    assert "not a line code" in F.new_line_problem(db, **(ok | {"code": "maths workshops"}))
    assert "already exists" in F.new_line_problem(db, **(ok | {"code": "MAT-INS"}))
    assert "No department" in F.new_line_problem(db, **(ok | {"department": "Maths"}))
    assert "cannot give" in F.new_line_problem(db, **(ok | {"amount": 10_000_000}))
    over = next(p.code for p in F.positions(db) if p.status == "critical")
    assert F.new_line_problem(db, **(ok | {"from_line": over, "amount": 100})) is not None


def test_agent_opens_a_line_at_zero_funded_by_a_transfer(client, db, ledger):
    donor, room = _room(db)[0]
    ctx: dict = {"proposals": []}
    amount = min(1500.0, room)
    T.propose_new_budget_line(db, ctx, code="MAT-WKS", name="Algebra 1 word-problems workshops",
                              department="Mathematics", category="Programs", from_line=donor, amount=amount,
                              reason="Workshops for Algebra 1 word problems; no existing line pays for workshops.")
    spec = ctx["proposals"][0]
    p = Proposal(agent="finance", kind=spec["kind"], summary=spec["summary"], reason=spec["reason"],
                 payload=spec["payload"], evidence=spec["evidence"], status="pending")
    db.add(p)
    db.commit()
    apply_proposal(db, p)
    line = next(x for x in client.get("/api/finance/lines").json() if x["code"] == "MAT-WKS")
    assert line["allocated"] == 0 and line["budget"] == amount and line["transfers_in"] == amount
    assert line["owner"] == "S. Frankel", "a new line is owned by its department's existing owner"
    with pytest.raises(ApplyError, match="already exists"):
        apply_proposal(db, Proposal(agent="finance", kind="budget_line", summary="t", reason="t",
                                    payload=spec["payload"], evidence=[], status="pending"))


def test_agent_new_line_needs_a_real_category_and_reason(db):
    donor, room = _room(db)[0]
    base = dict(code="MAT-WKS", name="Workshops", department="Mathematics", category="Programs",
                from_line=donor, amount=min(500, room), reason="Workshops no existing line pays for, all year.")
    with pytest.raises(ToolError, match="No category"):
        T.propose_new_budget_line(db, {"proposals": []}, **(base | {"category": "Fun"}))
    with pytest.raises(ToolError, match="reason must say"):
        T.propose_new_budget_line(db, {"proposals": []}, **(base | {"reason": "needed"}))


def test_person_can_open_a_line_and_revise_through_the_api(client, db, ledger):
    donor, room = _room(db)[0]
    r = client.post("/api/finance/lines", json={
        "code": "ENG-WRK", "name": "Writing workshop visiting authors", "department": "English",
        "category": "Programs", "from_line": donor, "amount": min(800, room), "reason": "Visiting authors"})
    assert r.status_code == 201, r.text
    assert r.json()["allocated"] == 0 and r.json()["budget"] == min(800, room)
    assert client.post("/api/finance/lines", json={
        "code": "ENG-WRK", "name": "Again", "department": "English", "category": "Programs",
        "from_line": donor, "amount": 100, "reason": "again"}).status_code == 409

    n = F.needs(db)[0]
    donor, room = _room(db)[0]
    r = client.post("/api/finance/revisions", json={
        "moves": [{"from_line": donor, "to_line": n.code, "amount": round(min(n.need, room), 2)}],
        "reason": "Cover the largest shortfall"})
    assert r.status_code == 201, r.text
    assert len(r.json()["transfers"]) == 1
    assert client.post("/api/finance/revisions", json={
        "moves": [{"from_line": donor, "to_line": donor, "amount": 10}], "reason": "self"}).status_code == 409


def test_finance_agent_moves_money_only_by_revision():
    names = {t.name for t in FLEET["finance"].tools}
    assert {"propose_budget_revision", "propose_new_budget_line"} <= names
    assert "propose_budget_transfer" not in names, (
        "observed live: given both, the model funded one of five short lines with a transfer and stopped")
