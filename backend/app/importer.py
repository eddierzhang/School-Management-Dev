"""Importing the school's records from its student information system.

The format is OneRoster 1.1 CSV, which PowerSchool, Infinite Campus, Aeries,
Skyward, Clever and most others export: a folder or zip of CSV files.

    users.csv            required  students, teachers and guardians
    classes.csv          required  sections, with classCode, periods and location
    enrollments.csv      required  who is in which class, as student or teacher
    courses.csv          optional  course titles and subjects
    academicSessions.csv optional  term names
    categories.csv       optional  kinds of work (homework, quiz, test, …)
    lineItems.csv        optional  assessments
    results.csv          optional  scores, including "not submitted" and "exempt"
    attendance.csv       optional  not part of OneRoster: userSourcedId,date,status

OneRoster has no skill tag on an assessment, and strand analysis needs one. Add a
`skill` (or `metadata.skill`) column to lineItems.csv; without it, pieces are
grouped under "general" and the import warns.

**Nothing is written until everything checks out.** Every file is read and every
reference resolved first; any error refuses the whole import. The import then
runs inside one transaction. A dry run (the default) performs it, reports exactly
what it would create, update and drop, runs the timetable checks on the result,
and rolls back.

**It is a full snapshot of the classes it contains.** For every class in the file,
a student enrolled here but absent from enrollments.csv is marked dropped, never
deleted. Students and classes missing from the file are left alone, as are plans,
documents and everything else people did in the app.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Assessment, AttendanceDay, Course, Enrollment, Score, Student, User

settings = get_settings()

REQUIRED = {
    "users.csv": {"sourcedId", "role", "givenName", "familyName"},
    "classes.csv": {"sourcedId", "title"},
    "enrollments.csv": {"classSourcedId", "userSourcedId", "role"},
}
OPTIONAL = {
    "courses.csv": {"sourcedId", "title"},
    "academicSessions.csv": {"sourcedId", "title"},
    "categories.csv": {"sourcedId", "title"},
    "lineItems.csv": {"sourcedId", "title", "classSourcedId", "dueDate"},
    "results.csv": {"lineItemSourcedId", "studentSourcedId", "scoreStatus"},
    "attendance.csv": {"userSourcedId", "date", "status"},
}
MAX_ZIP_BYTES = 200 * 1024 * 1024        # uncompressed, across every member
GUARDIAN_ROLES = {"parent", "guardian", "relative"}
ATTENDANCE_STATUSES = {"present", "absent", "tardy", "excused"}
KIND_WORDS = [("test", "test"), ("exam", "test"), ("quiz", "quiz"), ("lab", "lab"), ("project", "project"),
              ("homework", "homework"), ("classwork", "homework"), ("assignment", "homework")]


class ImportFileError(ValueError):
    """The upload itself cannot be read."""


@dataclass
class Issue:
    file: str
    line: int | None
    message: str


@dataclass
class ImportReport:
    applied: bool = False
    rows: dict[str, int] = field(default_factory=dict)
    created: Counter = field(default_factory=Counter)
    updated: Counter = field(default_factory=Counter)
    dropped_enrollments: int = 0
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    def error(self, file: str, line: int | None, message: str) -> None:
        if len(self.errors) < 500:
            self.errors.append(Issue(file, line, message))

    def warn(self, file: str, line: int | None, message: str) -> None:
        if len(self.warnings) < 200:
            self.warnings.append(Issue(file, line, message))

    def as_dict(self) -> dict:
        out = asdict(self)
        out["created"], out["updated"] = dict(self.created), dict(self.updated)
        out["ok"] = not self.errors
        return out


# ---- reading ----------------------------------------------------------------------
Rows = list[tuple[int, dict[str, str]]]         # (line number, row)


def read_directory(path: Path) -> dict[str, Rows]:
    return {name: _parse(name, (path / name).read_bytes())
            for name in {**REQUIRED, **OPTIONAL} if (path / name).exists()}


def read_zip(data: bytes) -> dict[str, Rows]:
    """The CSVs from a zip, at its root or inside one folder. Anything else is ignored."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ImportFileError("That is not a zip file.") from e
    wanted = {n.lower(): n for n in {**REQUIRED, **OPTIONAL}}
    members = {}
    for info in zf.infolist():
        base = info.filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if info.is_dir() or base not in wanted or info.filename.count("/") > 1:
            continue
        members[wanted[base]] = info
    if sum(i.file_size for i in members.values()) > MAX_ZIP_BYTES:
        raise ImportFileError("The CSVs in that zip are over 200 MB uncompressed. Import one school at a time.")
    return {name: _parse(name, zf.read(info)) for name, info in members.items()}


