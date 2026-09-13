"""The general manager: one agent over the fleet.

It does two jobs, and deliberately has no propose_ tools for either:

**Answers questions about the school.** Its read tool is the deterministic
briefing (app/school_briefing.py), so every number it quotes was computed, not
recalled. A 4B model asked to summarise the school from raw tables drops and
invents figures; asked to talk about a correct digest, it mostly does not.

**Puts the other agents to work.** `dispatch_agent` starts a specialist with a
task the manager writes. That is safe to do without approval because a
specialist can itself only *propose* — nothing a dispatched run does reaches the
records until a person approves it. The manager changes what gets looked at,
never what gets done.

Dispatched runs wait in a queue and start one at a time, after whatever is
running finishes. The queue is rebuilt from `queued` rows after a restart. Ollama serves one model; three agents started at once would
each take three times as long and all risk the wall-clock cap.
"""
from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AgentRun, Proposal
from .agents import FLEET, Agent, _tool
from .toolkit import ToolError

settings = get_settings()
MAX_DISPATCHES_PER_RUN = 3
MANAGER_NAME = "manager"
SECTIONS = ["overview", "students", "classes", "stockroom", "finance", "fleet"]


# ---- the queue ---------------------------------------------------------------
_queue: "queue.Queue[int]" = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()
_queued_ids: set[int] = set()


def _anything_running(db: Session) -> bool:
    return db.scalar(select(AgentRun.id).where(AgentRun.status == "running").limit(1)) is not None


def _work() -> None:
    from ..db import SessionLocal
    from .runner import run_in_background

    while True:
        run_id = _queue.get()
        try:
            waited = 0.0
            while waited < settings.agent_max_seconds * 3:
                with SessionLocal() as db:
                    if not _anything_running(db):
                        break
                time.sleep(3)
                waited += 3
            with SessionLocal() as db:
                run = db.get(AgentRun, run_id)
                if run is None or run.status != "queued":
                    continue
                run.status, run.started_at = "running", datetime.utcnow()
                agent, task = run.agent, run.prompt
                db.commit()
            run_in_background(run_id, agent, task)
        finally:
            with _lock:
                _queued_ids.discard(run_id)
            _queue.task_done()


def enqueue(run_id: int) -> None:
    global _worker
    with _lock:
        _queued_ids.add(run_id)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="fleet-dispatch", daemon=True)
            _worker.start()
    _queue.put(run_id)


QUEUED_TOO_LONG_HOURS = 6


def resume_queue(db: Session) -> None:
    """Pick up queued runs the in-memory queue lost.

    The dev server reloads whenever a file changes, and a reload empties the queue.
    The runs are still `queued` in the table, so they are put back in order rather
    than dropped. Only a run left waiting for hours is given up on.
    """
    with _lock:
        live = set(_queued_ids)
    cutoff = datetime.utcnow() - timedelta(hours=QUEUED_TOO_LONG_HOURS)
    for r in db.scalars(select(AgentRun).where(AgentRun.status == "queued").order_by(AgentRun.id)).all():
        if r.id in live:
            continue
        if r.started_at and r.started_at < cutoff:
            r.status, r.finished_at = "failed", datetime.utcnow()
            r.error = f"Waited over {QUEUED_TOO_LONG_HOURS} hours without starting. Dispatch it again."
        else:
            enqueue(r.id)
    db.commit()


