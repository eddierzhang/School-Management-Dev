"""The database job queue and the worker that runs it."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app import jobs
from app.db import SessionLocal
from app.models import AgentRun, Job, StudentSnapshot, WorkerBeat


@pytest.fixture
def queue(monkeypatch):
    """A clean queue with a recording handler; every job made here is removed afterwards."""
    with SessionLocal() as s:
        before = s.scalar(select(func.max(Job.id))) or 0
        # Set aside anything other tests left queued, so only this test's jobs run.
        parked = [j.id for j in s.scalars(select(Job).where(Job.status.in_(["queued", "running"]))).all()]
        for j in s.scalars(select(Job).where(Job.id.in_(parked))).all():
            j.status = "parked"
        s.commit()
    calls: list[dict] = []
    monkeypatch.setitem(jobs.HANDLERS, "test", lambda payload: calls.append(payload))
    monkeypatch.setattr(jobs, "RETRY_BACKOFF", 0)
    yield calls
    with SessionLocal() as s:
        s.execute(delete(Job).where(Job.id > before))
        for j in s.scalars(select(Job).where(Job.id.in_(parked))).all():
            j.status = "queued"
        s.execute(delete(WorkerBeat))
        s.commit()


def test_a_job_runs_once_and_is_marked_done(queue):
    with SessionLocal() as s:
        job = jobs.enqueue(s, "test", {"n": 1})
    assert jobs.run_pending("w1") == 1
    assert queue == [{"n": 1}]
    with SessionLocal() as s:
        done = s.get(Job, job.id)
        assert (done.status, done.attempts, done.locked_by) == ("done", 1, "w1")
    assert jobs.run_once("w1") is False


def test_a_failing_job_is_retried_then_given_up(queue, monkeypatch):
    def boom(payload):
        raise RuntimeError("model fell over")
    monkeypatch.setitem(jobs.HANDLERS, "test", boom)
    with SessionLocal() as s:
        job = jobs.enqueue(s, "test", {}, max_attempts=2)
    jobs.run_once()
    with SessionLocal() as s:
        assert s.get(Job, job.id).status == "queued" and "model fell over" in s.get(Job, job.id).error
    jobs.run_once()
    with SessionLocal() as s:
        assert s.get(Job, job.id).status == "failed"


def test_giving_up_on_an_agent_run_marks_the_run_failed(queue, monkeypatch):
    def boom(payload):
        raise RuntimeError("worker could not start the model")
    monkeypatch.setitem(jobs.HANDLERS, "agent_run", boom)
    with SessionLocal() as s:
        run = AgentRun(agent="support", model="m", prompt="p", status="queued", transcript=[])
        s.add(run); s.commit()
        jobs.enqueue(s, "agent_run", {"run_id": run.id, "agent": "support", "task": "p"}, max_attempts=1)
        run_id = run.id
    jobs.run_once()
    with SessionLocal() as s:
        run = s.get(AgentRun, run_id)
        assert run.status == "failed" and "could not start the model" in run.error
        s.delete(run); s.commit()


def test_a_unique_job_is_enqueued_once(queue):
    with SessionLocal() as s:
        assert jobs.enqueue(s, "test", {}, unique_key="once:today") is not None
        assert jobs.enqueue(s, "test", {}, unique_key="once:today") is None
        assert s.scalar(select(func.count()).select_from(Job).where(Job.unique_key == "once:today")) == 1


def test_only_one_model_bound_job_runs_at_a_time(queue):
    with SessionLocal() as s:
        first = jobs.enqueue(s, "document_analysis", {"doc_id": -1})
        jobs.enqueue(s, "agent_run", {"run_id": -1, "agent": "support", "task": "x"})
        light = jobs.enqueue(s, "test", {})
        claimed = jobs._claim(s, "w1")
        assert claimed.id == first.id
        # With a model job running, the next claim skips the other model job for the light one.
        assert jobs._claim(s, "w2").id == light.id
        assert jobs._claim(s, "w3") is None


def test_a_job_whose_worker_died_goes_back_on_the_queue(queue):
    with SessionLocal() as s:
        job = jobs.enqueue(s, "test", {})
        jobs._claim(s, "dead-worker")
        s.get(Job, job.id).heartbeat_at = datetime.utcnow() - timedelta(minutes=10)
        s.commit()
    assert jobs.reap_stale() == 1
    with SessionLocal() as s:
        j = s.get(Job, job.id)
        assert j.status == "queued" and "stopped responding" in j.error
    assert jobs.run_pending("w2") == 1 and queue == [{}]


def test_the_daily_snapshot_is_scheduled_once(queue, monkeypatch):
    day = date(2026, 9, 12)
    assert jobs.schedule_daily(day) is not None
    assert jobs.schedule_daily(day) is None
    with SessionLocal() as s:
        before = s.scalar(select(func.count()).select_from(StudentSnapshot).where(StudentSnapshot.taken_on == day))
    assert jobs.run_pending() == 1
    with SessionLocal() as s:
        after = s.scalar(select(func.count()).select_from(StudentSnapshot).where(StudentSnapshot.taken_on == day))
    assert after == before > 0, "the day was retaken in place, not duplicated"


def test_the_agent_run_handler_starts_the_run_with_its_scope(queue, monkeypatch):
    seen = {}
    import app.ai.runner as runner

    monkeypatch.setattr(runner, "run_in_background", lambda run_id, agent, task, opening=None, scope=None:
                        seen.update(run_id=run_id, opening=opening, scope=scope))
    with SessionLocal() as s:
        run = AgentRun(agent="classes", model="m", prompt="p", status="queued", transcript=[])
        s.add(run); s.commit()
        jobs.enqueue(s, "agent_run", {"run_id": run.id, "agent": "classes", "task": "p",
                                      "opening": ["get_class_performance", {"course_code": "MAT-150"}],
                                      "scope": {"only_course": "MAT-150"}})
        run_id = run.id
    jobs.run_pending()
    assert seen == {"run_id": run_id, "opening": ("get_class_performance", {"course_code": "MAT-150"}),
                    "scope": {"only_course": "MAT-150"}}
    with SessionLocal() as s:
        assert s.get(AgentRun, run_id).status == "running"
        s.delete(s.get(AgentRun, run_id)); s.commit()


def test_the_worker_drains_and_readiness_reports_it(queue, client):
    from app.worker import main

    with SessionLocal() as s:
        jobs.enqueue(s, "test", {"from": "drain"})
    assert main(["--drain"]) == 0
    assert queue == [{"from": "drain"}]
    with SessionLocal() as s:
        jobs.beat(s, "probe")
    worker = client.get("/api/ready").json()["checks"]["worker"]
    assert worker["required"] is False and worker["worker_alive"] is True