def _parse(name: str, raw: bytes) -> Rows:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    return [(i + 2, {k: (v or "").strip() for k, v in row.items() if k}) for i, row in enumerate(reader)]


# ---- helpers ----------------------------------------------------------------------
def _split(value: str) -> list[str]:
    return [v.strip() for v in re.split(r"[;,]", value or "") if v.strip()]


def _grade(value: str) -> int | None:
    first = (_split(value) or [""])[0].upper()
    if first in ("KG", "K"):
        return 0
    return int(first) if first.lstrip("-").isdigit() else None


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _kind(category_title: str, title: str) -> str:
    """The piece's own title wins ("Proofs quiz" filed under Tests is a quiz), then its category."""
    for text in (title.lower(), category_title.lower()):
        found = next((k for word, k in KIND_WORDS if word in text), None)
        if found:
            return found
    return "homework"


def _active(row: dict) -> bool:
    return row.get("status", "active").lower() != "tobedeleted"


# ---- the import -------------------------------------------------------------------
def run_import(db: Session, files: dict[str, Rows], *, apply: bool = False,
               create_teacher_accounts: bool = False, commit: bool = True) -> ImportReport:
    r = ImportReport(rows={name: len(rows) for name, rows in files.items()})
    plan = _validate(files, r)
    if r.errors:
        return r
    _apply(db, plan, r, create_teacher_accounts)
    db.flush()
    _check_result(db, plan, r)
    if apply and not r.errors and commit:
        db.commit()
        r.applied = True
    elif apply and not r.errors:
        r.applied = True          # the caller owns the transaction
    else:
        db.rollback()
    return r


@dataclass
class _Plan:
    students: dict[str, dict] = field(default_factory=dict)     # user sourcedId -> fields
    teachers: dict[str, dict] = field(default_factory=dict)
    classes: dict[str, dict] = field(default_factory=dict)      # class sourcedId -> fields
    enrollments: set[tuple[str, str]] = field(default_factory=set)   # (student sourcedId, class sourcedId)
    line_items: dict[str, dict] = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)
    attendance: list[dict] = field(default_factory=list)


