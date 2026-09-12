"""Study plans for one student in one class, drafted by an agent and adopted by a person.

A support plan routes a child to a person ("tutoring"). A study plan is what that
tutoring, or the student on their own, actually does week to week: which strand,
which assignments to redo or hand in, for how long, and how anyone will know it
worked.

Three pieces live here so the agent, the approval step and the student record agree:

* **The class-work reading.** Every past-due assignment the student has in the
  class, with the score or "missing", rolled up by strand and by kind of work and
  set against the class average. Deterministic findings name what exactly is
  wrong: a strand that is weak for this student but not the class, tests well
  below practice work, work not handed in, a strand that is sliding.
* **Checks on a drafted plan.** Every percentage must be in the reading, every
  strand one the class teaches, every catch-up assignment one that is really
  missing, and every finding must be addressed by some session.
* **Progress.** An adopted plan keeps the reading from its first day, so the
  record shows the baseline next to today.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics import build_signals
from .config import get_settings
from .models import Assessment, Course, Enrollment, Score, Student, StudyPlan

settings = get_settings()

REVIEW_AFTER_DAYS = 21
STRAND_GAP_POINTS = 8.0      # this far under the class average, a strand is the student's own gap
TEST_GAP_POINTS = 10.0       # tests and quizzes this far under practice work
STRAND_SLIDE_POINTS = 10.0   # latest piece in a strand this far under the earlier ones
PERCENT_TOLERANCE = 1.0
ASSESSED = {"test", "quiz"}
PRACTICE = {"homework", "lab", "project"}


@dataclass
class AssignmentRow:
    id: int
    title: str
    kind: str
    strand: str
    due_on: str
    pct: float | None          # None = not handed in
    class_pct: float | None    # class average on this piece, of work handed in
    late: bool


@dataclass
class StrandRow:
    strand: str
    pct: float                 # missing counts as zero, as in the gradebook
    handed_in_pct: float | None  # mean of the pieces actually handed in
    class_pct: float | None
    graded: int
    missing: int
    first_pct: float | None    # mean of the earlier pieces handed in
    last_pct: float | None     # the latest piece handed in


@dataclass
class KindRow:
    kind: str
    pct: float | None          # of work handed in
    handed_in: int
    due: int


@dataclass
class Finding:
    code: str  # strand-gap | strand-missing | class-gap | tests-below-practice | missing-work | sliding | declining
    text: str
    strand: str | None = None


@dataclass
class ClassWork:
    sid: str
    name: str
    course_code: str
    course_title: str
    teacher: str
    pct: float
    class_pct: float | None
    trend: float
    struggle: int
    assignments: list[AssignmentRow] = field(default_factory=list)
    strands: list[StrandRow] = field(default_factory=list)
    kinds: list[KindRow] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def missing(self) -> list[AssignmentRow]:
        return [a for a in self.assignments if a.pct is None]

    @property
    def needs_plan(self) -> bool:
        return self.pct < settings.support_threshold or bool(self.findings)

    def as_dict(self) -> dict:
        return asdict(self)


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 1) if xs else None


def class_work(db: Session, sid: str, code: str, sigs=None) -> ClassWork | None:
    """None when the student is not enrolled in the class or nothing is graded yet."""
    st = db.scalar(select(Student).where(Student.sid == sid))
    course = db.scalar(select(Course).where(Course.code == code))
    if st is None or course is None:
        return None
    sigs = sigs if sigs is not None else build_signals(db)
    sig = sigs.get(sid)
    cs = next((c for c in sig.courses if c.course_code == code), None) if sig else None
    if cs is None:
        return None

    items = db.scalars(select(Assessment).where(Assessment.course_id == course.id,
                                                Assessment.due_on <= settings.today)
                       .order_by(Assessment.due_on, Assessment.id)).all()
    enrolled = set(db.scalars(select(Enrollment.student_id).where(
        Enrollment.course_id == course.id, Enrollment.status == "enrolled")).all())
    scores = db.scalars(select(Score).where(Score.assessment_id.in_([a.id for a in items]))).all() if items else []
    mine = {s.assessment_id: s for s in scores if s.student_id == st.id}
    class_by_item: dict[int, list[float]] = defaultdict(list)
    by_id = {a.id: a for a in items}
    for s in scores:
        a = by_id.get(s.assessment_id)
        if a and s.student_id in enrolled and s.points is not None and a.max_points:
            class_by_item[a.id].append(100.0 * s.points / a.max_points)

    rows: list[AssignmentRow] = []
    for a in items:
        sc = mine.get(a.id)
        pct = round(100.0 * sc.points / a.max_points, 1) if sc and sc.points is not None and a.max_points else None
        rows.append(AssignmentRow(id=a.id, title=a.title, kind=a.kind, strand=a.skill,
                                  due_on=a.due_on.isoformat(), pct=pct,
                                  class_pct=_mean(class_by_item.get(a.id, [])), late=bool(sc and sc.late)))

    # Strand readings: the student's weighted strand mastery comes from the signal
    # engine, so the record, the list and the plan never disagree on a number.
    class_strand = _class_strand_means(sigs, code)
    strands: list[StrandRow] = []
    for sk in cs.skills:
        done = [r.pct for r in rows if r.strand == sk.skill and r.pct is not None]
        strands.append(StrandRow(strand=sk.skill, pct=sk.pct, handed_in_pct=_mean(done),
                                 class_pct=class_strand.get(sk.skill),
                                 graded=sk.graded, missing=sk.missing,
                                 first_pct=_mean(done[:-1]) if len(done) >= 2 else None,
                                 last_pct=done[-1] if len(done) >= 2 else None))
    strands.sort(key=lambda s: s.pct)

    kinds: list[KindRow] = []
    for kind in sorted({r.kind for r in rows}):
        of_kind = [r for r in rows if r.kind == kind]
        done = [r.pct for r in of_kind if r.pct is not None]
        kinds.append(KindRow(kind=kind, pct=_mean(done), handed_in=len(done), due=len(of_kind)))

    cw = ClassWork(sid=sid, name=st.name, course_code=code, course_title=course.title, teacher=course.teacher,
                   pct=cs.pct, class_pct=_mean([c.pct for s in sigs.values() for c in s.courses
                                                if c.course_code == code]),
                   trend=cs.delta, struggle=cs.struggle_index, assignments=rows, strands=strands, kinds=kinds)
    cw.findings = _findings(cw)
    return cw


def _class_strand_means(sigs, code: str) -> dict[str, float]:
    by: dict[str, list[float]] = defaultdict(list)
    for s in sigs.values():
        for c in s.courses:
            if c.course_code == code:
                for sk in c.skills:
                    by[sk.skill].append(sk.pct)
    return {k: round(statistics.fmean(v), 1) for k, v in by.items()}


def _findings(cw: ClassWork) -> list[Finding]:
    line = settings.support_threshold
    out: list[Finding] = []
    for s in cw.strands:
        if s.pct >= line:
            continue
        if s.missing and s.handed_in_pct is not None and s.handed_in_pct >= line:
            # Low only because pieces are missing: the fix is handing them in, not reteaching.
            out.append(Finding("strand-missing", f"{s.strand}: {s.pct:.0f}% in the gradebook but "
                                                 f"{s.handed_in_pct:.0f}% on the work handed in, so the gap is "
                                                 f"{s.missing} missing piece(s), not understanding", s.strand))
        elif s.class_pct is not None and s.class_pct < line:
            # The whole class is weak here: a study plan helps, but the teaching is the cause.
            out.append(Finding("class-gap", f"{s.strand}: {s.pct:.0f}%, and the class averages "
                                            f"{s.class_pct:.0f}% too, so the whole class finds it hard", s.strand))
        elif s.class_pct is None or s.class_pct - s.pct >= STRAND_GAP_POINTS:
            out.append(Finding("strand-gap", f"{s.strand}: {s.pct:.0f}% against a class average of "
                                             f"{s.class_pct:.0f}%" if s.class_pct is not None
                               else f"{s.strand}: {s.pct:.0f}%", s.strand))
    for s in cw.strands:
        if s.first_pct is not None and s.last_pct is not None and s.first_pct - s.last_pct >= STRAND_SLIDE_POINTS:
            out.append(Finding("sliding", f"{s.strand}: latest piece {s.last_pct:.0f}% after "
                                          f"{s.first_pct:.0f}% on earlier ones", s.strand))

    assessed = [r.pct for r in cw.assignments if r.kind in ASSESSED and r.pct is not None]
    practice = [r.pct for r in cw.assignments if r.kind in PRACTICE and r.pct is not None]
    if len(assessed) >= 2 and len(practice) >= 2:
        a, p = statistics.fmean(assessed), statistics.fmean(practice)
        if p - a >= TEST_GAP_POINTS:
            out.append(Finding("tests-below-practice",
                               f"Tests and quizzes average {a:.0f}% against {p:.0f}% on homework, labs and "
                               "projects: the work is understood but not holding up under test conditions"))

    if cw.missing:
        titles = "; ".join(f"{m.title} (due {m.due_on})" for m in cw.missing[:4])
        out.append(Finding("missing-work", f"{len(cw.missing)} of {len(cw.assignments)} assignments not "
                                           f"handed in: {titles}"))
    if cw.trend <= -8:
        out.append(Finding("declining", f"Recent work down {abs(cw.trend):.0f} points on the pieces before"))
    return out


def students_needing_plans(db: Session) -> list[ClassWork]:
    """Every (student, class) whose work calls for a study plan and has none, worst first."""
    sigs = build_signals(db)
    out = []
    for s in sigs.values():
        for c in s.courses:
            if c.pct >= settings.support_threshold and c.struggle_index < 35:
                continue
            if active_plan(db, s.sid, c.course_code):
                continue
            cw = class_work(db, s.sid, c.course_code, sigs)
            if cw and cw.needs_plan:
                out.append(cw)
    return sorted(out, key=lambda w: (w.pct, -w.struggle))


# ---- checking a draft ---------------------------------------------------------
def _figures(cw: ClassWork) -> list[float]:
    out = [settings.support_threshold, settings.concern_floor, cw.pct]
    out += [v for v in (cw.class_pct,) if v is not None]
    for s in cw.strands:
        out += [v for v in (s.pct, s.handed_in_pct, s.class_pct, s.first_pct, s.last_pct) if v is not None]
    for k in cw.kinds:
        if k.pct is not None:
            out.append(k.pct)
    for a in cw.assignments:
        out += [v for v in (a.pct, a.class_pct) if v is not None]
    assessed = [r.pct for r in cw.assignments if r.kind in ASSESSED and r.pct is not None]
    practice = [r.pct for r in cw.assignments if r.kind in PRACTICE and r.pct is not None]
    out += [statistics.fmean(x) for x in (assessed, practice) if x]
    return out


PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")
TARGET_WORDS = re.compile(r"\b(to|above|over|at least|reach|target|by|least|from)\s*$")


def uncited_percentages(text: str, cw: ClassWork) -> list[str]:
    """Percentages that match no figure in the reading. A target ("to 75%") may be new."""
    figures = _figures(cw)
    bad = []
    for m in PERCENT.finditer(text):
        if TARGET_WORDS.search(text[max(0, m.start() - 12):m.start()].lower()):
            continue
        if not any(abs(float(m.group(1)) - f) <= PERCENT_TOLERANCE for f in figures):
            bad.append(m.group(0))
    return bad


COUNT = re.compile(r"(\d+)\s+(?:out\s+)?of\s+(?:the\s+|their\s+|his\s+|her\s+)?(\d+)")


def miscounted(text: str, cw: ClassWork) -> list[str]:
    """"N of M" claims that match no count for the thing they are about.

    Learned from the class plans agent on the same model: it cites real numbers
    but borrows a count from the wrong measure. So a count is checked against the
    strand or kind of work named in its own sentence, and otherwise against the
    class as a whole.
    """
    total, missing = len(cw.assignments), len(cw.missing)
    overall = {(missing, total), (total - missing, total)}
    strand_pairs = {st.strand.lower(): {(st.missing, st.graded), (st.graded - st.missing, st.graded)}
                    for st in cw.strands}
    kind_pairs = {k.kind: {(k.handed_in, k.due), (k.due - k.handed_in, k.due)} for k in cw.kinds}
    bad = []
    for m in COUNT.finditer(text):
        pair = (int(m.group(1)), int(m.group(2)))
        sentence = (re.split(r"[.;!?]\s", text[:m.start()])[-1] + " " + re.split(r"[.;!?]\s", text[m.end():])[0]).lower()
        named = [v for k, v in strand_pairs.items() if k in sentence]
        named += [v for k, v in kind_pairs.items() if re.search(rf"\b{k}(?:s|zes|work)?\b", sentence)]
        expected = set().union(*named) if named else overall
        if pair not in expected:
            bad.append(m.group(0))
    return bad


DURATION = re.compile(r"\d+\s*(?:-\s*\d+\s*)?(?:min|minute|hour|hr)", re.IGNORECASE)
TEST_WORDS = re.compile(r"\b(test|quiz|timed|exam|practice paper|retake)", re.IGNORECASE)
SUBMISSION_WORDS = re.compile(r"hand(?:ed|ing)?[ -]in|turn(?:ed|ing)?[ -]in|missing|submi|catch[ -]?up|"
                              r"overdue|complete the", re.IGNORECASE)


def problems_with(cw: ClassWork, *, focus_strands: list[str], sessions: list[str],
                  catch_up: list[int], goal: str, diagnosis: str) -> list[str]:
    """Everything wrong with a draft, as sentences a small model can act on. Empty means it passes."""
    by_lower = {s.strand.lower(): s.strand for s in cw.strands}
    wrong = [f for f in focus_strands if f.strip().lower() not in by_lower]
    if wrong:
        return [f"{cw.course_code} does not assess: {', '.join(wrong)}. "
                f"This student's strands are: {', '.join(s.strand for s in cw.strands)}."]
    if not 1 <= len(focus_strands) <= 3:
        return ["focus_strands must name one to three strands from get_student_class_work."]
    if not 3 <= len(sessions) <= 8:
        return ["sessions must list three to eight separate study sessions."]

    out: list[str] = []
    vague = [s for s in sessions if len(s) < 30 or not DURATION.search(s)]
    if vague:
        out.append("Each session must say when, what exactly the student does, and for how long "
                   f"(e.g. '20 min'). Too vague: {vague[0]!r}.")
    if len({s.lower() for s in sessions}) < len(sessions):
        out.append("Two sessions are the same. Give distinct sessions.")
    text = " ".join(sessions).lower()
    unstudied = [by_lower[f.strip().lower()] for f in focus_strands if f.strip().lower() not in text]
    if unstudied:
        out.append(f"No session works on {unstudied[0]}, which is a focus strand. Name it in a session.")

    missing_ids = {a.id for a in cw.missing}
    bogus = [i for i in catch_up if i not in missing_ids]
    if bogus:
        real = "; ".join(f"{a.id} = {a.title}" for a in cw.missing[:6]) or "none"
        out.append(f"Assignment ids {bogus} are not missing for this student. Missing ones: {real}.")
    codes = {f.code for f in cw.findings}
    if "missing-work" in codes and not catch_up:
        real = "; ".join(f"{a.id} = {a.title}" for a in cw.missing[:6])
        out.append(f"This student has work not handed in. Put the ids to catch up in catch_up_assignments: {real}.")
    if "missing-work" in codes and not SUBMISSION_WORDS.search(text):
        out.append("Add a session for handing in the missing work.")
    if "tests-below-practice" in codes and not TEST_WORDS.search(text):
        out.append("Tests score well below practice work, and no session practises under test conditions. "
                   "Add a timed practice quiz or test session.")
    if not re.search(r"\d", goal):
        out.append("The goal must be measurable: name a number to reach, e.g. 'word problems to 72%'.")
    wrong_counts = miscounted(" ".join([diagnosis, *sessions]), cw)
    if wrong_counts:
        out.append(f"These counts do not match the student's work: {', '.join(wrong_counts)}. They have "
                   f"{len(cw.missing)} of {len(cw.assignments)} assignments missing overall; each strand and "
                   "kind of work has its own count in get_student_class_work. Use the one for what you name.")
    invented = uncited_percentages(" ".join([diagnosis, *sessions]), cw)
    if invented:
        out.append(f"These figures are not in the student's class data: {', '.join(invented)}. "
                   "Cite only numbers returned by get_student_class_work.")
    return out


def canonical_strands(named: list[str], cw: ClassWork) -> list[str]:
    by_lower = {s.strand.lower(): s.strand for s in cw.strands}
    return [by_lower[n.strip().lower()] for n in named if n.strip().lower() in by_lower]


# ---- adopting, and progress ---------------------------------------------------
def active_plan(db: Session, sid: str, code: str) -> StudyPlan | None:
    return db.scalar(select(StudyPlan).where(StudyPlan.student_sid == sid, StudyPlan.course_code == code,
                                             StudyPlan.status == "active"))


def adopt(db: Session, *, student_sid: str, course_code: str, title: str, diagnosis: str,
          focus_strands: list[str], sessions: list[str], catch_up_assignments: list[int], goal: str,
          run_id: int | None = None, proposal_id: int | None = None) -> StudyPlan:
    cw = class_work(db, student_sid, course_code)
    if cw is None:
        raise ValueError(f"{student_sid} is no longer taking {course_code}.")
    if active_plan(db, student_sid, course_code):
        raise ValueError(f"{cw.name} already has an active study plan for {course_code}.")
    unknown = [f for f in focus_strands if f.strip().lower() not in {s.strand.lower() for s in cw.strands}]
    if unknown:
        raise ValueError(f"{course_code} no longer assesses: {', '.join(unknown)}.")
    plan = StudyPlan(student_sid=student_sid, course_code=course_code, title=title, diagnosis=diagnosis,
                     focus_strands=canonical_strands(focus_strands, cw), sessions=list(sessions),
                     catch_up=[{"id": a.id, "title": a.title, "due_on": a.due_on}
                               for a in cw.missing if a.id in set(catch_up_assignments)],
                     goal=goal, owner=cw.teacher, status="active", baseline=cw.as_dict(),
                     opened_on=settings.today, review_on=settings.today + timedelta(days=REVIEW_AFTER_DAYS),
                     run_id=run_id, proposal_id=proposal_id)
    db.add(plan)
    db.flush()
    return plan


def progress(plan: StudyPlan, now: ClassWork | None) -> list[dict]:
    base = plan.baseline or {}
    rows = [("Class grade", base.get("pct"), now.pct if now else None)]
    base_strands = {s["strand"]: s["pct"] for s in base.get("strands", [])}
    now_strands = {s.strand: s.pct for s in now.strands} if now else {}
    rows += [(s, base_strands.get(s), now_strands.get(s)) for s in plan.focus_strands or []]
    out = [{"measure": m, "baseline": b, "now": n, "unit": "%",
            "change": round(n - b, 1) if b is not None and n is not None else None} for m, b, n in rows]
    base_missing = sum(1 for a in base.get("assignments", []) if a.get("pct") is None)
    now_missing = len(now.missing) if now else None
    out.append({"measure": "Assignments missing", "baseline": base_missing, "now": now_missing, "unit": "",
                "change": now_missing - base_missing if now_missing is not None else None})
    return out
