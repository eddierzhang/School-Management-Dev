"""The master schedule and a student's timetable."""
from sqlalchemy import select

from app.models import Course, Enrollment, Student


def test_school_schedule_places_every_section_once(client):
    s = client.get("/api/schedule").json()
    assert len(s["sections"]) == 26
    assert s["periods"][:7] == [1, 2, 3, 4, 5, 6, 7]
    assert all(sec["period"] in s["periods"] for sec in s["sections"])
    assert set(s["rooms"]) == {sec["room"] for sec in s["sections"]}


def test_seeded_timetable_has_no_room_or_teacher_clash(client):
    assert client.get("/api/schedule").json()["clashes"] == []


def test_a_double_booked_room_is_reported(client, db):
    src = db.scalar(select(Course).where(Course.code == "MAT-150"))
    other = db.scalar(select(Course).where(Course.code == "SCI-118"))
    was = (other.period, other.room)
    other.period, other.room = src.period, src.room
    db.commit()
    try:
        clashes = client.get("/api/schedule").json()["clashes"]
        assert {"kind": "room", "who": src.room, "period": src.period,
                "sections": ["MAT-150", "SCI-118"]} in clashes
    finally:
        other.period, other.room = was
        db.commit()


def test_student_clashes_in_the_school_view_match_each_timetable(client):
    s = client.get("/api/schedule").json()
    assert s["students_with_clashes"] == len({c["sid"] for c in s["student_clashes"]})
    for c in s["student_clashes"][:5]:
        mine = client.get(f"/api/students/{c['sid']}/schedule").json()
        row = next(p for p in mine["periods"] if p["period"] == c["period"])
        assert row["clash"] and sorted(x["code"] for x in row["enrolled"]) == c["sections"]


def test_student_timetable_accounts_for_every_enrollment(client, db):
    st = db.scalar(select(Student).where(Student.sid == "S-1507"))
    rows = db.scalars(select(Enrollment).where(Enrollment.student_id == st.id)).all()
    t = client.get("/api/students/S-1507/schedule").json()
    enrolled = [x["code"] for p in t["periods"] for x in p["enrolled"]]
    waiting = [x["code"] for p in t["periods"] for x in p["waitlisted"]]
    assert len(enrolled) == t["classes"] == sum(1 for e in rows if e.status == "enrolled")
    assert len(waiting) == t["waitlisted"] == sum(1 for e in rows if e.status == "waitlist")
    busy = {p["period"] for p in t["periods"] if p["enrolled"]}
    assert set(t["free_periods"]).isdisjoint(busy)
    assert t["clashes"] == sum(1 for p in t["periods"] if p["clash"])


def test_waitlisted_classes_are_shown_but_not_counted_as_classes(client, db):
    e = db.scalar(select(Enrollment).where(Enrollment.status == "waitlist"))
    sid = db.get(Student, e.student_id).sid
    t = client.get(f"/api/students/{sid}/schedule").json()
    assert t["waitlisted"] >= 1
    assert any(p["waitlisted"] for p in t["periods"])


def test_unknown_student_schedule_is_404(client):
    assert client.get("/api/students/S-0000/schedule").status_code == 404
