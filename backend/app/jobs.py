"""The job queue: background work kept in the database and run by a separate worker.

Agent runs and document reads take minutes on a local model. They used to run
inside the web process, which lost them on every restart, and with more than one
web worker could put several model calls on one GPU at once. Now a request
records a job and returns; `python -m app.worker` claims jobs one at a time and
runs them.

    enqueue(db, kind, payload)    record a job (committed with the caller's transaction if commit=False)
    run_once(worker_id)           claim the oldest runnable job and run it; False when there is none
    run_pending()                 run until the queue is empty (tests, and `python -m app.worker --drain`)
    reap_stale()                  requeue jobs whose worker stopped heartbeating; give up after max_attempts
    schedule_daily(today)         enqueue the day's snapshot once, however many workers ask

Claiming is a guarded UPDATE (`... WHERE id = ? AND status = 'queued'`), which is
atomic on Postgres and SQLite alike: two workers can race for a job, but only one
update matches. Model-bound jobs (agent runs, document reads) are claimed only
while no other model-bound job is running, so Ollama serves one at a time. Run
one worker per model host.
"""
from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from datetime import date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import AgentRun, Job, StudentDocument, WorkerBeat

settings = get_settings()
log = logging.getLogger("halverson.jobs")

MODEL_BOUND = ("agent_run", "document_analysis")
HEARTBEAT_EVERY = 30          # seconds
RETRY_BACKOFF = 60            # seconds, times the attempt number


def _stale_after() -> timedelta:
    # A healthy worker heartbeats every 30s whatever the job is doing, so two
    # minutes of silence means the process is gone.
    return timedelta(seconds=max(120, HEARTBEAT_EVERY * 4))


# ---- handlers ----------------------------------------------------------------------
def _agent_run(payload: dict) -> None:
    from .ai.runner import run_in_background

    with SessionLocal() as db:
        run = db.get(AgentRun, payload["run_id"])
        if run is None or run.status not in ("queued", "running"):
            return
        run.status, run.started_at = "running", datetime.utcnow()
        db.commit()
    opening = payload.get("opening")
    run_in_background(payload["run_id"], payload["agent"], payload["task"],
                      opening=tuple(opening) if opening else None, scope=payload.get("scope"))


def _document_analysis(payload: dict) -> None:
    from .ai.documents import analyse_in_background

    analyse_in_background(payload["doc_id"])


def _snapshot(payload: dict) -> None:
    from .history import take_snapshots

    with SessionLocal() as db:
        take_snapshots(db, date.fromisoformat(payload["on"]) if payload.get("on") else None)


HANDLERS: dict[str, Callable[[dict], None]] = {
    "agent_run": _agent_run,
    "document_analysis": _document_analysis,
    "snapshot": _snapshot,
}


def _give_up(db: Session, job: Job) -> None:
    """The job will not run again: say so on the thing a person is looking at."""
    last_line = next((ln for ln in reversed((job.error or "").splitlines()) if ln.strip()), "no error recorded")
    msg = f"The background job stopped after {job.attempts} attempt(s): {last_line.strip()}"
    if job.kind == "agent_run":
        run = db.get(AgentRun, job.payload.get("run_id"))
        if run is not None and run.status in ("queued", "running"):
            run.status, run.error, run.finished_at = "failed", msg, datetime.utcnow()
    elif job.kind == "document_analysis":
        doc = db.get(StudentDocument, job.payload.get("doc_id"))
        if doc is not None and doc.status == "processing":
            doc.status, doc.error = "failed", msg


# ---- the queue ---------------------------------------------------------------------
def enqueue(db: Session, kind: str, payload: dict, *, unique_key: str | None = None,
            run_after: datetime | None = None, max_attempts: int = 3, commit: bool = True) -> Job | None:
    """Record a job. With a `unique_key` already used, nothing is added and None is returned."""
    if kind not in HANDLERS:
        raise ValueError(f"No handler for job kind {kind!r}")
    if unique_key and db.scalar(select(Job.id).where(Job.unique_key == unique_key)):
        return None
    job = Job(kind=kind, payload=payload, status="queued", attempts=0, max_attempts=max_attempts,
              run_after=run_after or datetime.utcnow(), unique_key=unique_key)
    db.add(job)
    if commit:
        try:
            db.commit()
        except IntegrityError:            # another worker enqueued the same unique job first
            db.rollback()
            return None
    return job