# ---- tools ---------------------------------------------------------------------
def school_briefing(db: Session, ctx: dict, section: str = "overview") -> dict:
    from ..school_briefing import build_briefing

    section = (section or "overview").strip().lower()
    if section not in SECTIONS:
        raise ToolError(f"section must be one of: {', '.join(SECTIONS)}.")
    b = build_briefing(db)
    if section == "overview":
        s, c, st, f, fl = b["students"], b["classes"], b["stockroom"], b["finance"], b["fleet"]
        return {
            "school": b["school"], "term": b["term"], "as_of": b["as_of"],
            "needs_attention": b["attention"],
            "students": {k: s[k] for k in ("total", "needs_plan", "watch", "excelling", "open_plans",
                                           "needs_plan_without_one", "attendance_pct")},
            "going_well": [f"{s['excelling']} students are excelling",
                           *(f"{r['title']} averages {r['average']}%" for r in c["strongest"][:2])],
            "classes": {"sections": c["sections"],
                        "weakest": [f"{r['title']} {r['average']}%" for r in c["weakest"]],
                        "strongest": [f"{r['title']} {r['average']}%" for r in c["strongest"]]},
            "stockroom": {k: st[k] for k in ("needs_attention", "not_on_order", "on_requisition")},
            "finance": ({k: f[k] for k in ("budget", "spent", "committed", "over_budget", "at_risk",
                                           "charges_to_review", "year_elapsed_pct")}
                        if f.get("available") else "not set up"),
            "agent_proposals_waiting": fl["pending_proposals"],
            "note": "Call school_briefing with a section name for detail.",
        }
    return b[section]


def fleet_status(db: Session, ctx: dict) -> dict:
    rows = []
    for name, agent in FLEET.items():
        if name == MANAGER_NAME:
            continue
        last = db.scalar(select(AgentRun).where(AgentRun.agent == name).order_by(AgentRun.id.desc()).limit(1))
        pending = db.query(Proposal).filter(Proposal.agent == name, Proposal.status == "pending").count()
        rows.append({
            "agent": name, "title": agent.title, "handles": agent.domain,
            "busy": bool(last and last.status in ("running", "queued")),
            "last_run": ({"id": last.id, "status": last.status, "task": last.prompt[:120],
                          "summary": (last.summary or last.error or "")[:240]} if last else None),
            "proposals_waiting_for_approval": pending,
        })
    return {"agents": rows}


def agent_report(db: Session, ctx: dict, agent: str) -> dict:
    name = str(agent).strip().lower()
    if name not in FLEET or name == MANAGER_NAME:
        raise ToolError(f"No specialist named {agent!r}. Agents: "
                        f"{', '.join(n for n in FLEET if n != MANAGER_NAME)}.")
    runs = db.scalars(select(AgentRun).where(AgentRun.agent == name).order_by(AgentRun.id.desc()).limit(3)).all()
    pending = db.scalars(select(Proposal).where(Proposal.agent == name, Proposal.status == "pending")
                         .order_by(Proposal.id.desc()).limit(6)).all()
    return {
        "agent": name,
        "recent_runs": [{"id": r.id, "status": r.status, "task": r.prompt[:160],
                         "summary": (r.summary or r.error or "")[:400],
                         "proposals": db.query(Proposal).filter(Proposal.run_id == r.id).count()}
                        for r in runs],
        "waiting_for_approval": [{"id": p.id, "summary": p.summary, "reason": p.reason[:200]} for p in pending],
    }


def dispatch_agent(db: Session, ctx: dict, agent: str, task: str, reason: str) -> dict:
    name = str(agent).strip().lower()
    if name == MANAGER_NAME:
        raise ToolError("You cannot dispatch yourself. Dispatch a specialist.")
    if name not in FLEET:
        raise ToolError(f"No specialist named {agent!r}. Call fleet_status for the agents you can dispatch.")
    task = str(task or "").strip()
    if len(task) < 20:
        raise ToolError("Write the task as a full instruction of at least a sentence, naming what to look at.")
    sent = ctx.setdefault("dispatched", [])
    if len(sent) >= MAX_DISPATCHES_PER_RUN:
        raise ToolError(f"You have already dispatched {MAX_DISPATCHES_PER_RUN} agents this run. Give your summary.")
    if any(d["agent"] == name for d in sent):
        raise ToolError(f"You already dispatched {name} in this run.")
    busy = db.scalar(select(AgentRun).where(AgentRun.agent == name, AgentRun.status.in_(["running", "queued"])).limit(1))
    if busy is not None:
        raise ToolError(f"{name} is already working (run #{busy.id}). Do not dispatch it again; mention it in your summary.")

    parent = ctx.get("run_id") or db.scalar(
        select(AgentRun.id).where(AgentRun.agent == MANAGER_NAME, AgentRun.status == "running")
        .order_by(AgentRun.id.desc()).limit(1))
    run = AgentRun(agent=name, model=settings.ollama_model, prompt=task, status="queued",
                   transcript=[], started_at=datetime.utcnow(), parent_run_id=parent)
    db.add(run)
    db.commit()
    db.refresh(run)
    enqueue(run.id)
    sent.append({"agent": name, "run_id": run.id, "task": task, "reason": str(reason)[:300]})
    return {"dispatched": True, "agent": name, "run_id": run.id,
            "note": "Queued. It runs after current work finishes and will only PROPOSE changes for a person "
                    "to approve. Do not wait for it. Dispatch another agent if needed, or give your summary."}


