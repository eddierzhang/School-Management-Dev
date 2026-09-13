"""The two lists the support office actually works from, plus the reteach list."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..analytics import StudentSignal, skill_gaps
from ..auth.deps import Principal, require
from ..auth.scope import visible_courses, visible_students
from ..db import get_db
from ..deps import signals
from ..schemas import RecommendationOut, SkillGapOut, StudentDetail

router = APIRouter(tags=["support"])


def _visible(db: Session, user: Principal, sigs: dict[str, StudentSignal]) -> list[StudentSignal]:
    allowed = visible_students(db, user)
    return [s for s in sigs.values() if allowed is None or s.sid in allowed]


@router.get("/watchlist", response_model=list[StudentDetail])
def watchlist(
    limit: int = Query(25, ge=1, le=200),
    include_watch: bool = True,
    sigs: dict[str, StudentSignal] = Depends(signals),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("students.read")),
) -> list[StudentDetail]:
    bands = {"needs-plan", "watch"} if include_watch else {"needs-plan"}
    rows = [s for s in _visible(db, user, sigs) if s.band in bands]
    rows.sort(key=lambda s: -s.struggle_index)
    return [StudentDetail.model_validate(s) for s in rows[:limit]]


@router.get("/strengths", response_model=list[StudentDetail])
def strengths(
    limit: int = Query(25, ge=1, le=200),
    sigs: dict[str, StudentSignal] = Depends(signals),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("students.read")),
) -> list[StudentDetail]:
    """Students with something to build on — including ones who also have concerns.

    Deliberately not filtered to band == "excelling": a student who is failing
    maths and top of the class in science belongs on both lists, and the second
    list is where the school finds the lever.
    """
    rows = [s for s in _visible(db, user, sigs) if s.excel_index >= 60]
    rows.sort(key=lambda s: -s.excel_index)
    return [StudentDetail.model_validate(s) for s in rows[:limit]]


@router.get("/skill-gaps", response_model=list[SkillGapOut])
def gaps(
    limit: int = Query(40, ge=1, le=200),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("students.read")),
) -> list[SkillGapOut]:
    allowed = visible_courses(db, user)
    return [SkillGapOut.model_validate(g) for g in skill_gaps(db)
            if allowed is None or g.course_code in allowed][:limit]


@router.get("/recommendations", response_model=list[RecommendationOut])
def all_recommendations(
    priority: int | None = Query(None, ge=1, le=3),
    sigs: dict[str, StudentSignal] = Depends(signals),
    db: Session = Depends(get_db),
    user: Principal = Depends(require("students.read")),
) -> list[RecommendationOut]:
    out = []
    for s in _visible(db, user, sigs):
        for r in s.recommendations:
            if priority is None or r.priority == priority:
                out.append(RecommendationOut.model_validate(r))
    out.sort(key=lambda r: r.priority)
    return out
