"""In-process background workers (design Q6): claim pending jobs with SKIP LOCKED and run them."""

import asyncio
import logging
import socket
import time
import uuid
from contextlib import suppress
from datetime import timedelta
from typing import Any

from fastapi import FastAPI

from app.api.errors import error_body
from app.ctgov.client import CtgovUnavailable, InconsistentResults
from app.llm.client import LLMUnavailable, UsageLog
from app.pipeline.query import JobCancelled, run_job
from app.store import jobs

log = logging.getLogger(__name__)
RETRYABLE = (CtgovUnavailable, InconsistentResults, LLMUnavailable)
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 30.0  # a running job's heartbeat, whatever stage it is in
REQUEUE_SECONDS = 60.0  # how often worker 0 looks for jobs whose worker stopped beating
STALE_AFTER = timedelta(minutes=2)


async def _beat(app: FastAPI, job_id: uuid.UUID) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            async with app.state.sessions() as s:
                await jobs.heartbeat(s, job_id)
                await s.commit()
        except Exception:  # a missed beat is not fatal; the next one may succeed
            log.warning("heartbeat for job %s failed", job_id, exc_info=True)


async def _process_one(app: FastAPI, worker_id: str) -> bool:
    """Claim and run one job. Returns False when there was nothing to do."""
    sessions = app.state.sessions
    async with sessions() as s:
        job = await jobs.claim_next(s, worker_id=worker_id)
        await s.commit()
    if job is None:
        return False
    beat = asyncio.create_task(_beat(app, job.job_id))
    try:
        llms = app.state.llm_factory(UsageLog())
        result_id = await run_job(
            job.job_id,
            sessions=sessions,
            ctgov=app.state.ctgov,
            llms=llms,
            settings=app.state.settings,
        )
    except JobCancelled:
        # DELETE /v1/jobs/{id} already wrote `cancelled`: not failed, not retried.
        log.info("job %s cancelled; stopped", job.job_id)
        return True
    except Exception as exc:
        retry = isinstance(exc, RETRYABLE) and job.attempts < job.max_attempts
        log.exception("job %s failed (attempt %d, retry=%s)", job.job_id, job.attempts, retry)
        error: dict[str, Any] = error_body(exc, str(job.trace_id))
        async with sessions() as s:
            await jobs.fail(s, job.job_id, error=error, retry=retry)
            await s.commit()
        return True
    finally:
        beat.cancel()
        with suppress(asyncio.CancelledError):
            await beat
    async with sessions() as s:
        if not await jobs.succeed(s, job.job_id, result_id=result_id):
            log.info("job %s was cancelled as it finished; its answer is kept", job.job_id)
        await s.commit()
    return True


async def worker_loop(app: FastAPI, index: int) -> None:
    worker_id = f"{socket.gethostname()}-{index}-{uuid.uuid4().hex[:6]}"
    next_requeue = time.monotonic() + REQUEUE_SECONDS
    while True:
        try:
            if index == 0 and time.monotonic() >= next_requeue:
                await requeue_stale(app)
                next_requeue = time.monotonic() + REQUEUE_SECONDS
            if not await _process_one(app, worker_id):
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the worker alive (e.g. database briefly down)
            log.exception("worker %s error", worker_id)
            await asyncio.sleep(2)


async def requeue_stale(app: FastAPI) -> None:
    async with app.state.sessions() as s:
        count = await jobs.requeue_stale(s, older_than=STALE_AFTER)
        await s.commit()
    if count:
        log.warning("requeued %d jobs whose worker stopped sending heartbeats", count)
