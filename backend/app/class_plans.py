"""Improvement plans for a whole class, drafted by an agent and adopted by a person.

A support plan is for one child. A class plan is for the course itself: when a
strand sits below the line for half the room, or a third of the work never comes
in, tutoring children one at a time is the wrong tool, and the fix is to the
teaching.

Three pieces live here so the agent, the approval step and the class page agree:

* **The performance snapshot.** One deterministic reading of a class — averages,
  strands, work handed in, by kind of work, trend — and a status with named issues.
  The agent reads it; the page shows it; a plan stores it as its baseline.
* **Checks on a drafted plan.** A 4B model writes fluent, confident numbers that
  are not in the data. Every percentage a draft cites must match a figure in the
  snapshot, and every strand it names must be one the course actually teaches.
* **Progress.** A plan keeps the snapshot from the day it was adopted, so the
  class page can show the baseline next to today instead of asking anyone to
  remember what the numbers were.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics import StudentSignal, build_signals
from .config import get_settings
from .models import Assessment, ClassPlan, Course, Enrollment, Score

settings = get_settings()

# Below this share of past-due work handed in, submission is the class's problem.
COMPLETION_CONCERN = 0.85
# A strand is a cohort gap, not a few students, when this share is below the line.
COHORT_GAP_SHARE = 0.40
# Mean change in points, recent work against earlier work.
SLIDING = -5.0
REVIEW_AFTER_DAYS = 28
PERCENT_TOLERANCE = 1.0


@dataclass
class StrandReading:
    strand: str
    mean: float
    below_line: int
    cohort: int

    @property
    def share_below(self) -> float:
        return round(self.below_line / self.cohort, 3) if self.cohort else 0.0


@dataclass
class KindReading:
    kind: str
    mean: float | None        # of work handed in
    handed_in: float          # share of past-due pieces submitted


@dataclass
class ClassPerformance:
    code: str
    title: str
    dept: str
    teacher: str
    students: int
    mean: float | None
    median: float | None
    below_line: int
    completion: float | None
    trend: float | None
    improving: int
    declining: int
    needs_plan: int
    strands: list[StrandReading] = field(default_factory=list)
    kinds: list[KindReading] = field(default_factory=list)
    status: str = "no-data"   # needs-plan | watch | strong | no-data
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        for s, raw in zip(self.strands, d["strands"], strict=True):
            raw["share_below"] = s.share_below
        return d


def _kinds(db: Session, course: Course) -> list[KindReading]:
    enrolled = set(db.scalars(select(Enrollment.student_id).where(
        Enrollment.course_id == course.id, Enrollment.status == "enrolled")).all())
    if not enrolled:
        return []
    pcts: dict[str, list[float]] = defaultdict(list)
    due: dict[str, int] = defaultdict(int)
    handed: dict[str, int] = defaultdict(int)
    items = db.scalars(select(Assessment).where(Assessment.course_id == course.id,
                                                Assessment.due_on <= settings.today)).all()
    scores = {(s.assessment_id, s.student_id): s for s in db.scalars(
        select(Score).where(Score.assessment_id.in_([a.id for a in items]))).all()} if items else {}
    for a in items:
        for sid in enrolled:
            sc = scores.get((a.id, sid))
            if sc is not None and sc.exempt:
                continue
            due[a.kind] += 1
            if sc is not None and sc.points is not None and a.max_points:
                handed[a.kind] += 1
                pcts[a.kind].append(100.0 * sc.points / a.max_points)
    return sorted((KindReading(kind=k, mean=round(statistics.fmean(pcts[k]), 1) if pcts[k] else None,
                               handed_in=round(handed[k] / due[k], 3))
                   for k in due), key=lambda r: (r.mean if r.mean is not None else 999))


def _assess(p: ClassPerformance) -> None:
    line, floor = settings.support_threshold, settings.concern_floor
    issues: list[str] = []
    severe = False
    if p.mean is not None and p.mean < line:
        issues.append(f"Class average {p.mean:.0f}%, under the {line:.0f}% line")
        severe = True
    for s in p.strands:
        if s.mean < floor or s.share_below >= COHORT_GAP_SHARE:
            issues.append(f"{s.strand}: {s.mean:.0f}% average, {s.below_line} of {s.cohort} below the line")
            severe = severe or s.mean < floor or s.share_below >= 0.5
    if p.completion is not None and p.completion < COMPLETION_CONCERN:
        issues.append(f"{100 * (1 - p.completion):.0f}% of past-due work not handed in")
        severe = True
    if p.trend is not None and p.trend <= SLIDING:
        issues.append(f"Recent work down {abs(p.trend):.0f} points on average")
        severe = True
    weak_kind = next((k for k in p.kinds if k.mean is not None and k.mean < line), None)
    if weak_kind:
        issues.append(f"{weak_kind.kind.capitalize()} work averages {weak_kind.mean:.0f}%")

    if p.mean is None:
        p.status = "no-data"
    elif severe:
        p.status = "needs-plan"
    elif issues or p.mean < 80:
        p.status = "watch"
    else:
        p.status = "strong"
    p.issues = issues


def performance(db: Session, code: str, sigs: dict[str, StudentSignal] | None = None) -> ClassPerformance | None:
    course = db.scalar(select(Course).where(Course.code == code))
    if course is None:
        return None
    sigs = sigs if sigs is not None else build_signals(db)
    mine = [cs for s in sigs.values() for cs in s.courses if cs.course_code == code]
    pcts = [cs.pct for cs in mine]
    deltas = [cs.delta for cs in mine]
    graded = sum(cs.graded_items for cs in mine)
    missing = sum(cs.missing for cs in mine)

    by_strand: dict[str, list[float]] = defaultdict(list)
    for cs in mine:
        for sk in cs.skills:
            by_strand[sk.skill].append(sk.pct)
    strands = sorted((StrandReading(strand=k, mean=round(statistics.fmean(v), 1),
                                    below_line=sum(1 for x in v if x < settings.support_threshold),
                                    cohort=len(v)) for k, v in by_strand.items()),
                     key=lambda s: s.mean)

    p = ClassPerformance(
        code=course.code, title=course.title, dept=course.dept, teacher=course.teacher,
        students=len(mine),
        mean=round(statistics.fmean(pcts), 1) if pcts else None,
        median=round(statistics.median(pcts), 1) if pcts else None,
        below_line=sum(1 for x in pcts if x < settings.support_threshold),
        completion=round(1 - missing / graded, 3) if graded else None,
        trend=round(statistics.fmean(deltas), 1) if deltas else None,
        improving=sum(1 for d in deltas if d >= 3), declining=sum(1 for d in deltas if d <= -3),
        needs_plan=sum(1 for cs in mine if cs.struggle_index >= 55),
        strands=strands, kinds=_kinds(db, course),
    )
    _assess(p)
    return p


STATUS_ORDER = {"needs-plan": 0, "watch": 1, "strong": 2, "no-data": 3}


def all_performance(db: Session) -> list[ClassPerformance]:
    """Every class, the ones that most need a plan first."""
    sigs = build_signals(db)
    rows = [performance(db, c.code, sigs) for c in db.scalars(select(Course).order_by(Course.code)).all()]
    return sorted((r for r in rows if r), key=lambda r: (STATUS_ORDER[r.status], r.mean if r.mean is not None else 999))


# ---- checking a draft ---------------------------------------------------------
def _figures(p: ClassPerformance) -> list[float]:
    """Every percentage a plan could honestly cite about this class."""
    out = [settings.support_threshold, settings.concern_floor, 100 * COMPLETION_CONCERN]
    out += [v for v in (p.mean, p.median) if v is not None]
    if p.completion is not None:
        out += [100 * p.completion, 100 * (1 - p.completion)]
    if p.students:
        out.append(100 * p.below_line / p.students)
    for s in p.strands:
        out += [s.mean, 100 * s.share_below, 100 * (1 - s.share_below)]
    for k in p.kinds:
        out += [100 * k.handed_in, 100 * (1 - k.handed_in)] + ([k.mean] if k.mean is not None else [])
    return out


PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")


def uncited_percentages(text: str, p: ClassPerformance) -> list[str]:
    """Percentages in `text` that match no figure in the snapshot.

    Targets are exempt when phrased as one ("to 75%", "above 80%"): a goal is
    allowed to name a number the class has not reached yet.
    """
    figures = _figures(p)
    bad = []
    for m in PERCENT.finditer(text):
        before = text[max(0, m.start() - 12):m.start()].lower()
        if re.search(r"\b(to|above|over|at least|reach|target|by|least|from)\s*$", before):
            continue
        value = float(m.group(1))
        if not any(abs(value - f) <= PERCENT_TOLERANCE for f in figures):
            bad.append(m.group(0))
    return bad


COUNT = re.compile(r"(\d+)\s+(?:out\s+)?of\s+(?:the\s+)?(\d+)")


def miscounted(text: str, p: ClassPerformance) -> list[str]:
    """"N of M" claims that match no count in the snapshot.

    Observed live on MAT-150: "15 of 28 students below the 72% line". 15 of 28 is
    the word-problems strand; the class as a whole is 13 of 28. Every percentage
    in that sentence was real, so only a check on the counts catches it — and the
    check has to know which count belongs to which measure, not just that both
    numbers appear somewhere.
    """
    strand_pairs = {s.strand.lower(): (s.below_line, s.cohort) for s in p.strands}
    measures = [(r"declin|slid|falling|down", (p.declining, p.students)),
                (r"improv|rising|climb", (p.improving, p.students)),
                (r"plan|support", (p.needs_plan, p.students)),
                (r"below|under|line|behind", (p.below_line, p.students))]
    bad = []
    for m in COUNT.finditer(text):
        pair = (int(m.group(1)), int(m.group(2)))
        # Only the sentence the count sits in: the strand named two sentences ago is not its subject.
        before = re.split(r"[.;!?]\s", text[:m.start()])[-1].lower()
        after = re.split(r"[.;!?]\s", text[m.end():])[0].lower()
        named = [st for st in strand_pairs if st in before or st in after]
        if named:
            expected = {strand_pairs[st] for st in named}
        else:
            # The measure named first after the count is the one it counts.
            hits = [(hit.start(), want) for pattern, want in measures if (hit := re.search(pattern, after))]
            expected = {min(hits)[1]} if hits else {want for _, want in measures}
        if pair not in expected:
            bad.append(m.group(0))
    return bad


SUBMISSION_WORDS = re.compile(r"hand(?:ed|ing)?[ -]in|turn(?:ed|ing)?[ -]in|missing|submi|late work|incomplete|past[ -]due|"
                              r"overdue|catch[ -]?up",
                              re.IGNORECASE)


def unaddressed_causes(actions: list[str], p: ClassPerformance) -> list[str]:
    """Causes in the data that no action touches.

    Observed live: for a class with 16% of work never handed in and two weak
    strands, the model planned two reteach lessons and nothing about the missing
    work. Reteaching does not fix work that never arrives, so a plan that ignores
    a submission problem is sent back rather than adopted.
    """
    out = []
    if p.completion is not None and p.completion < COMPLETION_CONCERN and not any(
            SUBMISSION_WORDS.search(a) for a in actions):
        out.append(f"{100 * (1 - p.completion):.0f}% of past-due work is not handed in, "
                   "and no action deals with getting work handed in")
    return out


def unknown_strands(named: list[str], p: ClassPerformance) -> list[str]:
    known = {s.strand.lower() for s in p.strands}
    return [n for n in named if n.strip().lower() not in known]


def canonical_strands(named: list[str], p: ClassPerformance) -> list[str]:
    by_lower = {s.strand.lower(): s.strand for s in p.strands}
    return [by_lower[n.strip().lower()] for n in named if n.strip().lower() in by_lower]


# ---- adopting, and progress ---------------------------------------------------
def active_plan(db: Session, code: str) -> ClassPlan | None:
    return db.scalar(select(ClassPlan).where(ClassPlan.course_code == code, ClassPlan.status == "active"))


def adopt(db: Session, *, course_code: str, title: str, diagnosis: str, focus_strands: list[str],
          actions: list[str], goal: str, run_id: int | None = None, proposal_id: int | None = None,
          owner: str | None = None) -> ClassPlan:
    p = performance(db, course_code)
    if p is None:
        raise ValueError(f"{course_code} is no longer running.")
    if active_plan(db, course_code):
        raise ValueError(f"{course_code} already has an active improvement plan. "
                         "Complete or retire it before adopting another.")
    missing = unknown_strands(focus_strands, p)
    if missing:
        raise ValueError(f"{course_code} no longer teaches: {', '.join(missing)}.")
    plan = ClassPlan(course_code=course_code, title=title, diagnosis=diagnosis,
                     focus_strands=canonical_strands(focus_strands, p), actions=list(actions), goal=goal,
                     owner=owner or p.teacher, status="active", baseline=p.as_dict(),
                     opened_on=settings.today, review_on=settings.today + timedelta(days=REVIEW_AFTER_DAYS),
                     run_id=run_id, proposal_id=proposal_id)
    db.add(plan)
    db.flush()
    return plan


def progress(plan: ClassPlan, now: ClassPerformance | None) -> list[dict]:
    """Baseline against today, for the class average, work handed in, and each focus strand."""
    base = plan.baseline or {}
    rows = [("Class average", base.get("mean"), now.mean if now else None),
            ("Work handed in", _pct(base.get("completion")), _pct(now.completion) if now else None)]
    base_strands = {s["strand"]: s["mean"] for s in base.get("strands", [])}
    now_strands = {s.strand: s.mean for s in now.strands} if now else {}
    rows += [(s, base_strands.get(s), now_strands.get(s)) for s in plan.focus_strands or []]
    return [{"measure": m, "baseline": b, "now": n,
             "change": round(n - b, 1) if b is not None and n is not None else None}
            for m, b, n in rows]


def _pct(v: float | None) -> float | None:
    return round(100 * v, 1) if v is not None else None
