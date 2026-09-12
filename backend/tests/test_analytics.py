"""Engine unit tests on a purpose-built record, isolated from the seeded database.

Each test constructs exactly the situation it is about, so a failure names a rule
rather than a dataset.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analytics import BAND_EXCELLING, build_signals, skill_gaps
from app.db import Base
from app.models import Assessment, AttendanceDay, Course, Enrollment, Score, Student

TODAY = date(2026, 9, 12)
TERM = date(2026, 8, 10)
SKILLS = ["alpha", "beta"]


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    try:
        yield s
    finally:
        s.close()


def scenario(session, pcts, *, skills=None, absent_days=0, present_days=20,
             future_item=False, missing_indices=(), omit_row_indices=()):
    """One student, one course, one score per assessment.

    `pcts` are percentages in due-date order. Indices in `missing_indices` get a
    blank Score row; those in `omit_row_indices` get no row at all. Both mean
    "not submitted" and must behave identically.
    """
    st = Student(sid="S-0001", name="Test Student", grade=7, homeroom="7A")
    c = Course(code="TST-101", title="Test Course", dept="Testing", teacher="A. Teacher",
               period=1, room="T-1", capacity=30)
    session.add_all([st, c])
    session.flush()
    session.add(Enrollment(student_id=st.id, course_id=c.id, status="enrolled"))

    skills = skills or [SKILLS[i % len(SKILLS)] for i in range(len(pcts))]
    for i, pct in enumerate(pcts):
        a = Assessment(course_id=c.id, title=f"Item {i}", kind="quiz", skill=skills[i],
                       max_points=100.0, weight=1.0,
                       assigned_on=TERM + timedelta(days=i * 3),
                       due_on=TERM + timedelta(days=i * 3 + 2))
        session.add(a)
        session.flush()
        if i in omit_row_indices:
            continue
        session.add(Score(assessment_id=a.id, student_id=st.id,
                          points=None if i in missing_indices else float(pct)))

    if future_item:
        a = Assessment(course_id=c.id, title="Next week", kind="test", skill=skills[0],
                       max_points=100.0, weight=3.0,
                       assigned_on=TODAY, due_on=TODAY + timedelta(days=5))
        session.add(a)

    for d in range(present_days + absent_days):
        day = TERM + timedelta(days=d)
        session.add(AttendanceDay(student_id=st.id, day=day,
                                  status="absent" if d < absent_days else "present"))
    session.commit()
    return st, c


def only(session):
    sigs = build_signals(session, TODAY)
    assert len(sigs) == 1
    return next(iter(sigs.values()))


# --- mastery ---------------------------------------------------------------
def test_mastery_is_the_weighted_average(session):
    scenario(session, [80, 90, 70, 100])
    sig = only(session)
    assert sig.courses[0].pct == pytest.approx(85.0, abs=0.1)


def test_missing_past_due_work_counts_as_zero(session):
    scenario(session, [100, 100, 100, 100], missing_indices=(3,))
    sig = only(session)
    c = sig.courses[0]
    assert c.pct == pytest.approx(75.0, abs=0.1), "a missing piece must pull the grade down"
    assert c.missing == 1
    assert c.missing_rate == pytest.approx(0.25)


def test_a_blank_row_and_a_missing_row_mean_the_same_thing(session):
    scenario(session, [100, 100, 100, 100], missing_indices=(2,), omit_row_indices=(3,))
    c = only(session).courses[0]
    assert c.missing == 2
    assert c.pct == pytest.approx(50.0, abs=0.1)


def test_work_not_yet_due_is_excluded(session):
    scenario(session, [90, 90], future_item=True)
    c = only(session).courses[0]
    assert c.graded_items == 2, "a heavy future test must not count as a zero"
    assert c.pct == pytest.approx(90.0, abs=0.1)


# --- the excelling axis (regression) ---------------------------------------
def test_excelling_record_reaches_the_excelling_band(session):
    """Regression: excel_index was scaled so that even a near-perfect record
    could not reach its own band cutoff, so nobody ever read as excelling."""
    scenario(session, [95, 93, 96, 94, 95, 94])
    sig = only(session)
    assert sig.courses[0].excel_index >= BAND_EXCELLING, sig.courses[0]
    assert sig.band == "excelling", sig.band


def test_excel_index_climbs_with_mastery(session):
    engine_results = []
    for level in (80, 86, 92, 98):
        s = sessionmaker(bind=create_engine("sqlite://", connect_args={"check_same_thread": False},
                                            poolclass=StaticPool, future=True),
                         expire_on_commit=False, future=True)()
        Base.metadata.create_all(s.get_bind())
        scenario(s, [level] * 6)
        engine_results.append(build_signals(s, TODAY)["S-0001"].courses[0].excel_index)
        s.close()
    assert engine_results == sorted(engine_results)
    assert engine_results[0] < engine_results[-1]


def test_a_perfect_record_does_not_look_like_a_concern(session):
    scenario(session, [97, 98, 96, 99, 97, 98])
    sig = only(session)
    assert sig.struggle_index == 0
    assert sig.band == "excelling"


# --- the struggling axis ---------------------------------------------------
def test_decline_registers_even_when_the_average_is_fine(session):
    # Strong early, collapsing late: the average hides what the trend shows.
    scenario(session, [95, 95, 95, 70, 66, 62])
    c = only(session).courses[0]
    assert c.delta < -20, c.delta
    assert c.struggle_index > 0
    assert any(r.code == "declining" for r in only(session).reasons)


def test_absence_contributes_to_struggle(session):
    scenario(session, [88] * 6, absent_days=6, present_days=24)
    sig = only(session)
    assert sig.absence_rate == pytest.approx(0.2, abs=0.01)
    assert sig.struggle_index > 0
    assert any(r.code == "attendance" for r in sig.reasons)


def test_concern_outranks_excelling_in_the_band(session):
    """A student failing one subject and topping another is not 'average'."""
    st = Student(sid="S-0001", name="Split Student", grade=8, homeroom="8A")
    strong = Course(code="SCI-100", title="Science", dept="Science", teacher="T", capacity=30)
    weak = Course(code="MAT-100", title="Maths", dept="Mathematics", teacher="U", capacity=30)
    session.add_all([st, strong, weak])
    session.flush()
    session.add_all([Enrollment(student_id=st.id, course_id=strong.id, status="enrolled"),
                     Enrollment(student_id=st.id, course_id=weak.id, status="enrolled")])
    for course, level in ((strong, 97.0), (weak, 48.0)):
        for i in range(6):
            a = Assessment(course_id=course.id, title=f"i{i}", kind="quiz", skill="core",
                           max_points=100.0, weight=1.0,
                           assigned_on=TERM, due_on=TERM + timedelta(days=i * 3 + 2))
            session.add(a)
            session.flush()
            session.add(Score(assessment_id=a.id, student_id=st.id, points=level))
    for d in range(20):
        session.add(AttendanceDay(student_id=st.id, day=TERM + timedelta(days=d), status="present"))
    session.commit()

    sig = only(session)
    assert sig.band in ("needs-plan", "watch"), sig.band
    assert sig.excel_index >= 60, "the strength must still be reported, not averaged away"
    assert {r.kind for r in sig.reasons} == {"concern", "strength"}
    assert any(r.code == "enrichment-placement" or r.kind == "enrichment"
               for r in sig.recommendations) or any(
        r.code == "targeted-tutoring" for r in sig.recommendations)


# --- skills ---------------------------------------------------------------
def test_skills_isolate_the_weak_strand(session):
    scenario(session, [95, 45, 94, 43, 96, 47],
             skills=["alpha", "beta", "alpha", "beta", "alpha", "beta"])
    sig = only(session)
    strands = {s.skill: s.pct for s in sig.courses[0].skills}
    assert strands["alpha"] > 90 and strands["beta"] < 50
    assert sig.weakest_skills[0].skill == "beta"
    assert sig.strongest_skills[0].skill == "alpha"


def test_skill_gaps_report_the_cohort_not_the_individual(session):
    scenario(session, [95, 40, 95, 40], skills=["alpha", "beta", "alpha", "beta"])
    gaps = {g.skill: g for g in skill_gaps(session, TODAY)}
    assert gaps["beta"].class_mean < gaps["alpha"].class_mean
    assert gaps["beta"].students_below == 1
    assert gaps["beta"].cohort == 1


# --- edges ---------------------------------------------------------------
def test_student_with_no_graded_work_is_not_flagged(session):
    st = Student(sid="S-0001", name="New Arrival", grade=6, homeroom="6A")
    c = Course(code="TST-101", title="Test", dept="Testing", teacher="A", capacity=30)
    session.add_all([st, c])
    session.flush()
    session.add(Enrollment(student_id=st.id, course_id=c.id, status="enrolled"))
    session.add(Assessment(course_id=c.id, title="Future", kind="test", skill="core",
                           max_points=100.0, weight=1.0, assigned_on=TODAY,
                           due_on=TODAY + timedelta(days=7)))
    session.commit()
    sig = only(session)
    assert sig.courses == []
    assert sig.struggle_index == 0 and sig.excel_index == 0
    assert sig.band == "steady"
    assert sig.recommendations == []


def test_every_reason_carries_readable_detail(session):
    scenario(session, [55, 50, 48, 44, 40, 38], missing_indices=(4,), absent_days=5, present_days=20)
    sig = only(session)
    assert sig.reasons
    for r in sig.reasons:
        assert r.label and r.detail
        assert r.kind in ("concern", "strength")
        assert not r.detail.endswith(" ")