def _validate(files: dict[str, Rows], r: ImportReport) -> _Plan:
    p = _Plan()
    for name in REQUIRED:
        if name not in files:
            r.error(name, None, f"{name} is required and was not found.")
    for name, cols in {**REQUIRED, **OPTIONAL}.items():
        rows = files.get(name)
        if rows:
            missing = cols - set(rows[0][1])
            if missing:
                r.error(name, 1, f"Missing column(s): {', '.join(sorted(missing))}.")
    if r.errors:
        return p

    # users
    users: dict[str, dict] = {}
    seen_sids: dict[str, int] = {}
    for line, row in files["users.csv"]:
        sid_ = row["sourcedId"]
        if not sid_:
            r.error("users.csv", line, "A user has no sourcedId.")
            continue
        if sid_ in users:
            r.error("users.csv", line, f"sourcedId {sid_} appears twice.")
            continue
        users[sid_] = row | {"_line": line}
        if not _active(row):
            continue
        role = row["role"].lower()
        name = " ".join(x for x in (row["givenName"], row["familyName"]) if x).strip()
        if role == "student":
            sid = row.get("identifier") or row.get("username") or sid_
            grade = _grade(row.get("grades", ""))
            if len(sid) > 16:
                r.error("users.csv", line, f"Student ID {sid!r} is longer than 16 characters.")
            if grade is None:
                r.error("users.csv", line, f"Student {sid} has no readable grade ({row.get('grades')!r}).")
            if sid in seen_sids:
                r.error("users.csv", line, f"Student ID {sid} is used by two students (also line {seen_sids[sid]}).")
            seen_sids[sid] = line
            p.students[sid_] = {"sid": sid, "name": name or sid, "grade": grade if grade is not None else 0,
                                "homeroom": row.get("metadata.homeroom", "") or row.get("homeroom", ""),
                                "agents": _split(row.get("agentSourcedIds", "")), "line": line}
        elif role in ("teacher", "aide"):
            p.teachers[sid_] = {"name": name or row.get("username") or sid_, "email": row.get("email", "").lower()}
    for s in p.students.values():
        guardian = next((users[a] for a in s.pop("agents") if a in users
                         and users[a]["role"].lower() in GUARDIAN_ROLES), None)
        s["guardian_name"] = " ".join(x for x in (guardian["givenName"], guardian["familyName"]) if x) if guardian else None
        s["guardian_email"] = guardian.get("email") or None if guardian else None

    # courses, terms, classes
    courses = {row["sourcedId"]: row for _, row in files.get("courses.csv", [])}
    terms = {row["sourcedId"]: row["title"] for _, row in files.get("academicSessions.csv", [])}
    codes: dict[str, int] = {}
    for line, row in files["classes.csv"]:
        if not _active(row):
            continue
        course = courses.get(row.get("courseSourcedId", ""), {})
        code = (row.get("classCode") or row["sourcedId"]).strip().upper()
        if len(code) > 16:
            r.error("classes.csv", line, f"Class code {code!r} is longer than 16 characters.")
        if code in codes:
            r.error("classes.csv", line, f"Class code {code} is used by two classes (also line {codes[code]}).")
        codes[code] = line
        period = next((int(x) for x in _split(row.get("periods", "")) if x.isdigit()), 0)
        term = next((terms[t] for t in _split(row.get("termSourcedIds", "")) if t in terms), None)
        p.classes[row["sourcedId"]] = {
            "code": code, "title": (course.get("title") or row["title"])[:120],
            "dept": (_split(row.get("subjects", "")) or _split(course.get("subjects", "")) or ["General"])[0][:60],
            "period": period, "room": (row.get("location") or "TBD")[:32], "term": term or settings.term,
            "teachers": [], "line": line}

    # enrollments
    for line, row in files["enrollments.csv"]:
        if not _active(row):
            continue
        cls, user, role = row["classSourcedId"], row["userSourcedId"], row["role"].lower()
        if cls not in p.classes:
            r.error("enrollments.csv", line, f"Class {cls} is not in classes.csv.")
            continue
        if role == "student":
            if user not in p.students:
                r.error("enrollments.csv", line, f"Student {user} is not an active student in users.csv.")
                continue
            p.enrollments.add((user, cls))
        elif role in ("teacher", "aide"):
            if user not in p.teachers:
                r.error("enrollments.csv", line, f"Teacher {user} is not in users.csv.")
                continue
            primary = row.get("primary", "").lower() == "true"
            p.classes[cls]["teachers"].insert(0 if primary else len(p.classes[cls]["teachers"]), p.teachers[user]["name"])
    for cls in p.classes.values():
        if not cls["teachers"]:
            r.warn("classes.csv", cls["line"], f"{cls['code']} has no teacher enrollment; it is listed as taught by TBD.")

    # assessments and scores
    categories = {row["sourcedId"]: row["title"] for _, row in files.get("categories.csv", [])}
    untagged = 0
    for line, row in files.get("lineItems.csv", []):
        if not _active(row):
            continue
        if row["classSourcedId"] not in p.classes:
            r.error("lineItems.csv", line, f"Class {row['classSourcedId']} is not in classes.csv.")
            continue
        due = _date(row["dueDate"])
        assigned = _date(row.get("assignDate", "")) or due
        if due is None:
            r.error("lineItems.csv", line, f"dueDate {row['dueDate']!r} is not a date.")
            continue
        try:
            max_points = float(row.get("resultValueMax") or 100)
        except ValueError:
            r.error("lineItems.csv", line, f"resultValueMax {row.get('resultValueMax')!r} is not a number.")
            continue
        if max_points <= 0:
            r.error("lineItems.csv", line, "resultValueMax must be above zero.")
            continue
        skill = (row.get("skill") or row.get("metadata.skill") or "").strip()
        untagged += not skill
        p.line_items[row["sourcedId"]] = {
            "class": row["classSourcedId"], "title": row["title"][:160], "skill": (skill or "general")[:80],
            "kind": _kind(categories.get(row.get("categorySourcedId", ""), ""), row["title"]),
            "max_points": max_points, "due_on": due, "assigned_on": assigned}
    if untagged:
        r.warn("lineItems.csv", None, f"{untagged} assessment(s) have no skill column, so strand analysis groups them "
                                      "under 'general'. Add a skill column to see what students struggle on.")

    for line, row in files.get("results.csv", []):
        if not _active(row):
            continue
        item, student = p.line_items.get(row["lineItemSourcedId"]), row["studentSourcedId"]
        if item is None:
            r.error("results.csv", line, f"Line item {row['lineItemSourcedId']} is not in lineItems.csv.")
            continue
        if student not in p.students:
            r.error("results.csv", line, f"Student {student} is not an active student in users.csv.")
            continue
        status = row["scoreStatus"].lower()
        exempt, points = status == "exempt", None
        if not exempt and status != "not submitted":
            try:
                points = float(row.get("score", ""))
            except ValueError:
                r.error("results.csv", line, f"score {row.get('score')!r} is not a number (status {status!r}).")
                continue
            if not 0 <= points <= item["max_points"]:
                r.error("results.csv", line, f"score {points:g} is outside 0–{item['max_points']:g}.")
                continue
        late = row.get("late", "").lower() in ("true", "1", "yes") or "late" in status
        p.results.append({"item": row["lineItemSourcedId"], "student": student, "points": points,
                          "exempt": exempt, "late": late, "recorded_on": _date(row.get("scoreDate", ""))})

    for line, row in files.get("attendance.csv", []):
        student, day, status = row["userSourcedId"], _date(row["date"]), row["status"].lower()
        if student not in p.students:
            r.error("attendance.csv", line, f"Student {student} is not an active student in users.csv.")
        elif day is None:
            r.error("attendance.csv", line, f"date {row['date']!r} is not a date.")
        elif status not in ATTENDANCE_STATUSES:
            r.error("attendance.csv", line, f"status must be one of {', '.join(sorted(ATTENDANCE_STATUSES))}.")
        else:
            p.attendance.append({"student": student, "day": day, "status": status})
    return p


