"""L2 plan cache (design Q8, Q16): never invalidated by data updates."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.models import PlanCache


async def get(session: AsyncSession, request_key: str) -> PlanCache | None:
    row = await session.get(PlanCache, request_key)
    if row is not None:
        await session.execute(
            update(PlanCache)
            .where(PlanCache.request_key == request_key)
            .values(hit_count=PlanCache.hit_count + 1, last_used_at=datetime.now(UTC))
        )
    return row


async def put(
    session: AsyncSession,
    request_key: str,
    planner_version: str,
    plan: dict[str, Any],
    trace: dict[str, Any],
) -> None:
    await session.execute(
        insert(PlanCache)
        .values(
            request_key=request_key, planner_version=planner_version, plan=plan, planner_trace=trace
        )
        .on_conflict_do_nothing(index_elements=["request_key"])
    )
