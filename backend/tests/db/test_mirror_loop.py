"""The mirror's sync loop (design Q22): one sync at a time, backoff, and an error when behind."""

import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.store import mirror
from app.store.db import create_engine
from app.workers.mirror import CHECK_SECONDS, LoopState, tick
from tests.support.fake_registry import FakeRegistry, registry_client, trial

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]
T0 = datetime(2026, 10, 25, 10, 0, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(os.environ["DATABASE_URL"])
    yield engine
    await engine.dispose()


def fake() -> FakeRegistry:
    return FakeRegistry([trial("NCT1"), trial("NCT2", None)], "2026-10-23T09:00:04")


async def test_a_tick_syncs_then_waits_the_check_interval(
    engine: AsyncEngine, sessions: Sessions
) -> None:
    client, _ = registry_client(fake())
    state = LoopState()
    assert await tick(engine, client, sessions, state, T0) == CHECK_SECONDS == 600
    async with sessions() as s:
        assert await mirror.count_trials(s) == 2


async def test_a_tick_skips_while_another_pod_holds_the_lock(
    engine: AsyncEngine, sessions: Sessions
) -> None:
    client, transport = registry_client(fake())
    async with engine.connect() as other:
        assert await mirror.try_lock(other)
        assert await tick(engine, client, sessions, LoopState(), T0) == CHECK_SECONDS
        await mirror.unlock(other)
    assert transport.requests == []


async def test_failures_back_off_and_log_an_error_after_three_hours(
    engine: AsyncEngine, sessions: Sessions, caplog: pytest.LogCaptureFixture
) -> None:
    registry = fake()
    registry.fail_after = 0
    client, _ = registry_client(registry)
    state = LoopState()
    delays = []
    for minutes in (0, 1, 6, 21, 51, 111, 171, 231):
        delays.append(await tick(engine, client, sessions, state, T0 + timedelta(minutes=minutes)))
    assert delays == [60, 300, 900, 1800, 3600, 3600, 3600, 3600]
    behind = [
        r for r in caplog.records if r.levelno == logging.ERROR and "behind" in r.getMessage()
    ]
    assert len(behind) == 1  # once, when the third hour passed

    registry.fail_after = None
    assert await tick(engine, client, sessions, state, T0 + timedelta(hours=5)) == CHECK_SECONDS
    assert (state.failures, state.failing_since) == (0, None)