def _claim(db: Session, worker_id: str) -> Job | None:
    now = datetime.utcnow()
    model_busy = db.scalar(select(Job.id).where(Job.status == "running", Job.kind.in_(MODEL_BOUND)).limit(1))
    stmt = select(Job).where(Job.status == "queued", Job.run_after <= now).order_by(Job.id).limit(5)
    if model_busy is not None:
        stmt = stmt.where(Job.kind.not_in(MODEL_BOUND))
    for candidate in db.scalars(stmt).all():
        won = db.execute(update(Job).where(Job.id == candidate.id, Job.status == "queued").values(
            status="running", locked_by=worker_id, heartbeat_at=now, started_at=now,
            attempts=Job.attempts + 1)).rowcount
        db.commit()
        if won == 1:
            return db.get(Job, candidate.id)
    return None


def _heartbeat(job_id: int, worker_id: str, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_EVERY):
        try:
            with SessionLocal() as db:
                now = datetime.utcnow()
                db.execute(update(Job).where(Job.id == job_id, Job.locked_by == worker_id).values(heartbeat_at=now))
                beat(db, worker_id, job_id, now)
        except Exception:
            log.exception("heartbeat failed for job %s", job_id)


def beat(db: Session, worker_id: str, job_id: int | None = None, now: datetime | None = None) -> None:
    row = db.get(WorkerBeat, worker_id)
    if row is None:
        db.add(WorkerBeat(worker_id=worker_id, seen_at=now or datetime.utcnow(), current_job_id=job_id))
    else:
        row.seen_at, row.current_job_id = now or datetime.utcnow(), job_id
    db.commit()


def run_once(worker_id: str = "inline") -> bool:
    with SessionLocal() as db:
        job = _claim(db, worker_id)
        if job is None:
            return False
        job_id, kind, payload = job.id, job.kind, dict(job.payload or {})
        beat(db, worker_id, job_id)

    log.info("job started", extra={"job_id": job_id, "kind": kind, "worker": worker_id})
    stop = threading.Event()
    pulse = threading.Thread(target=_heartbeat, args=(job_id, worker_id, stop), daemon=True)
    pulse.start()
    error = None
    try:
        HANDLERS[kind](payload)
    except Exception:
        error = traceback.format_exc(limit=8)
        log.exception("job failed", extra={"job_id": job_id, "kind": kind})
    finally:
        stop.set()
        pulse.join(timeout=5)

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        now = datetime.utcnow()
        if error is None:
            job.status, job.finished_at, job.error = "done", now, None
        elif job.attempts < job.max_attempts:
            job.status, job.error = "queued", error
            job.run_after = now + timedelta(seconds=RETRY_BACKOFF * job.attempts)
            job.locked_by = None
        else:
            job.status, job.finished_at, job.error = "failed", now, error
            _give_up(db, job)
        db.commit()
        beat(db, worker_id, None)
    log.info("job finished", extra={"job_id": job_id, "kind": kind, "status": "done" if error is None else "error"})
    return True


def run_pending(worker_id: str = "inline", limit: int = 100) -> int:
    """Run runnable jobs until none are left. Returns how many ran."""
    ran = 0
    while ran < limit and run_once(worker_id):
        ran += 1
    return ran


def reap_stale(now: datetime | None = None) -> int:
    """A running job whose heartbeat stopped belongs to a worker that died. Put it back."""
    now = now or datetime.utcnow()
    with SessionLocal() as db:
        stale = db.scalars(select(Job).where(Job.status == "running",
                                             Job.heartbeat_at < now - _stale_after())).all()
        for job in stale:
            job.error = f"Worker {job.locked_by} stopped responding while running this job."
            job.locked_by = None
            if job.attempts < job.max_attempts:
                job.status, job.run_after = "queued", now
            else:
                job.status, job.finished_at = "failed", now
                _give_up(db, job)
        db.commit()
        return len(stale)


def schedule_daily(today: date | None = None, now: datetime | None = None) -> Job | None:
    """Once a day, after HR_SNAPSHOT_HOUR (UTC), record every student's indices."""
    today = today or settings.today
    now = now or datetime.utcnow()
    if now.hour < settings.snapshot_hour and settings.pinned_today is None:
        return None
    with SessionLocal() as db:
        return enqueue(db, "snapshot", {"on": today.isoformat()}, unique_key=f"snapshot:{today.isoformat()}",
                       max_attempts=2)


def queue_status(db: Session) -> dict:
    """For readiness: how deep the queue is, and whether a worker has been seen lately."""
    queued = db.query(Job).filter(Job.status == "queued").count()
    running = db.query(Job).filter(Job.status == "running").count()
    latest = db.scalar(select(WorkerBeat).order_by(WorkerBeat.seen_at.desc()).limit(1))
    alive = latest is not None and latest.seen_at > datetime.utcnow() - _stale_after()
    return {"queued": queued, "running": running, "worker_seen": latest.seen_at.isoformat() if latest else None,
            "worker_alive": alive}