def _apply(db: Session, p: _Plan, r: ImportReport, create_teacher_accounts: bool) -> None:
    # students
    existing = {s.sid: s for s in db.scalars(select(Student).where(
        Student.sid.in_([s["sid"] for s in p.students.values()]))).all()}
    by_source: dict[str, Student] = {}
    for src, s in p.students.items():
        st = existing.get(s["sid"])
        fields = {k: s[k] for k in ("name", "grade", "guardian_name", "guardian_email")}
        if s["homeroom"]:
            fields["homeroom"] = s["homeroom"]
        if st is None:
            st = Student(sid=s["sid"], homeroom=s["homeroom"] or "", **fields)
            db.add(st)
            r.created["students"] += 1
        elif any(getattr(st, k) != v for k, v in fields.items()):
            for k, v in fields.items():
                setattr(st, k, v)
            r.updated["students"] += 1
        by_source[src] = st

    # classes
    enrolled_count = Counter(cls for _, cls in p.enrollments)
    have = {c.code: c for c in db.scalars(select(Course).where(
        Course.code.in_([c["code"] for c in p.classes.values()]))).all()}
    classes: dict[str, Course] = {}
    for src, c in p.classes.items():
        course = have.get(c["code"])
        teacher = (c["teachers"] or ["TBD"])[0][:120]
        fields = {"title": c["title"], "dept": c["dept"], "teacher": teacher, "period": c["period"],
                  "room": c["room"], "term": c["term"]}
        if course is None:
            course = Course(code=c["code"], capacity=max(24, enrolled_count[src]), signups=[], **fields)
            db.add(course)
            r.created["classes"] += 1
        else:
            if any(getattr(course, k) != v for k, v in fields.items()):
                r.updated["classes"] += 1
            for k, v in fields.items():
                setattr(course, k, v)
            course.capacity = max(course.capacity, enrolled_count[src])
        classes[src] = course
    db.flush()

    # enrollments: the file is the whole roster of each class in it
    wanted = {(by_source[s].id, classes[c].id) for s, c in p.enrollments}
    current = {(e.student_id, e.course_id): e for e in db.scalars(select(Enrollment).where(
        Enrollment.course_id.in_([c.id for c in classes.values()]))).all()}
    for key in wanted:
        e = current.get(key)
        if e is None:
            db.add(Enrollment(student_id=key[0], course_id=key[1], status="enrolled"))
            r.created["enrollments"] += 1
        elif e.status != "enrolled":
            e.status = "enrolled"
            r.updated["enrollments"] += 1
    for key, e in current.items():
        if key not in wanted and e.status in ("enrolled", "waitlist"):
            e.status = "dropped"
            r.dropped_enrollments += 1

    # assessments
    known = {a.source_id: a for a in db.scalars(select(Assessment).where(
        Assessment.source_id.in_(list(p.line_items)))).all()} if p.line_items else {}
    items: dict[str, Assessment] = {}
    for src, li in p.line_items.items():
        a = known.get(src)
        fields = {"course_id": classes[li["class"]].id, "title": li["title"], "kind": li["kind"], "skill": li["skill"],
                  "max_points": li["max_points"], "due_on": li["due_on"], "assigned_on": li["assigned_on"]}
        if a is None:
            a = Assessment(source_id=src, weight=1.0, **fields)
            db.add(a)
            r.created["assessments"] += 1
        else:
            if any(getattr(a, k) != v for k, v in fields.items()):
                r.updated["assessments"] += 1
            for k, v in fields.items():
                setattr(a, k, v)
        items[src] = a
    db.flush()

    # scores
    if p.results:
        scores = {(s.assessment_id, s.student_id): s for s in db.scalars(select(Score).where(
            Score.assessment_id.in_([a.id for a in items.values()]))).all()}
        for res in p.results:
            a, st = items[res["item"]], by_source[res["student"]]
            sc = scores.get((a.id, st.id))
            fields = {"points": res["points"], "exempt": res["exempt"], "late": res["late"],
                      "recorded_on": res["recorded_on"] or settings.today}
            if sc is None:
                sc = Score(assessment_id=a.id, student_id=st.id, **fields)
                db.add(sc)
                scores[(a.id, st.id)] = sc
                r.created["scores"] += 1
            elif any(getattr(sc, k) != v for k, v in fields.items() if k != "recorded_on"):
                for k, v in fields.items():
                    setattr(sc, k, v)
                r.updated["scores"] += 1

    # attendance
    if p.attendance:
        ids = [by_source[x["student"]].id for x in p.attendance]
        days = [x["day"] for x in p.attendance]
        rows = {(a.student_id, a.day): a for a in db.scalars(select(AttendanceDay).where(
            AttendanceDay.student_id.in_(set(ids)), AttendanceDay.day >= min(days), AttendanceDay.day <= max(days))).all()}
        for x in p.attendance:
            key = (by_source[x["student"]].id, x["day"])
            row = rows.get(key)
            if row is None:
                rows[key] = AttendanceDay(student_id=key[0], day=key[1], status=x["status"])
                db.add(rows[key])
                r.created["attendance days"] += 1
            elif row.status != x["status"]:
                row.status = x["status"]
                r.updated["attendance days"] += 1

    # teacher accounts, for sign-in through the school's identity provider
    if create_teacher_accounts:
        taken = {e for (e,) in db.execute(select(func.lower(User.email))).all()}
        for t in p.teachers.values():
            if t["email"] and t["email"] not in taken:
                db.add(User(email=t["email"], name=t["name"][:120], role="teacher", teacher_name=t["name"][:120],
                            active=True, password_hash=None))
                taken.add(t["email"])
                r.created["teacher accounts"] += 1


