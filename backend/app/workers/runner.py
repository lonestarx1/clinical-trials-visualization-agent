"""In-process background workers (design Q6): claim pending jobs with SKIP LOCKED and run them."""

import asyncio
import logging
import socket
import uuid
from datetime import timedelta
from typing import Any

from fastapi import FastAPI

from app.api.errors import error_body
from app.ctgov.client import CtgovUnavailable, InconsistentResults
from app.llm.client import LLMUnavailable, UsageLog
from app.pipeline.query import run_job
from app.store import jobs

log = logging.getLogger(__name__)
RETRYABLE = (CtgovUnavailable, InconsistentResults, LLMUnavailable)
POLL_SECONDS = 0.5


async def _process_one(app: FastAPI, worker_id: str) -> bool:
    """Claim and run one job. Returns False when there was nothing to do."""
    sessions = app.state.sessions
    async with sessions() as s:
        job = await jobs.claim_next(s, worker_id=worker_id)
        await s.commit()
    if job is None:
        return False
    try:
        llms = app.state.llm_factory(UsageLog())
        result_id = await run_job(
            job.job_id,
            sessions=sessions,
            ctgov=app.state.ctgov,
            llms=llms,
            settings=app.state.settings,
        )
    except Exception as exc:
        retry = isinstance(exc, RETRYABLE) and job.attempts < job.max_attempts
        log.exception("job %s failed (attempt %d, retry=%s)", job.job_id, job.attempts, retry)
        error: dict[str, Any] = error_body(exc, str(job.trace_id))
        async with sessions() as s:
            await jobs.fail(s, job.job_id, error=error, retry=retry)
            await s.commit()
        return True
    async with sessions() as s:
        await jobs.succeed(s, job.job_id, result_id=result_id)
        await s.commit()
    return True


async def worker_loop(app: FastAPI, index: int) -> None:
    worker_id = f"{socket.gethostname()}-{index}-{uuid.uuid4().hex[:6]}"
    while True:
        try:
            if not await _process_one(app, worker_id):
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the worker alive (e.g. database briefly down)
            log.exception("worker %s error", worker_id)
            await asyncio.sleep(2)


async def requeue_stale(app: FastAPI) -> None:
    async with app.state.sessions() as s:
        count = await jobs.requeue_stale(s, older_than=timedelta(minutes=2))
        await s.commit()
    if count:
        log.warning("requeued %d jobs left running by a previous process", count)
