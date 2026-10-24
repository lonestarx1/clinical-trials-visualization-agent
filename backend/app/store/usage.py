"""LLM usage rows and the daily budget (design Q16, section 10)."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import UsageLog
from app.store.models import LlmUsage


async def record(
    session: AsyncSession,
    log: UsageLog,
    *,
    trace_id: uuid.UUID | None,
    job_id: uuid.UUID | None,
    price_version: str,
) -> None:
    if not log.calls:
        return
    await session.execute(
        insert(LlmUsage),
        [
            {
                "call_id": uuid.uuid4(),
                "trace_id": trace_id,
                "job_id": job_id,
                "stage": c.stage,
                "model": c.model,
                "is_fallback": c.fallback,
                "input_tokens": c.input_tokens,
                "cached_input_tokens": c.cached_tokens,
                "output_tokens": c.output_tokens,
                "reasoning_tokens": c.reasoning_tokens,
                "latency_ms": c.latency_ms,
                "cost_usd": None if c.cost_usd is None else Decimal(str(round(c.cost_usd, 6))),
                "price_version": price_version,
            }
            for c in log.calls
        ],
    )


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def spent_today(session: AsyncSession) -> Decimal:
    start, end = _day_bounds(datetime.now(UTC).date())
    total = await session.scalar(
        select(func.coalesce(func.sum(LlmUsage.cost_usd), 0)).where(
            LlmUsage.created_at >= start, LlmUsage.created_at < end
        )
    )
    return Decimal(total or 0)


async def summary(session: AsyncSession, *, day: date) -> dict[str, Any]:
    start, end = _day_bounds(day)
    rows = (
        await session.scalars(
            select(LlmUsage).where(LlmUsage.created_at >= start, LlmUsage.created_at < end)
        )
    ).all()
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0})
    for r in rows:
        by_model[r.model]["calls"] += 1
        by_model[r.model]["cost_usd"] += float(r.cost_usd or 0)
    return {
        "day": day.isoformat(),
        "calls": len(rows),
        "cost_usd": round(sum(float(r.cost_usd or 0) for r in rows), 6),
        "unknown_cost_calls": sum(1 for r in rows if r.cost_usd is None),
        "fallback_calls": sum(1 for r in rows if r.is_fallback),
        "by_model": dict(by_model),
    }
