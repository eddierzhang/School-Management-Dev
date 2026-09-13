"""Importing from the student information system (OneRoster 1.1 CSV).

Every test that writes runs the import inside the test's own transaction and rolls
it back, so the seeded school the other tests rely on is never changed.
"""
import csv
import io
import zipfile

import pytest
from sqlalchemy import select

from app import importer
from app.analytics import build_signals
from app.models import Assessment, Course, Enrollment, Score, Student, User


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode()


def export(**changes) -> dict[str, bytes]:
    """A small school: two students, one guardian, a teacher, one class, three assessments."""
    files = {
        "users.csv": _csv(
            ["sourcedId", "status", "role", "username", "identifier", "givenName", "familyName", "grades", "email",
             "agentSourcedIds"],
            [["u1", "active", "student", "ada", "OR-001", "Ada", "Lovelace", "10", "", "g1"],
             ["u2", "active", "student", "alan", "OR-002", "Alan", "Turing", "09", "", ""],
             ["g1", "active", "parent", "", "", "Anne", "Lovelace", "", "anne@example.org", ""],
             ["t1", "active", "teacher", "", "", "Grace", "Hopper", "", "g.hopper@import.example.edu", ""]]),
        "courses.csv": _csv(["sourcedId", "title", "subjects"], [["c1", "Geometry", "Mathematics"]]),
        "academicSessions.csv": _csv(["sourcedId", "title"], [["term1", "Fall 2026"]]),
        "classes.csv": _csv(
            ["sourcedId", "status", "title", "courseSourcedId", "classCode", "periods", "location", "termSourcedIds"],
            [["k1", "active", "Geometry P7", "c1", "OR-GEO", "7", "Room 99", "term1"]]),
        "enrollments.csv": _csv(
            ["sourcedId", "classSourcedId", "userSourcedId", "role", "primary"],
            [["e1", "k1", "u1", "student", "false"], ["e2", "k1", "u2", "student", "false"],
             ["e3", "k1", "t1", "teacher", "true"]]),
        "categories.csv": _csv(["sourcedId", "title"], [["cat1", "Tests"], ["cat2", "Homework"]]),
        "lineItems.csv": _csv(
            ["sourcedId", "title", "classSourcedId", "categorySourcedId", "assignDate", "dueDate", "resultValueMax", "skill"],
            [["li1", "Proofs quiz", "k1", "cat1", "2026-08-20", "2026-08-25", "20", "proofs"],
             ["li2", "Angles homework", "k1", "cat2", "2026-08-26", "2026-08-28", "10", "angles"],
             ["li3", "Unit test", "k1", "cat1", "2026-09-01", "2026-09-04", "100", "proofs"]]),
        "results.csv": _csv(
            ["sourcedId", "lineItemSourcedId", "studentSourcedId", "scoreStatus", "score", "scoreDate"],
            [["r1", "li1", "u1", "fully graded", "8", "2026-08-26"],
             ["r2", "li2", "u1", "not submitted", "", ""],
             ["r3", "li3", "u1", "exempt", "", ""],
             ["r4", "li1", "u2", "fully graded", "19", "2026-08-26"],
             ["r5", "li2", "u2", "fully graded", "9", "2026-08-29"],
             ["r6", "li3", "u2", "fully graded", "91", "2026-09-05"]]),
        "attendance.csv": _csv(["userSourcedId", "date", "status"],
                               [["u1", "2026-09-01", "absent"], ["u1", "2026-09-02", "present"]]),
    }
    files.update(changes)
    return files


def parsed(files: dict[str, bytes]):
    return {name: importer._parse(name, data) for name, data in files.items()}


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(f"export/{name}", data)
    return buf.getvalue()


@pytest.fixture
def scratch(db):
    """The import's writes, visible to the test and rolled back afterwards."""
    yield db
    db.rollback()


def test_a_dry_run_reports_everything_and_writes_nothing(db):
    r = importer.run_import(db, parsed(export()))
    assert not r.errors and not r.applied, r.errors
    assert r.created == {"students": 2, "classes": 1, "enrollments": 2, "assessments": 3, "scores": 6,
                         "attendance days": 2}
    assert db.scalar(select(Student).where(Student.sid == "OR-001")) is None


def test_applying_creates_the_school_as_exported(scratch):
    r = importer.run_import(scratch, parsed(export()), apply=True, commit=False)
    assert r.applied and not r.errors
    ada = scratch.scalar(select(Student).where(Student.sid == "OR-001"))
    assert (ada.name, ada.grade, ada.guardian_name, ada.guardian_email) == ("Ada Lovelace", 10, "Anne Lovelace",
                                                                           "anne@example.org")
    geo = scratch.scalar(select(Course).where(Course.code == "OR-GEO"))
    assert (geo.title, geo.dept, geo.teacher, geo.period, geo.room) == ("Geometry", "Mathematics", "Grace Hopper", 7,
                                                                        "Room 99")
    kinds = {a.source_id: a.kind for a in scratch.scalars(select(Assessment).where(Assessment.course_id == geo.id))}
    assert kinds == {"li1": "quiz", "li2": "homework", "li3": "test"}