def _check_result(db: Session, p: _Plan, r: ImportReport) -> None:
    """Run the timetable's own checks on the database as the import leaves it."""
    from .schedule import school_schedule

    s = school_schedule(db)
    imported = {c["code"] for c in p.classes.values()}
    for c in s.clashes:
        if imported & set(c.sections):
            r.warn("classes.csv", None, f"{c.kind.capitalize()} {c.who} is booked into {', '.join(c.sections)} "
                                        f"in period {c.period}.")
    students = {c.sid for c in s.student_clashes if imported & set(c.sections)}
    if students:
        r.warn("enrollments.csv", None, f"{len(students)} student(s) are enrolled in two classes in the same period "
                                        "(listed on the Schedule tab).")
    rostered = {s for s, _ in p.enrollments}
    empty = [st["sid"] for src, st in p.students.items() if src not in rostered]
    if empty:
        r.warn("enrollments.csv", None, f"{len(empty)} student(s) have no class enrollment: "
                                        f"{', '.join(empty[:5])}{'…' if len(empty) > 5 else ''}.")
    graded = {li["class"] for li in p.line_items.values()}
    ungraded = [c["code"] for src, c in p.classes.items() if src not in graded and p.line_items]
    if ungraded:
        r.warn("lineItems.csv", None, f"{len(ungraded)} class(es) have no assessments, so no grades: "
                                      f"{', '.join(ungraded[:5])}{'…' if len(ungraded) > 5 else ''}.")
    future = sum(1 for li in p.line_items.values() if li["due_on"] > settings.today)
    if future:
        r.warn("lineItems.csv", None, f"{future} assessment(s) are due after today and will not count until then.")
