"""The mirror's sync loop (design Q22), in the API process so it shares the rate limiter.

Every 10 minutes it asks whether ClinicalTrials.gov has new data and, if so, syncs. A Postgres
advisory lock keeps it to one sync at a time, even while a rolling update runs two pods.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ctgov.client import CtgovClient
from app.mirror.sync import SyncResult, sync
from app.store import mirror

log = logging.getLogger(__name__)
CHECK_SECONDS = 600
RETRY_SECONDS = (60, 300, 900, 1800, 3600)  # after the 1st, 2nd, ... failure in a row
BEHIND_AFTER = timedelta(hours=3)


@dataclass
class LoopState:
    failures: int = 0
    failing_since: datetime | None = None
    reported: bool = False


async def sync_with_lock(
    engine: AsyncEngine, ctgov: CtgovClient, sessions: async_sessionmaker[AsyncSession]
) -> SyncResult | None:
    async with engine.connect() as conn:
        if not await mirror.try_lock(conn):
            log.info("another process is syncing the mirror")
            return None
        try:
            return await sync(ctgov, sessions)
        finally:
            await mirror.unlock(conn)


async def tick(
    engine: AsyncEngine,
    ctgov: CtgovClient,
    sessions: async_sessionmaker[AsyncSession],
    state: LoopState,
    now: datetime,
) -> float:
    """One check, and a sync when there is new data. Returns the seconds to wait."""
    try:
        result = await sync_with_lock(engine, ctgov, sessions)
    except Exception:
        state.failures += 1
        state.failing_since = state.failing_since or now
        log.exception("mirror sync failed (%d in a row)", state.failures)
        if now - state.failing_since >= BEHIND_AFTER and not state.reported:
            state.reported = True
            log.error("the mirror is behind: no successful sync since %s", state.failing_since)
        return RETRY_SECONDS[min(state.failures, len(RETRY_SECONDS)) - 1]
    if result is not None:
        log.info(
            "mirror %s done: data %s, %d trials saved, %d removed",
            result.kind,
            result.data_timestamp,
            result.upserted,
            result.removed,
        )
    state.failures, state.failing_since, state.reported = 0, None, False
    return CHECK_SECONDS


async def mirror_loop(app: FastAPI) -> None:
    state = LoopState()
    while True:
        delay = await tick(
            app.state.engine, app.state.mirror_ctgov, app.state.sessions, state, datetime.now(UTC)
        )
        await asyncio.sleep(delay)
