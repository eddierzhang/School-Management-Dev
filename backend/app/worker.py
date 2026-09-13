"""The worker: runs background jobs one at a time.

    python -m app.worker            run until stopped (SIGTERM or Ctrl-C finishes the current job first)
    python -m app.worker --drain    run what is queued now, then exit

Each loop it puts back jobs whose worker died, enqueues the day's history
snapshot once it is due, and claims the next job. Run one worker per Ollama
host: model-bound jobs are claimed only while no other is running.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import time

from . import jobs
from .config import get_settings
from .db import SessionLocal, schema_status
from .observability import configure

log = logging.getLogger("halverson.worker")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.worker", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drain", action="store_true", help="run the queued jobs, then exit")
    args = ap.parse_args(argv)

    configure("worker")
    settings = get_settings()
    problems = settings.production_problems()
    if problems:
        log.error("Refusing to start in production: %s", "; ".join(problems))
        return 2
    status = schema_status()
    if not status["up_to_date"]:
        log.error("Database schema is at %s, the code expects %s. Run `alembic upgrade head`.",
                  status["current"], status["head"])
        return 2

    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    if args.drain:
        jobs.reap_stale()
        ran = jobs.run_pending(worker_id, limit=10_000)
        log.info("drained %s job(s)", ran)
        return 0

    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        log.info("stopping after the current job")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker %s started", worker_id)
    last_housekeeping = 0.0
    while not stopping:
        try:
            if time.monotonic() - last_housekeeping > 30:
                jobs.reap_stale()
                jobs.schedule_daily()
                with SessionLocal() as db:
                    jobs.beat(db, worker_id)
                last_housekeeping = time.monotonic()
            if not jobs.run_once(worker_id):
                time.sleep(settings.worker_poll_seconds)
        except Exception:
            log.exception("worker loop error; retrying shortly")
            time.sleep(5)
    log.info("worker %s stopped", worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
