from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import ollama
from ..ai.agents import FLEET
from ..ai.executor import ApplyError, apply_proposal, reject_proposal
from ..ai.runner import run_in_background
from ..config import get_settings
from ..db import get_db
from ..models import AgentRun, Proposal

router = APIRouter(prefix="/agents", tags=["agents"])
settings = get_settings()


class RunRequest(BaseModel):
    task: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    note: str | None = None


def _run_out(r: AgentRun, full: bool = False) -> dict:
    out = {"id": r.id, "agent": r.agent, "model": r.model, "prompt": r.prompt, "status": r.status,
           "summary": r.summary, "steps_used": r.steps_used, "tool_errors": r.tool_errors,
           "duration_ms": r.duration_ms, "error": r.error,
           "started_at": r.started_at.isoformat() if r.started_at else None,
           "finished_at": r.finished_at.isoformat() if r.finished_at else None,
           "proposals": len(r.proposals)}
    if full:
        out["transcript"] = r.transcript or []
    return out


def _proposal_out(p: Proposal) -> dict:
    return {"id": p.id, "run_id": p.run_id, "agent": p.agent, "kind": p.kind, "summary": p.summary,
            "reason": p.reason, "payload": p.payload, "evidence": p.evidence, "status": p.status,
            "result": p.result,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "decided_at": p.decided_at.isoformat() if p.decided_at else None}


@router.get("")
def list_fleet() -> dict:
    """The fleet, plus whether the local model can actually run it."""
    h = ollama.health()
    return {
        "runtime": h,
        "agents": [{"name": a.name, "title": a.title, "domain": a.domain,
                    "default_task": a.default_task,
                    "tools": [{"name": t.name, "description": t.description,
                               "proposes": t.proposes} for t in a.tools]}
                   for a in FLEET.values()],
    }


@router.post("/{name}/run", status_code=202)
def start_run(name: str, body: RunRequest, background: BackgroundTasks,
              db: Session = Depends(get_db)) -> dict:
    agent = FLEET.get(name)
    if agent is None:
        raise HTTPException(404, f"No agent named {name!r}. Fleet: {', '.join(FLEET)}")
    h = ollama.health()
    if not h["reachable"]:
        raise HTTPException(503, h["error"] or "Ollama is not reachable.")
    if not h.get("can_run_agents"):
        raise HTTPException(
            503,
            f"{settings.ollama_model} cannot call tools, so it cannot run an agent. "
            f"Install a tool-capable model (for example: ollama pull qwen3:4b) "
            f"and set HR_OLLAMA_MODEL.",
        )

    task = (body.task or "").strip() or agent.default_task
    run = AgentRun(agent=agent.name, model=settings.ollama_model, prompt=task, status="running",
                   transcript=[], started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    background.add_task(run_in_background, run.id, agent.name, task)
    return _run_out(run)


@router.get("/runs")
def list_runs(agent: str | None = None, limit: int = 25, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(AgentRun).order_by(AgentRun.id.desc()).limit(min(limit, 100))
    if agent:
        stmt = stmt.where(AgentRun.agent == agent)
    return [_run_out(r) for r in db.scalars(stmt).all()]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"No run {run_id}")
    return _run_out(run, full=True)


@router.get("/proposals")
def list_proposals(status: str | None = "pending", agent: str | None = None,
                   db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Proposal).order_by(Proposal.id.desc())
    if status:
        stmt = stmt.where(Proposal.status == status)
    if agent:
        stmt = stmt.where(Proposal.agent == agent)
    return [_proposal_out(p) for p in db.scalars(stmt).all()]


@router.post("/proposals/{pid}/approve")
def approve(pid: int, db: Session = Depends(get_db)) -> dict:
    p = db.get(Proposal, pid)
    if p is None:
        raise HTTPException(404, f"No proposal {pid}")
    try:
        result = apply_proposal(db, p)
    except ApplyError as e:
        p.status = "failed"
        p.result = str(e)
        p.decided_at = datetime.utcnow()
        db.commit()
        raise HTTPException(409, str(e)) from e
    return {"applied": True, "result": result, "proposal": _proposal_out(p)}


@router.post("/proposals/{pid}/reject")
def reject(pid: int, body: RejectRequest, db: Session = Depends(get_db)) -> dict:
    p = db.get(Proposal, pid)
    if p is None:
        raise HTTPException(404, f"No proposal {pid}")
    try:
        reject_proposal(db, p, body.note)
    except ApplyError as e:
        raise HTTPException(409, str(e)) from e
    return {"rejected": True, "proposal": _proposal_out(p)}
