"""Background job worker.

Runs inside the API process (INLINE_WORKER=true, default) or standalone:
    python -m app.worker
Several standalone workers can run at once; jobs are claimed atomically.
No Redis/Celery needed for the local zero-cost setup.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update

from .config import get_settings
from .db import init_db, session_scope
from .models import ErrorLog, Job, Project
from .providers.manager import AllProvidersExhausted
from .services.pipeline import AwaitingApproval, Cancelled, Pipeline

log = logging.getLogger("worker")
HEARTBEAT = {"t": 0.0}  # last time the in-process worker loop ran (seconds since epoch)


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def recover_stale_jobs() -> int:
    """Jobs left 'running' by a crash/restart go back to the queue (they resume, not restart)."""
    with session_scope() as db:
        res = db.execute(update(Job).where(Job.status == "running").values(status="queued", message="resumed after restart"))
        return res.rowcount or 0


def claim_next() -> str | None:
    with session_scope() as db:
        now = _now()
        candidates = db.query(Job).filter(or_(Job.status == "queued", Job.status == "paused")).order_by(Job.created_at).all()
        for job in candidates:
            if job.status == "paused" and (job.resume_after is None or _aware(job.resume_after) > now):
                continue  # paused without a retry time waits for the user
            # one active job per project
            busy = db.query(Job).filter(Job.project_id == job.project_id, Job.status == "running").first()
            if busy:
                continue
            res = db.execute(update(Job).where(Job.id == job.id, Job.status == job.status).values(status="running", updated_at=now))
            if res.rowcount == 1:
                if job.started_at is None:
                    db.execute(update(Job).where(Job.id == job.id).values(started_at=now))
                return job.id
    return None


def run_job(job_id: str) -> str:
    s = get_settings()
    try:
        Pipeline(job_id).run()
    except Cancelled:
        _finish(job_id, "cancelled", "Cancelled by user. Finished work is kept; resume any time.")
        _project_status(job_id, "cancelled")
        return "cancelled"
    except AwaitingApproval:
        _finish(job_id, "awaiting_approval", "Story and characters are ready. Review them, then approve to continue.")
        return "awaiting_approval"
    except AllProvidersExhausted as e:
        when = _now() + timedelta(seconds=e.retry_after_s) if e.retry_after_s else None
        msg = (f"Paused: {e}. " + (f"Will retry automatically at {when.strftime('%H:%M UTC')}." if when
                                   else "Start or configure a free provider, then press Resume."))
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.status, job.message, job.resume_after = "paused", msg, when
            db.add(ErrorLog(project_id=job.project_id, job_id=job_id, where=f"providers:{e.kind}", message=str(e)))
        _project_status(job_id, "paused")
        return "paused"
    except Exception as e:
        log.exception("job %s failed", job_id)
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.attempts += 1
            db.add(ErrorLog(project_id=job.project_id, job_id=job_id, where="pipeline", message=traceback.format_exc()[-4000:]))
            if job.attempts <= s.max_retries:
                job.status, job.resume_after = "paused", _now() + timedelta(seconds=20 * job.attempts)
                job.message = f"Error: {e}. Retrying automatically (attempt {job.attempts + 1}/{s.max_retries + 1})."
                return "retrying"
            job.status, job.message, job.finished_at = "failed", f"Failed: {e}", _now()
            job.progress = min(job.progress, 99.0)
        _project_status(job_id, "failed")
        return "failed"
    with session_scope() as db:
        has_video = bool(db.get(Project, db.get(Job, job_id).project_id).final_video)
    if not has_video:
        _finish(job_id, "failed", "Failed: rendering finished without a validated MP4.")
        _project_status(job_id, "failed")
        return "failed"
    with session_scope() as db:
        job = db.get(Job, job_id)
        took = (_now() - _aware(job.started_at)).total_seconds() if job.started_at else None
    _finish(job_id, "completed", f"Video ready in {took / 60:.1f} min." if took else "Video ready.", progress=100.0)
    return "completed"


def _finish(job_id: str, status: str, msg: str, progress: float | None = None):
    with session_scope() as db:
        job = db.get(Job, job_id)
        job.status, job.message = status, msg
        if status in ("completed", "failed", "cancelled"):
            job.finished_at = _now()
        if progress is not None:
            job.progress = progress


def _project_status(job_id: str, status: str):
    with session_scope() as db:
        job = db.get(Job, job_id)
        db.get(Project, job.project_id).status = status


class Worker:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        recover_stale_jobs()
        self._thread = threading.Thread(target=self.loop, name="engine-worker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def loop(self):
        poll = get_settings().worker_poll_s
        while not self._stop.is_set():
            HEARTBEAT["t"] = time.time()
            try:
                job_id = claim_next()
                if job_id:
                    run_job(job_id)
                    continue
            except Exception:
                log.exception("worker loop error")
            self._stop.wait(poll)


def main():  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    w = Worker()
    recover_stale_jobs()
    log.info("worker started")
    try:
        w.loop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":  # pragma: no cover
    main()