def test_exempt_work_is_neither_missing_nor_graded(scratch):
    importer.run_import(scratch, parsed(export()), apply=True, commit=False)
    exempt = scratch.scalar(select(Score).join(Assessment).where(Assessment.source_id == "li3",
                                                                 Score.exempt.is_(True)))
    assert exempt is not None
    geo = next(c for c in build_signals(scratch)["OR-001"].courses if c.course_code == "OR-GEO")
    assert (geo.graded_items, geo.missing) == (2, 1)       # the exempt test is not counted at all


def test_reimporting_the_same_export_changes_nothing(scratch):
    importer.run_import(scratch, parsed(export()), apply=True, commit=False)
    again = importer.run_import(scratch, parsed(export()), apply=True, commit=False)
    assert not again.created and not again.updated and again.dropped_enrollments == 0


def test_a_student_missing_from_the_roster_is_dropped_not_deleted(scratch):
    importer.run_import(scratch, parsed(export()), apply=True, commit=False)
    fewer = export(**{
        "enrollments.csv": _csv(["sourcedId", "classSourcedId", "userSourcedId", "role", "primary"],
                                [["e1", "k1", "u1", "student", "false"], ["e3", "k1", "t1", "teacher", "true"]]),
        "results.csv": _csv(["sourcedId", "lineItemSourcedId", "studentSourcedId", "scoreStatus", "score"], [])})
    r = importer.run_import(scratch, parsed(fewer), apply=True, commit=False)
    assert r.dropped_enrollments == 1 and not r.errors
    alan = scratch.scalar(select(Student).where(Student.sid == "OR-002"))
    assert alan is not None
    assert scratch.scalar(select(Enrollment.status).where(Enrollment.student_id == alan.id)) == "dropped"


def test_bad_references_refuse_the_whole_import(db):
    broken = export(**{
        "results.csv": _csv(["sourcedId", "lineItemSourcedId", "studentSourcedId", "scoreStatus", "score"],
                            [["r1", "li1", "nobody", "fully graded", "5"], ["r2", "li1", "u1", "fully graded", "25"]]),
        "users.csv": export()["users.csv"] + b"u3,active,student,x,OR-003,No,Grade,,,\n"})
    r = importer.run_import(db, parsed(broken), apply=True)
    messages = " | ".join(f"{i.file}:{i.line} {i.message}" for i in r.errors)
    assert not r.applied
    assert "nobody" in messages and "outside 0–20" in messages and "no readable grade" in messages
    assert db.scalar(select(Student).where(Student.sid == "OR-001")) is None


def test_missing_files_and_columns_are_named(db):
    files = export()
    del files["enrollments.csv"]
    files["classes.csv"] = _csv(["sourcedId"], [["k1"]])
    msgs = [i.message for i in importer.run_import(db, parsed(files)).errors]
    assert any("enrollments.csv is required" in m for m in msgs) and any("title" in m for m in msgs)


def test_timetable_problems_are_warned_about(db):
    clash = export(**{"classes.csv": _csv(
        ["sourcedId", "title", "courseSourcedId", "classCode", "periods", "location"],
        [["k1", "Geometry", "c1", "OR-GEO", "1", "Room 99"], ["k2", "Algebra", "c1", "OR-ALG", "1", "Room 99"]]),
        "enrollments.csv": _csv(["sourcedId", "classSourcedId", "userSourcedId", "role"],
                                [["e1", "k1", "u1", "student"], ["e2", "k2", "u1", "student"], ["e3", "k1", "t1", "teacher"],
                                 ["e4", "k2", "u2", "student"]])})
    r = importer.run_import(db, parsed(clash))
    text = " ".join(i.message for i in r.warnings)
    assert "Room 99" in text and "same period" in text and "no teacher" in text


def test_teacher_accounts_are_created_for_school_sign_in(scratch):
    importer.run_import(scratch, parsed(export()), apply=True, create_teacher_accounts=True, commit=False)
    u = scratch.scalar(select(User).where(User.email == "g.hopper@import.example.edu"))
    assert (u.role, u.teacher_name, u.password_hash) == ("teacher", "Grace Hopper", None)


def test_the_api_checks_a_zip_and_only_admins_may(client, login):
    r = client.post("/api/admin/import/oneroster", files={"file": ("export.zip", zipped(export()), "application/zip")},
                    data={"apply": "false"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and not body["applied"] and body["created"]["students"] == 2
    assert client.post("/api/admin/import/oneroster", files={"file": ("x.zip", b"not a zip", "application/zip")}
                       ).status_code == 422
    assert login("counselor").post("/api/admin/import/oneroster",
                                   files={"file": ("export.zip", zipped(export()), "application/zip")}).status_code == 403


def test_ungraded_courses_do_not_move_a_students_indices(db):
    """The catalog marks P.E. ungraded; its scores stay on its class page but out of the indices."""
    sigs = build_signals(db)
    pe = [c for s in sigs.values() for c in s.courses if c.course_code == "PE-160"]
    assert pe and not any(c.graded for c in pe)
    assert not any(r.label.endswith("PE-160") for s in sigs.values() for r in s.reasons)
    assert not any(rec.course_code == "PE-160" and rec.kind != "enrichment"
                   for s in sigs.values() for rec in s.recommendations)
