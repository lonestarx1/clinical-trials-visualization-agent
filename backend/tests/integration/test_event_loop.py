"""Building a large chart must not block the event loop: other requests keep being served."""

import asyncio
import time
from typing import Any

import pytest

from app.pipeline import run
from app.pipeline.run import run_plan
from app.schemas.plan import QueryPlan
from tests.support.recorded_api import BASE, recorded_client

PLAN = QueryPlan.model_validate(
    {"scope": "in_scope", "intent": "distribution", "chart_type": "bar_chart", "dimension": "phase"}
)


async def test_other_work_runs_while_a_chart_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    real = run.build_chart

    def slow_build_chart(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.5)  # stands in for aggregating hundreds of thousands of trials
        return real(*args, **kwargs)

    monkeypatch.setattr(run, "build_chart", slow_build_chart)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    client, _ = recorded_client()
    other = asyncio.create_task(ticker())
    try:
        response = await run_plan(PLAN, client, base_url=BASE)
    finally:
        other.cancel()
    assert response.status == "ok"
    assert ticks >= 10, f"the event loop was blocked: only {ticks} ticks in 0.5 s"