MANAGER = Agent(
    name=MANAGER_NAME,
    title="General manager",
    domain="The whole school: answers questions about it, and puts the other agents to work.",
    system=(
        "You are the general manager of Halverson Ridge High School. You oversee four specialist "
        "agents: support (students), registrar (classes and timetable), stockroom (supplies) and finance "
        "(budget), plus any others fleet_status lists.\n\n"
        "If the person asks a QUESTION about the school, call school_briefing (with a section for "
        "detail) and answer using only the numbers the tools returned. Do not dispatch anyone for a "
        "question. Write the answer as full, grammatical sentences in this shape:\n"
        "  1. One sentence on the overall picture.\n"
        "  2. The most important concerns, one sentence each, each with its number — cover students, "
        "classes and money if the briefing raises them.\n"
        "  3. One sentence on something going well.\n\n"
        "If the person asks you to GET WORK DONE, look at school_briefing and fleet_status, then call "
        "dispatch_agent for each specialist that should act, with a specific task that names the "
        "classes, students, items or budget lines to look at. Dispatch only agents whose area has a "
        "real problem. Then write a short summary of what you dispatched and why.\n\n"
        "Rules:\n"
        "- Use tools to get facts. Never invent a number, name or code.\n"
        "- WRITING THAT YOU DISPATCHED AN AGENT DOES NOT DISPATCH IT. Only calling dispatch_agent does.\n"
        "- Specialists only propose changes; people approve them. Say so if asked what will happen.\n"
        f"- Dispatch at most {MAX_DISPATCHES_PER_RUN} agents. Finish with a summary of at most six sentences."
    ),
    default_task="Give me a briefing on the school: what needs attention first, and why.",
    opening=("school_briefing", {"section": "overview"}),
    tools=[
        _tool(school_briefing, "school_briefing",
              "Computed facts about the school. 'overview' gives headline numbers and what needs attention; "
              "a section gives detail.",
              {"type": "object", "properties": {
                  "section": {"type": "string", "enum": SECTIONS,
                              "description": "overview, students, classes, stockroom, finance or fleet."}},
               "required": []}),
        _tool(fleet_status, "fleet_status",
              "The specialist agents: what each handles, whether it is busy, its last run, and proposals waiting.",
              {"type": "object", "properties": {}, "required": []}),
        _tool(agent_report, "agent_report",
              "One specialist's recent runs, what they concluded, and its proposals waiting for approval.",
              {"type": "object", "properties": {
                  "agent": {"type": "string", "description": "Agent name, e.g. finance."}},
               "required": ["agent"]}),
        _tool(dispatch_agent, "dispatch_agent",
              "Start a specialist agent on a task you write. It queues, runs after current work, and only proposes.",
              {"type": "object", "properties": {
                  "agent": {"type": "string", "description": "Specialist name from fleet_status."},
                  "task": {"type": "string", "description": "A specific instruction naming what to look at."},
                  "reason": {"type": "string", "description": "The fact from the briefing that makes this necessary."}},
               "required": ["agent", "task", "reason"]}),
    ],
)
