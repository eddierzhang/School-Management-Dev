"""The general manager's screen: the school briefing, and what a manager run set in motion."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.manager import MANAGER_NAME, resume_queue
from ..auth.deps import module, require
from ..db import get_db
from ..models import AgentRun, Proposal
from ..school_briefing import build_briefing

# The briefing spans every domain (students, money, stock), so it is for administrators.
router = APIRouter(prefix="/manager", tags=["manager"], dependencies=[Depends(module("manager")), Depends(require("manager.run"))])


def _run(r: AgentRun) -> dict:
    return {"id": r.id, "agent": r.agent, "status": r.status, "prompt": r.prompt, "summary": r.summary,
            "error": r.error, "steps_used": r.steps_used, "duration_ms": r.duration_ms,
            "parent_run_id": r.parent_run_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


@router.get("/briefing")
def briefing(db: Session = Depends(get_db)) -> dict:
    return build_briefing(db)


@router.get("/runs")
def manager_runs(limit: int = 10, db: Session = Depends(get_db)) -> list[dict]:
    """Recent manager runs, each with the specialist runs it dispatched."""
    resume_queue(db)
    runs = db.scalars(select(AgentRun).where(AgentRun.agent == MANAGER_NAME)
                      .order_by(AgentRun.id.desc()).limit(min(limit, 50))).all()
    return [manager_run(r.id, db) for r in runs]


@router.get("/runs/{run_id}")
def manager_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    r = db.get(AgentRun, run_id)
    if r is None or r.agent != MANAGER_NAME:
        raise HTTPException(404, f"No manager run {run_id}")
    children = db.scalars(select(AgentRun).where(AgentRun.parent_run_id == r.id).order_by(AgentRun.id)).all()
    out = _run(r)
    out["dispatched"] = []
    for c in children:
        props = db.scalars(select(Proposal).where(Proposal.run_id == c.id)).all()
        out["dispatched"].append(_run(c) | {
            "proposals": [{"id": p.id, "summary": p.summary, "status": p.status} for p in props]})
    return out
