"""DB-backed job queue: bounded retries with backoff, deferral, and recovery of stale running jobs."""

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_factory, utcnow
from app.models import Job
from app.providers.base import ProviderError, TransientProviderError

logger = logging.getLogger("maa.jobs")


def enqueue(db: Session, workspace_id: int, kind: str, ref_id: int, payload: dict | None = None) -> Job:
    existing = db.scalar(select(Job).where(Job.kind == kind, Job.ref_id == ref_id, Job.status.in_(["queued", "running"])))
    if existing:  # duplicate prevention
        return existing
    job = Job(workspace_id=workspace_id, kind=kind, ref_id=ref_id, payload=payload or {}, max_attempts=get_settings().job_max_attempts)
    db.add(job)
    db.flush()
    return job


def recover_stale(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    cutoff = now - timedelta(seconds=get_settings().job_stale_seconds)
    n = 0
    for j in db.scalars(select(Job).where(Job.status == "running", Job.locked_at < cutoff)):
        j.status, j.locked_at, j.last_error = "queued", None, "Recovered after worker interruption"
        n += 1
    return n


def _handler(kind: str):
    from app.graph.workflow import process_meeting
    from app.services import calendar_events, followups

    return {
        "process_meeting": lambda db, j: process_meeting(db, j.ref_id, j.payload),
        "send_followup": lambda db, j: followups.execute_followup(db, j.ref_id),
        "create_event": lambda db, j: calendar_events.execute(db, j.ref_id),
    }[kind]


def _fail_entity(db: Session, job: Job, error: str) -> None:
    from app.models import FollowUp, Meeting

    if job.kind == "process_meeting":
        m = db.get(Meeting, job.ref_id)
        if m and m.status not in ("review", "completed"):
            m.status, m.error = "failed", error
            m.stage_log = [*m.stage_log, {"stage": "failed", "at": utcnow().isoformat(), "detail": error}]
    elif job.kind == "send_followup":
        fu = db.get(FollowUp, job.ref_id)
        if fu and fu.status not in ("sent", "revoked", "expired", "rejected"):
            fu.status, fu.last_error = "failed", error


def run_pending(db: Session, limit: int = 10, now: datetime | None = None) -> dict:
    """Process due jobs once. Returns counters (used by the worker thread and by tests)."""
    from app.services import followups

    now = now or utcnow()
    db.expire_all()  # never act on stale cached rows
    stats = {"succeeded": 0, "retried": 0, "dead": 0, "deferred": 0}
    recover_stale(db, now)
    followups.expire_stale(db)
    db.commit()
    jobs = db.scalars(select(Job).where(Job.status == "queued", Job.next_run_at <= now).order_by(Job.id).limit(limit)).all()
    for job in jobs:
        db.expire_all()
        job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
        db.commit()
        try:
            _handler(job.kind)(db, job)
            job.status, job.last_error = "succeeded", ""
            stats["succeeded"] += 1
        except followups.Deferred as d:
            db.rollback()
            job = db.get(Job, job.id)
            job.status, job.attempts, job.next_run_at, job.last_error = "queued", max(job.attempts - 1, 0), d.until, d.why
            stats["deferred"] += 1
        except TransientProviderError as e:
            db.rollback()
            job = db.get(Job, job.id)
            job.last_error = str(e)
            if job.attempts >= job.max_attempts:
                job.status = "dead"
                _fail_entity(db, job, f"Gave up after {job.attempts} attempts: {e}")
                stats["dead"] += 1
            else:
                job.status = "queued"
                job.next_run_at = now + timedelta(seconds=get_settings().job_backoff_seconds * 2 ** (job.attempts - 1))
                stats["retried"] += 1
        except (ProviderError, ValueError) as e:  # permanent (includes RuleError)
            db.rollback()
            job = db.get(Job, job.id)
            job.status, job.last_error = "dead", str(e)
            _fail_entity(db, job, str(e))
            stats["dead"] += 1
        except Exception as e:  # noqa: BLE001 - never let one job kill the worker
            logger.exception("job crashed")
            db.rollback()
            job = db.get(Job, job.id)
            job.status, job.last_error = "dead", f"Unexpected error: {type(e).__name__}"
            _fail_entity(db, job, "Unexpected internal error")
            stats["dead"] += 1
        db.commit()
    return stats


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="maa-worker")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        interval = get_settings().worker_interval_seconds
        while not self._stop.wait(interval):
            db = session_factory()()
            try:
                run_pending(db)
            except Exception:  # noqa: BLE001
                logger.exception("worker tick failed")
            finally:
                db.close()
