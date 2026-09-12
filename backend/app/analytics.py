"""The signal engine: who is struggling, who is excelling, and on what.

Every number here is explainable. A student never appears on the watchlist
because "the model said so" — they appear with named reasons, each traceable to
a rule with a stated threshold, because a support office has to defend a
referral to a teacher, a parent, and sometimes the student.

Two independent axes, not one scale:

  struggle_index  0.55·low mastery + 0.20·decline + 0.15·missing work + 0.10·absence
  excel_index     0.55·high mastery + 0.20·improvement + 0.15·completion + 0.10·consistency

They are deliberately separate. A student acing science while failing maths is
not "average" — averaging those into one number is how such a student gets
missed. Both indices are always reported, and the band names the more urgent one.

Skill tags are what make the "on what" answerable: mastery is rolled up per
`Assessment.skill`, so the engine can say *linear equations, not graphing* —
the difference between a useful referral and a shrug.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Assessment, AttendanceDay, Course, Enrollment, Intervention, Score, Student

settings = get_settings()


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# --- weights, in one place so they can be argued with -----------------------
STRUGGLE_WEIGHTS = {"mastery": 0.55, "decline": 0.20, "missing": 0.15, "absence": 0.10}
EXCEL_WEIGHTS = {"mastery": 0.55, "improvement": 0.20, "completion": 0.15, "consistency": 0.10}

# Normalisation scales: the value at which a factor counts as "fully present".
DECLINE_FULL = 15.0     # a 15-point drop between recent and prior work
MISSING_FULL = 0.35     # 35% of graded work not submitted
ABSENCE_FULL = 0.15     # absent 15% of school days
IMPROVE_FULL = 12.0     # a 12-point gain
SPREAD_FULL = 22.0      # score spread at which consistency reads as zero

# Mastery curves. These are deliberately separate from `support_threshold`, which
# is policy: the threshold decides when a grade needs a documented plan, while
# these decide how loudly the index speaks. Mastery carries enough weight that
# failing one class reaches the "needs a plan" band on its own, with no help from
# any other factor — an earlier weighting capped mastery's contribution below the
# band's own cutoff, so a student at 48% with perfect attendance read as "steady".
MASTERY_CONCERN_START = 80.0   # below here, concern starts to register (a B- holds)
MASTERY_CONCERN_FULL = 50.0    # at or below here, mastery concern is total
EXCEL_FLOOR = 80.0             # below here, nothing counts toward excelling
EXCEL_FULL = 96.0              # at or above here, mastery credit is total

BAND_NEEDS_PLAN = 55
BAND_WATCH = 35
BAND_EXCELLING = 70


@dataclass
class Reason:
    code: str
    label: str
    detail: str
    kind: str  # "concern" | "strength"


@dataclass
class SkillMastery:
    skill: str
    pct: float
    graded: int
    missing: int
    course_code: str = ""


@dataclass
class CourseSignal:
    course_code: str
    course_title: str
    dept: str
    teacher: str
    pct: float
    recent_pct: float | None
    prior_pct: float | None
    delta: float
    graded_items: int
    missing: int
    missing_rate: float
    completion: float
    spread: float
    struggle_index: int
    excel_index: int
    skills: list[SkillMastery] = field(default_factory=list)


@dataclass
class Recommendation:
    code: str
    title: str
    rationale: str
    kind: str
    priority: int              # 1 highest
    course_code: str | None = None
    suggested_owner: str = "Support office"


@dataclass
class StudentSignal:
    sid: str
    name: str
    grade: int
    homeroom: str
    struggle_index: int
    excel_index: int
    band: str
    days_counted: int
    absences: int
    tardies: int
    absence_rate: float
    tardy_rate: float
    courses: list[CourseSignal] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    weakest_skills: list[SkillMastery] = field(default_factory=list)
    strongest_skills: list[SkillMastery] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    open_interventions: int = 0


# ---------------------------------------------------------------------------
def _weighted_pct(items: list[tuple[float, float, float]]) -> float | None:
    """items: (points, max_points, weight). Returns 0-100, or None if nothing graded."""
    den = sum(mx * w for _, mx, w in items)
    if den <= 0:
        return None
    num = sum(p * w for p, _, w in items)
    return round(100.0 * num / den, 1)


def _band(struggle: int, excel: int) -> str:
    if struggle >= BAND_NEEDS_PLAN:
        return "needs-plan"
    if struggle >= BAND_WATCH:
        return "watch"
    if excel >= BAND_EXCELLING:
        return "excelling"
    return "steady"


def build_signals(db: Session, today: date | None = None) -> dict[str, StudentSignal]:
    """One pass over the record, returning a signal per student, keyed by SID."""
    today = today or settings.today

    students = db.scalars(select(Student)).all()
    courses = {c.id: c for c in db.scalars(select(Course)).all()}
    assessments = db.scalars(select(Assessment)).all()
    graded = [a for a in assessments if a.due_on <= today]
    graded_by_course: dict[int, list[Assessment]] = defaultdict(list)
    for a in graded:
        graded_by_course[a.course_id].append(a)
    for lst in graded_by_course.values():
        lst.sort(key=lambda a: a.due_on)

    scores: dict[tuple[int, int], Score] = {
        (s.assessment_id, s.student_id): s for s in db.scalars(select(Score)).all()
    }
    enrollments = db.scalars(select(Enrollment).where(Enrollment.status == "enrolled")).all()
    by_student: dict[int, list[Enrollment]] = defaultdict(list)
    for e in enrollments:
        by_student[e.student_id].append(e)

    attendance: dict[int, list[AttendanceDay]] = defaultdict(list)
    for a in db.scalars(select(AttendanceDay).where(AttendanceDay.day <= today)).all():
        attendance[a.student_id].append(a)

    open_iv: dict[int, int] = defaultdict(int)
    for iv in db.scalars(select(Intervention).where(Intervention.status == "active")).all():
        open_iv[iv.student_id] += 1

    catalog = _catalog_context(db, courses)
    out: dict[str, StudentSignal] = {}

    for st in students:
        days = attendance.get(st.id, [])
        absences = sum(1 for d in days if d.status == "absent")
        tardies = sum(1 for d in days if d.status == "tardy")
        n_days = len(days)
        absence_rate = round(absences / n_days, 4) if n_days else 0.0
        tardy_rate = round(tardies / n_days, 4) if n_days else 0.0
        absence_norm = clamp(absence_rate / ABSENCE_FULL)

        course_signals: list[CourseSignal] = []
        for enr in by_student.get(st.id, []):
            course = courses.get(enr.course_id)
            if course is None:
                continue
            items = graded_by_course.get(course.id, [])
            if not items:
                continue
            sig = _course_signal(course, items, scores, st.id, absence_norm)
            if sig is not None:
                course_signals.append(sig)

        course_signals.sort(key=lambda c: c.struggle_index, reverse=True)

        if course_signals:
            struggle = _rollup([c.struggle_index for c in course_signals], breadth=0.35)
            excel = _rollup([c.excel_index for c in course_signals], breadth=0.25)
        else:
            struggle = excel = 0

        sig = StudentSignal(
            sid=st.sid, name=st.name, grade=st.grade, homeroom=st.homeroom,
            struggle_index=struggle, excel_index=excel, band=_band(struggle, excel),
            days_counted=n_days, absences=absences, tardies=tardies,
            absence_rate=absence_rate, tardy_rate=tardy_rate,
            courses=course_signals, open_interventions=open_iv.get(st.id, 0),
        )
        _attach_skills(sig)
        sig.reasons = _reasons(sig)
        sig.recommendations = _recommend(sig, catalog)
        out[st.sid] = sig

    return out


def _rollup(values: list[int], breadth: float) -> int:
    """The worst (or best) course sets the level; the rest add urgency on top.

    Averaging across courses was wrong twice over: it made a student failing one
    subject look fine because five others were fine, and it quietly punished
    students who take more classes, since the same failing grade got diluted
    further with every extra course on the timetable. One bad class is a referral
    on its own; several is worse than one.
    """
    if not values:
        return 0
    ordered = sorted(values, reverse=True)
    lead, rest = ordered[0], ordered[1:]
    if not rest:
        return int(round(lead))
    # Breadth consumes a share of the REMAINING headroom rather than being added
    # on top. Adding it outright pushed most multi-course students to 100, which
    # flattened the ranking exactly where it matters most — among the worst cases.
    spread = statistics.fmean(rest) / 100.0
    return int(min(100, round(lead + breadth * (100 - lead) * spread)))


def _course_signal(
    course: Course, items: list[Assessment],
    scores: dict[tuple[int, int], Score], student_id: int, absence_norm: float,
) -> CourseSignal | None:
    graded_tuples: list[tuple[float, float, float]] = []
    per_item_pct: list[tuple[date, float]] = []
    per_skill: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    skill_missing: dict[str, int] = defaultdict(int)
    missing = 0

    for a in items:
        sc = scores.get((a.id, student_id))
        submitted = sc is not None and sc.points is not None
        pts = float(sc.points) if submitted else 0.0   # missing past-due work counts as zero
        if not submitted:
            missing += 1
            skill_missing[a.skill] += 1
        graded_tuples.append((pts, a.max_points, a.weight))
        per_skill[a.skill].append((pts, a.max_points, a.weight))
        if a.max_points > 0:
            per_item_pct.append((a.due_on, 100.0 * pts / a.max_points))

    pct = _weighted_pct(graded_tuples)
    if pct is None:
        return None

    n = len(items)
    missing_rate = missing / n if n else 0.0
    completion = 1.0 - missing_rate

    per_item_pct.sort(key=lambda t: t[0])
    vals = [v for _, v in per_item_pct]
    recent_vals, prior_vals = vals[-3:], vals[-6:-3]
    recent = round(statistics.fmean(recent_vals), 1) if len(recent_vals) >= 2 else None
    prior = round(statistics.fmean(prior_vals), 1) if len(prior_vals) >= 2 else None
    delta = round(recent - prior, 1) if (recent is not None and prior is not None) else 0.0
    spread = round(statistics.pstdev(vals), 1) if len(vals) >= 2 else 0.0

    mastery_low = clamp((MASTERY_CONCERN_START - pct) / (MASTERY_CONCERN_START - MASTERY_CONCERN_FULL))
    decline = clamp(-delta / DECLINE_FULL)
    missing_norm = clamp(missing_rate / MISSING_FULL)
    struggle = round(100 * (
        STRUGGLE_WEIGHTS["mastery"] * mastery_low
        + STRUGGLE_WEIGHTS["decline"] * decline
        + STRUGGLE_WEIGHTS["missing"] * missing_norm
        + STRUGGLE_WEIGHTS["absence"] * absence_norm
    ))

    mastery_high = clamp((pct - EXCEL_FLOOR) / (EXCEL_FULL - EXCEL_FLOOR))
    improvement = clamp(delta / IMPROVE_FULL)
    consistency = clamp(1.0 - spread / SPREAD_FULL)
    excel = round(100 * (
        EXCEL_WEIGHTS["mastery"] * mastery_high
        + EXCEL_WEIGHTS["improvement"] * improvement
        + EXCEL_WEIGHTS["completion"] * completion
        + EXCEL_WEIGHTS["consistency"] * consistency
    ))

    skills = []
    for skill, tup in per_skill.items():
        spct = _weighted_pct(tup)
        if spct is None:
            continue
        skills.append(SkillMastery(skill=skill, pct=spct, graded=len(tup),
                                   missing=skill_missing.get(skill, 0), course_code=course.code))
    skills.sort(key=lambda s: s.pct)

    return CourseSignal(
        course_code=course.code, course_title=course.title, dept=course.dept, teacher=course.teacher,
        pct=pct, recent_pct=recent, prior_pct=prior, delta=delta,
        graded_items=n, missing=missing, missing_rate=round(missing_rate, 4),
        completion=round(completion, 4), spread=spread,
        struggle_index=struggle, excel_index=excel, skills=skills,
    )


def _attach_skills(sig: StudentSignal) -> None:
    every = [s for c in sig.courses for s in c.skills if s.graded >= 2]
    every.sort(key=lambda s: s.pct)
    sig.weakest_skills = every[:4]
    sig.strongest_skills = list(reversed(every[-4:]))


def _reasons(sig: StudentSignal) -> list[Reason]:
    out: list[Reason] = []
    for c in sig.courses:
        if c.pct < settings.concern_floor:
            out.append(Reason("low-grade", f"Failing {c.course_code}",
                              f"{c.pct:.0f}% in {c.course_title}, below the {settings.concern_floor:.0f}% floor.",
                              "concern"))
        elif c.pct < settings.support_threshold:
            out.append(Reason("below-support", f"{c.course_code} below the support line",
                              f"{c.pct:.0f}% in {c.course_title}, under the {settings.support_threshold:.0f}% threshold.",
                              "concern"))
        if c.delta <= -8:
            out.append(Reason("declining", f"Slipping in {c.course_code}",
                              f"Down {abs(c.delta):.0f} points: last three pieces averaged "
                              f"{c.recent_pct:.0f}% against {c.prior_pct:.0f}% before.", "concern"))
        if c.missing_rate >= 0.15:
            out.append(Reason("missing-work", f"Missing work in {c.course_code}",
                              f"{c.missing} of {c.graded_items} assignments not submitted.", "concern"))
        if c.excel_index >= BAND_EXCELLING:
            out.append(Reason("excelling", f"Excelling in {c.course_code}",
                              f"{c.pct:.0f}% in {c.course_title}"
                              + (f", up {c.delta:.0f} points recently." if c.delta >= 4 else "."), "strength"))
        elif c.delta >= 8:
            out.append(Reason("improving", f"Climbing in {c.course_code}",
                              f"Up {c.delta:.0f} points on recent work, now {c.pct:.0f}%.", "strength"))

    if sig.absence_rate >= 0.12:
        out.append(Reason("attendance", "Attendance is eroding instruction time",
                          f"Absent {sig.absences} of {sig.days_counted} days "
                          f"({sig.absence_rate * 100:.0f}%).", "concern"))
    elif sig.tardy_rate >= 0.20:
        out.append(Reason("tardies", "Frequently late",
                          f"Tardy {sig.tardies} of {sig.days_counted} days.", "concern"))

    declining = [c.course_code for c in sig.courses if c.delta <= -8]
    if len(declining) >= 2:
        out.insert(0, Reason("broad-decline", "Slipping in more than one class",
                             "Recent work is down in " + ", ".join(declining)
                             + " — a pattern rather than one hard unit.", "concern"))
    return out


def _catalog_context(db: Session, courses: dict[int, Course]) -> dict[str, list[Course]]:
    """Courses with room in them, by department — the enrichment placements available."""
    counts: dict[int, int] = defaultdict(int)
    for e in db.scalars(select(Enrollment).where(Enrollment.status == "enrolled")).all():
        counts[e.course_id] += 1
    by_dept: dict[str, list[Course]] = defaultdict(list)
    for c in courses.values():
        if counts[c.id] < c.capacity:
            by_dept[c.dept].append(c)
    return by_dept


def _recommend(sig: StudentSignal, catalog: dict[str, list[Course]]) -> list[Recommendation]:
    """Rules, in priority order. Each says what to do and why, not just 'at risk'."""
    recs: list[Recommendation] = []
    enrolled_codes = {c.course_code for c in sig.courses}

    if sig.absence_rate >= 0.12:
        recs.append(Recommendation(
            "attendance-plan", "Attendance plan with a family call",
            f"Absent {sig.absences} of {sig.days_counted} days. Grades follow attendance; "
            "tutoring on top of missed instruction rarely holds.",
            "attendance-plan", 1, suggested_owner="Attendance office"))

    declining = [c for c in sig.courses if c.delta <= -8]
    if len(declining) >= 2:
        recs.append(Recommendation(
            "counselor-check-in", "Counselor check-in this week",
            "Down in " + ", ".join(c.course_code for c in declining)
            + ". A decline across unrelated subjects usually is not about the subjects.",
            "check-in", 1, suggested_owner="Counseling"))

    for c in sig.courses:
        if c.missing_rate >= 0.25:
            recs.append(Recommendation(
                "homework-recovery", f"Homework recovery block for {c.course_code}",
                f"{c.missing} of {c.graded_items} pieces missing in {c.course_title}. "
                "The grade is a submission problem before it is a comprehension problem.",
                "homework-recovery", 1, c.course_code, "Study hall lead"))
        elif c.pct < settings.concern_floor and c.skills:
            weak = c.skills[0]
            recs.append(Recommendation(
                "targeted-tutoring", f"Tutoring on {weak.skill}",
                f"{c.pct:.0f}% in {c.course_title} with work turned in — the gap is comprehension. "
                f"Weakest strand is {weak.skill} at {weak.pct:.0f}%.",
                "tutoring", 1, c.course_code, c.teacher))
        elif settings.concern_floor <= c.pct < settings.support_threshold:
            recs.append(Recommendation(
                "progress-monitor", f"Two-week progress check on {c.course_code}",
                f"{c.pct:.0f}% sits just under the {settings.support_threshold:.0f}% line. "
                "Worth watching before it needs a plan.",
                "check-in", 2, c.course_code, c.teacher))

    for c in sig.courses:
        if c.excel_index >= BAND_EXCELLING:
            placements = [x for x in catalog.get(c.dept, []) if x.code not in enrolled_codes]
            if placements:
                pick = placements[0]
                recs.append(Recommendation(
                    "enrichment-placement", f"Offer a seat in {pick.code} — {pick.title}",
                    f"{c.pct:.0f}% in {c.course_title} and {pick.title} has room. "
                    f"Same department, so it builds on strength rather than adding load.",
                    "enrichment", 3, pick.code, "Registrar"))
            else:
                recs.append(Recommendation(
                    "enrichment-extension", f"Extension work in {c.course_code}",
                    f"{c.pct:.0f}% in {c.course_title} with nothing open in {c.dept} to move into.",
                    "enrichment", 3, c.course_code, c.teacher))
            break

    recs.sort(key=lambda r: r.priority)
    return recs


# --- cohort views: what the school should act on, not just who --------------
@dataclass
class SkillGap:
    course_code: str
    course_title: str
    dept: str
    teacher: str
    skill: str
    class_mean: float
    students_below: int
    cohort: int
    share_below: float


def skill_gaps(db: Session, today: date | None = None) -> list[SkillGap]:
    """Per course, per skill: how the cohort did. This is the reteach list.

    A single student below on 'linear equations' is a tutoring referral. Half the
    class below on it is a lesson to run again, and no amount of tutoring fixes
    that one student at a time.
    """
    signals = build_signals(db, today)
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    meta: dict[str, CourseSignal] = {}
    for sig in signals.values():
        for c in sig.courses:
            meta.setdefault(c.course_code, c)
            for s in c.skills:
                buckets[(c.course_code, s.skill)].append(s.pct)

    out: list[SkillGap] = []
    for (code, skill), vals in buckets.items():
        c = meta[code]
        below = sum(1 for v in vals if v < settings.support_threshold)
        out.append(SkillGap(
            course_code=code, course_title=c.course_title, dept=c.dept, teacher=c.teacher,
            skill=skill, class_mean=round(statistics.fmean(vals), 1),
            students_below=below, cohort=len(vals),
            share_below=round(below / len(vals), 4) if vals else 0.0,
        ))
    out.sort(key=lambda g: (g.class_mean, -g.share_below))
    return out


DISTRIBUTION_BUCKETS = [(0, 60, "Below 60"), (60, 70, "60–69"), (70, 80, "70–79"),
                        (80, 90, "80–89"), (90, 101, "90–100")]


def course_distribution(signals: dict[str, StudentSignal], code: str) -> list[dict]:
    vals = [c.pct for sig in signals.values() for c in sig.courses if c.course_code == code]
    return [{"label": label, "count": sum(1 for v in vals if lo <= v < hi)}
            for lo, hi, label in DISTRIBUTION_BUCKETS]
