"""Stockroom API tests.

Mutating tests restore what they touched: the seeded stockroom is shared with the
agent tests, which pick "an item that is not on the requisition" and would fail
against a stockroom this module had flagged wholesale.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai import tools as T
from app.models import InventoryItem
from app.stock import status_of


@pytest.fixture
def restore_stock():
    """Snapshot every mutable stockroom field, put it all back afterwards."""
    from app.db import SessionLocal

    s = SessionLocal()
    before = {i.sku: (i.on_hand, i.reorder_point, i.par, i.requisitioned, i.last_counted)
              for i in s.scalars(select(InventoryItem)).all()}
    s.close()
    yield
    s = SessionLocal()
    try:
        for item in s.scalars(select(InventoryItem)).all():
            if item.sku not in before:
                s.delete(item)
                continue
            (item.on_hand, item.reorder_point, item.par,
             item.requisitioned, item.last_counted) = before[item.sku]
        s.commit()
    finally:
        s.close()


# --- reading ---------------------------------------------------------------
def test_lists_the_whole_stockroom(client):
    rows = client.get("/api/inventory").json()
    assert len(rows) == 24
    for r in rows:
        assert r["status"] in ("critical", "serious", "warning", "good")
        assert 0 <= r["ratio"] <= 1
        assert r["short_by"] >= 0


def test_worst_items_come_first(client):
    rows = client.get("/api/inventory").json()
    gaps = [r["on_hand"] - r["reorder_point"] for r in rows]
    assert gaps == sorted(gaps), "the stockroom is ordered by how far under the reorder point"


def test_filters(client):
    low = client.get("/api/inventory", params={"needs_attention": True}).json()
    assert low and all(r["status"] in ("critical", "serious") for r in low)
    assert len(low) < 24

    sci = client.get("/api/inventory", params={"category": "Science Lab"}).json()
    assert sci and all(r["category"] == "Science Lab" for r in sci)

    hit = client.get("/api/inventory", params={"q": "fingerprint"}).json()
    assert len(hit) == 1 and hit[0]["sku"] == "SCI-FPK-020"

    by_course = client.get("/api/inventory", params={"q": "SCI-210"}).json()
    assert by_course, "searching a course code should find the items it consumes"


def test_summary_adds_up(client):
    s = client.get("/api/inventory/summary").json()
    rows = client.get("/api/inventory").json()
    assert s["items"] == len(rows) == 24
    assert s["needs_attention"] == sum(1 for r in rows if r["status"] in ("critical", "serious"))
    assert s["below_reorder"] == sum(1 for r in rows if r["on_hand"] <= r["reorder_point"])
    assert s["value_on_hand"] > 0
    assert "Science Lab" in s["categories"]


def test_detail_names_the_classes_that_depend_on_it(client):
    d = client.get("/api/inventory/SCI-FPK-020").json()
    assert d["sku"] == "SCI-FPK-020"
    assert [c["code"] for c in d["classes"]] == ["SCI-210"]
    assert d["classes"][0]["enrolled"] > 0
    assert d["students_affected"] == d["classes"][0]["enrolled"]
    assert d["value_on_hand"] == pytest.approx(d["on_hand"] * d["unit_cost"], abs=0.01)


def test_unknown_sku_is_404(client):
    assert client.get("/api/inventory/NOPE-999").status_code == 404


def test_lowercase_sku_still_resolves(client):
    assert client.get("/api/inventory/sci-fpk-020").json()["sku"] == "SCI-FPK-020"


# --- the shared rule -------------------------------------------------------
def test_the_api_and_the_agent_agree_on_what_is_low(client, db):
    """One definition of "low" — app/stock.py — or an agent proposes an order for
    something the screen calls healthy."""
    api_low = {r["sku"] for r in client.get("/api/inventory", params={"needs_attention": True}).json()}
    agent_low = {i["sku"] for i in T.list_low_stock(db, {"proposals": []}, category=None)["items"]}
    # The agent's list caps at LIST_CAP, so it must be a subset of the API's, not equal.
    assert agent_low <= api_low, agent_low - api_low
    for item in db.scalars(select(InventoryItem)).all():
        if item.on_hand <= item.reorder_point:
            assert status_of(item).needs_attention, f"{item.sku} is at or below reorder but not flagged"


# --- writing ---------------------------------------------------------------
def test_adjusting_on_hand_moves_the_status(client, restore_stock):
    before = client.get("/api/inventory/GEN-PPR-CAS").json()
    assert before["status"] == "good"
    after = client.patch("/api/inventory/GEN-PPR-CAS", json={"on_hand": 0}).json()
    assert after["on_hand"] == 0
    assert after["status"] == "critical"
    assert after["short_by"] == after["par"]


def test_reorder_point_above_par_is_refused(client, restore_stock):
    item = client.get("/api/inventory/GEN-PPR-CAS").json()
    r = client.patch("/api/inventory/GEN-PPR-CAS", json={"reorder_point": item["par"] + 1})
    assert r.status_code == 422
    assert "par level" in r.json()["detail"]


def test_empty_patch_is_refused(client):
    assert client.patch("/api/inventory/GEN-PPR-CAS", json={}).status_code == 422


def test_negative_values_are_refused(client):
    assert client.patch("/api/inventory/GEN-PPR-CAS", json={"on_hand": -1}).status_code == 422
    assert client.patch("/api/inventory/GEN-PPR-CAS", json={"par": 0}).status_code == 422


def test_recording_a_count_stamps_the_date(client, restore_stock):
    from app.config import get_settings

    d = client.post("/api/inventory/MAT-GRD-PAD/count", json={"on_hand": 7}).json()
    assert d["on_hand"] == 7
    assert d["last_counted"] == get_settings().today.isoformat()
    assert d["days_since_count"] == 0


# --- the requisition -------------------------------------------------------
def test_requisition_groups_by_supplier(client, restore_stock):
    client.patch("/api/inventory/SCI-FPK-020", json={"requisitioned": True})
    client.patch("/api/inventory/SCI-GLV-NIT", json={"requisitioned": True})
    req = client.get("/api/inventory/requisition").json()
    assert req["lines"] >= 2
    assert req["cost"] == pytest.approx(sum(g["cost"] for g in req["by_supplier"]), abs=0.01)
    for group in req["by_supplier"]:
        assert group["lines"]
        assert all(line["supplier"] == group["supplier"] for line in group["lines"])
        assert group["cost"] == pytest.approx(
            sum(line["cost_to_par"] for line in group["lines"]), abs=0.01)


def test_requisitioning_everything_low_covers_every_flagged_item(client, restore_stock):
    flagged = {r["sku"] for r in client.get("/api/inventory", params={"needs_attention": True}).json()}
    req = client.post("/api/inventory/requisition/low").json()
    on_req = {line["sku"] for g in req["by_supplier"] for line in g["lines"]}
    assert flagged <= on_req
    assert req["cost"] > 0


# --- adding and removing ---------------------------------------------------
def test_add_an_item(client, restore_stock):
    body = {"sku": "art-brs-12", "name": "Bristle brush, size 12", "category": "Arts",
            "unit": "unit", "on_hand": 30, "reorder_point": 10, "par": 40,
            "unit_cost": 2.5, "linked_courses": ["ART-140"]}
    d = client.post("/api/inventory", json=body)
    assert d.status_code == 201, d.text
    created = d.json()
    assert created["sku"] == "ART-BRS-12", "SKUs are normalised to upper case"
    assert created["status"] == "good"
    assert [c["code"] for c in created["classes"]] == ["ART-140"]
    assert client.post("/api/inventory", json=body).status_code == 409
    assert client.delete("/api/inventory/ART-BRS-12").status_code == 204
    assert client.get("/api/inventory/ART-BRS-12").status_code == 404


def test_add_rejects_an_unknown_class(client):
    r = client.post("/api/inventory", json={
        "sku": "TST-001", "name": "Test item", "linked_courses": ["XXX-999"]})
    assert r.status_code == 404
    assert "XXX-999" in r.json()["detail"]


def test_add_rejects_reorder_above_par(client):
    r = client.post("/api/inventory", json={
        "sku": "TST-002", "name": "Test item", "reorder_point": 50, "par": 10})
    assert r.status_code == 422
