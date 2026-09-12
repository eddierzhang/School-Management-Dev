"""Demand ranking and opening classes.

Every test that opens something removes it again: the API tests assert the
seeded catalogue has exactly 26 sections.
"""
from sqlalchemy import select

from app.demand import band_of, score
from app.models import Course, Enrollment


def _remove(db, code: str, restore_to: str | None = None) -> None:
    db.expire_all()
    c = db.scalar(select(Course).where(Course.code == code))
    if c is None:
        return
    if restore_to:
        src = db.scalar(select(Course).where(Course.code == restore_to))
        for e in db.scalars(select(Enrollment).where(Enrollment.course_id == c.id)).all():
            e.course_id, e.status = src.id, "waitlist"
        db.flush()
    db.delete(c)
    db.commit()


# --- the index -------------------------------------------------------------
def test_score_matches_the_published_formula():
    # full, a waitlist of half a section, 6 signups against a scale of 12
    value, fill, pressure, velocity = score(enrolled=20, capacity=20, waitlist=10, signups=[9, 9, 3, 3])
    assert (fill, pressure, velocity) == (1.0, 0.5, 0.5)
    assert value == round(100 * (0.40 + 0.35 * 0.5 + 0.25 * 0.5))


def test_components_are_capped_so_one_signal_cannot_swamp_the_others():
    value, *_ = score(enrolled=20, capacity=20, waitlist=400, signups=[900, 900])
    assert value == 100


def test_bands_cover_every_score():
    assert band_of(100)[1] == "Over-subscribed"
    assert band_of(52)[1] == "High demand"
    assert band_of(51)[1] == "Healthy"
    assert band_of(0)[1] == "Seats to fill"


def test_demand_ranks_waitlisted_classes_above_half_empty_ones(client):
    r = client.get("/api/courses/demand").json()
    classes = r["classes"]
    assert len(classes) == 26
    scores = [c["score"] for c in classes]
    assert scores == sorted(scores, reverse=True)
    top, bottom = classes[0], classes[-1]
    assert top["waitlist"] > 0 and top["action"] == "open-section"
    assert bottom["label"] == "Seats to fill" and bottom["waitlist"] == 0
    assert bottom["action"] in ("promote", "review")
    assert "0.40" in r["formula"]


def test_courses_list_reports_waitlists(client):
    rows = {c["code"]: c for c in client.get("/api/courses").json()}
    assert rows["SCI-210"]["waitlist"] == 19


# --- opening a section -----------------------------------------------------
def test_opening_a_section_moves_the_waitlist_and_relieves_demand(client, db):
    before = next(c for c in client.get("/api/courses/demand").json()["classes"] if c["code"] == "SCI-210")
    period = 6
    room = client.get("/api/courses/openings", params={"period": period}).json()["free_rooms"][0]
    try:
        r = client.post("/api/courses/SCI-210/sections",
                        json={"period": period, "room": room, "capacity": 24, "move_from_waitlist": 19})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["course"]["code"] == "SCI-210.B"
        assert body["moved_from_waitlist"] == 19
        assert body["course"]["title"] == "Forensic Science"

        after = next(c for c in client.get("/api/courses/demand").json()["classes"] if c["code"] == "SCI-210")
        assert [s["code"] for s in after["sections"]] == ["SCI-210", "SCI-210.B"]
        assert after["waitlist"] == 0 and after["enrolled"] == before["enrolled"] + 19
        assert after["score"] < before["score"]
    finally:
        _remove(db, "SCI-210.B", restore_to="SCI-210")


def test_a_section_cannot_take_a_room_already_in_use(client):
    src = next(c for c in client.get("/api/courses").json() if c["code"] == "SCI-210")
    r = client.post("/api/courses/TEC-130/sections", json={"period": src["period"], "room": src["room"]})
    assert r.status_code == 409
    assert "already used" in r.json()["detail"]


def test_a_teacher_cannot_teach_two_sections_at_once(client):
    src = next(c for c in client.get("/api/courses").json() if c["code"] == "SCI-210")
    r = client.post("/api/courses/SCI-210/sections",
                    json={"period": src["period"], "room": "NOWHERE-1", "teacher": src["teacher"]})
    assert r.status_code == 409
    assert "already teaches" in r.json()["detail"]


def test_section_of_an_unknown_class_is_404(client):
    assert client.post("/api/courses/XXX-999/sections", json={"period": 1, "room": "A"}).status_code == 404


# --- opening a new class ---------------------------------------------------
def test_opening_a_new_class(client, db):
    free = client.get("/api/courses/openings", params={"period": 8}).json()
    try:
        r = client.post("/api/courses", json={
            "code": "art-155", "title": "Printmaking", "dept": "Visual Arts",
            "teacher": free["free_teachers"][0], "period": 8, "room": free["free_rooms"][0],
            "capacity": 18, "description": "Relief, intaglio and screen printing."})
        assert r.status_code == 201, r.text
        assert r.json()["course"]["code"] == "ART-155"
        row = next(c for c in client.get("/api/courses/demand").json()["classes"] if c["code"] == "ART-155")
        assert row["enrolled"] == 0 and row["label"] == "Seats to fill"

        dup = client.post("/api/courses", json={
            "code": "ART-155", "title": "Again", "dept": "Visual Arts", "teacher": "X. Y",
            "period": 0, "room": "Z", "capacity": 10})
        assert dup.status_code == 409
    finally:
        _remove(db, "ART-155")


def test_a_new_class_code_must_be_well_formed(client):
    r = client.post("/api/courses", json={"code": "ART-155.B", "title": "Printmaking", "dept": "Arts",
                                          "teacher": "A. B", "period": 0, "room": "A", "capacity": 10})
    assert r.status_code == 422
