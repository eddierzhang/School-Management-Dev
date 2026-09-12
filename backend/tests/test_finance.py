"""Finance tests: the budget engine, the API, and the finance agent's boundaries.

Fresh seed, so no stockroom requisitions are open and commitments start at zero.
Mutating tests remove what they add.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app import finance as F
from app.ai import tools as T
from app.ai.executor import ApplyError, apply_proposal
from app.ai.toolkit import ToolError
from app.models import BudgetTransfer, InventoryItem, Proposal, Transaction


def _pos(client, code):
    return next(l for l in client.get("/api/finance/lines").json() if l["code"] == code)


# --- the pure rule ----------------------------------------------------------
def test_one_time_purchases_are_not_extrapolated():
    # $11,480 laptop refresh plus $1,240 recurring, a fifth of the way through the year.
    status, _, projected, _ = F.classify(22000, 12720, 11480, 0, 0.2, date(2026, 9, 12))
    assert status == "good"
    assert projected == pytest.approx(11480 + 1240 / 0.2)
    # The same spend, all treated as recurring, would wrongly read as a runaway line.
    assert F.classify(22000, 12720, 0, 0, 0.2, date(2026, 9, 12))[0] == "serious"


def test_commitments_count_before_they_are_paid():
    assert F.classify(5000, 4000, 0, 1500, 0.2, date(2026, 9, 12))[0] == "critical"


def test_underspending_waits_out_the_first_six_weeks():
    assert F.classify(8500, 0, 0, 0, 0.05, date(2026, 7, 20))[0] == "good"
    assert F.classify(8500, 100, 0, 0, 0.2, date(2026, 9, 12))[0] == "warning"


# --- the seeded year ---------------------------------------------------------
def test_seeded_situations_are_found(client):
    by = {l["code"]: l for l in client.get("/api/finance/lines").json()}
    assert by["PE-EQP"]["status_label"] == "Over budget"
    assert by["SPD-TRV"]["status_label"] == "At risk"
    assert by["FAC-MNT"]["status_label"] == "At risk"
    assert by["ART-STU"]["status_label"] == "Under-spending"
    assert by["CSC-TEC"]["status_label"] == "On track", "the one-time refresh must not look like a runaway"


def test_anomalies_find_the_duplicate_and_skip_reviewed_purchases(client):
    rows = client.get("/api/finance/anomalies").json()
    rules = {(a["rule"], a["vendor"]) for a in rows}
    assert ("possible duplicate", "Bayside HVAC Services") in rules
    assert ("large single charge", "Petzl Education") in rules
    assert not any(a["vendor"] == "CDW Education" for a in rows), "a reviewed planned purchase is not raised"


def test_summary_adds_up(client):
    s = client.get("/api/finance/summary").json()
    lines = client.get("/api/finance/lines").json()
    assert s["budget"] == pytest.approx(sum(l["budget"] for l in lines))
    assert s["available"] == pytest.approx(s["budget"] - s["spent"] - s["committed"])
    assert s["over"] == sum(1 for l in lines if l["status"] == "critical")


# --- stockroom -> finance ----------------------------------------------------
def test_approving_a_requisition_commits_money_on_the_right_line(client, db):
    before = _pos(client, "SCI-LAB")["committed"]
    item = db.scalar(select(InventoryItem).where(InventoryItem.sku == "SCI-FPK-020"))
    was = item.requisitioned
    try:
        client.patch("/api/inventory/SCI-FPK-020", json={"requisitioned": True})
        after = _pos(client, "SCI-LAB")
        assert after["committed"] > before
        assert any(c["sku"] == "SCI-FPK-020" for c in after["commitments"])
    finally:
        client.patch("/api/inventory/SCI-FPK-020", json={"requisitioned": was})


# --- recording and reviewing ------------------------------------------------
def test_record_a_charge_moves_the_line(client, db):
    before = _pos(client, "ENG-INS")["spent"]
    r = client.post("/api/finance/transactions", json={
        "line_code": "ENG-INS", "vendor": "Test Books", "description": "Test set", "amount": 99.5})
    assert r.status_code == 201, r.text
    try:
        assert _pos(client, "ENG-INS")["spent"] == pytest.approx(before + 99.5)
    finally:
        db.delete(db.get(Transaction, r.json()["id"])); db.commit()


@pytest.mark.parametrize("body,code", [
    ({"line_code": "NOPE", "vendor": "x y", "description": "x y", "amount": 5}, 404),
    ({"line_code": "ENG-INS", "vendor": "x y", "description": "x y", "amount": 0}, 422),
    ({"line_code": "ENG-INS", "vendor": "x y", "description": "x y", "amount": 5, "posted_on": "2030-01-01"}, 422),
    ({"line_code": "ENG-INS", "vendor": "x y", "description": "x y", "amount": 5, "posted_on": "2026-06-01"}, 422),
])
def test_record_validation(client, body, code):
    assert client.post("/api/finance/transactions", json=body).status_code == code


def test_transfer_rules(client, db):
    assert client.post("/api/finance/transfers", json={
        "from_line": "PE-EQP", "to_line": "SPD-TRV", "amount": 100, "reason": "from an overspent line"}).status_code == 409
    assert client.post("/api/finance/transfers", json={
        "from_line": "SUP-TUT", "to_line": "SUP-TUT", "amount": 100, "reason": "same line"}).status_code == 422
    r = client.post("/api/finance/transfers", json={
        "from_line": "SUP-TUT", "to_line": "SPD-TRV", "amount": 500, "reason": "cover travel pace"})
    assert r.status_code == 201, r.text
    try:
        dst = _pos(client, "SPD-TRV")
        assert dst["transfers_in"] == 500 and dst["allocated"] == 14000, "allocations are never edited"
    finally:
        db.delete(db.get(BudgetTransfer, r.json()["id"])); db.commit()


# --- the agent's boundaries -------------------------------------------------
def test_agent_cannot_move_money_into_a_healthy_line(db):
    with pytest.raises(ToolError, match="Over budget or At risk"):
        T.propose_budget_transfer(db, {"proposals": []}, "SUP-TUT", "SCI-LAB", 300, "x")


def test_agent_cannot_overshoot_the_need(db):
    with pytest.raises(ToolError, match="needs about"):
        T.propose_budget_transfer(db, {"proposals": []}, "PRO-DEV", "SPD-TRV", 9000, "x")


def test_agent_proposal_is_revalidated_when_approved(db):
    ctx = {"proposals": []}
    T.propose_budget_transfer(db, ctx, "SUP-TUT", "SPD-TRV", 400, "travel pace")
    spec = ctx["proposals"][0]
    p = Proposal(agent="finance", kind=spec["kind"], summary=spec["summary"], reason=spec["reason"],
                 payload=spec["payload"], evidence=spec["evidence"], status="pending")
    db.add(p); db.commit()
    # Before approval, the tutoring line spends nearly everything it has.
    big = Transaction(line_id=db.scalar(select(Transaction).join(Transaction.line)
                                        .where(Transaction.vendor == "Bright Path Tutoring")).line_id,
                      posted_on=date(2026, 9, 12), vendor="Test", description="drain", amount=17200)
    db.add(big); db.commit()
    try:
        with pytest.raises(ApplyError, match="changed since"):
            apply_proposal(db, p)
    finally:
        db.rollback()
        db.delete(db.get(Transaction, big.id)); db.delete(db.get(Proposal, p.id)); db.commit()


def test_agent_review_proposal_holds_the_charge(db):
    dup = next(a for a in F.anomalies(db) if a["rule"] == "possible duplicate")
    ctx = {"proposals": []}
    T.propose_transaction_review(db, ctx, dup["transaction_id"], "Invoice paid twice.", "duplicate rule")
    spec = ctx["proposals"][0]
    p = Proposal(agent="finance", kind=spec["kind"], summary=spec["summary"], reason=spec["reason"],
                 payload=spec["payload"], evidence=spec["evidence"], status="pending")
    db.add(p); db.commit()
    t = db.get(Transaction, dup["transaction_id"])
    try:
        apply_proposal(db, p)
        db.refresh(t)
        assert t.review_status == "flagged"
        with pytest.raises(ToolError, match="already flagged"):
            T.propose_transaction_review(db, {"proposals": []}, t.id, "again", "again")
    finally:
        t.review_status, t.review_note = "clear", ""
        db.delete(db.get(Proposal, p.id)); db.commit()


def test_every_suggested_donor_can_really_give_what_it_says(db):
    """Regression: shown only problem lines, the live agent tried four transfers from
    lines that were themselves at risk. Donors are now listed — and must be real."""
    donors = T.list_budget_status(db, {"proposals": []}, only_problems=True)["lines_with_room"]
    assert donors, "the agent must be shown somewhere money can come from"
    for d in donors:
        assert F.transfer_problem(db, d["code"], "SPD-TRV", d["can_give_up_to"]) is None, d
        # and it is the most: one more step would break a rule
        assert F.transfer_problem(db, d["code"], "SPD-TRV", d["can_give_up_to"] + 250) is not None, d


def test_a_refused_transfer_names_lines_that_can_give(db):
    with pytest.raises(ToolError, match="Lines that can give"):
        T.propose_budget_transfer(db, {"proposals": []}, "FAC-MNT", "PE-EQP", 1056, "x")
