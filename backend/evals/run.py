"""Run the AI evaluation set against the real OpenAI API (design Q18, Q20). Opt-in: it costs money.

    uv run python -m evals.run                         # the configured models, 1 run per case
    uv run python -m evals.run --runs 3 --label baseline
    uv run python -m evals.run --stages planner --model planner=gpt-5.4:low
    uv run python -m evals.run --bakeoff --runs 3      # Q20's candidates for every stage

Each stage runs on its own: the planner gets live ClinicalTrials.gov counts, the narrator gets
fact sheets from live results. Fallback models are off, so a score belongs to one model.
Writes docs/eval/<label>.md and docs/eval/results/<label>.json.
"""

import argparse
import asyncio
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from openai import AsyncOpenAI

from app.agents.guard import SafetyCheckUnavailable, check_request
from app.agents.narrator import Narration, narrate
from app.agents.planner import plan_request
from app.core.config import Settings, StageSettings
from app.core.pricing import load_pricing
from app.ctgov.client import CtgovClient, RateLimiter
from app.llm.client import LLM, OpenAILLM, UsageLog
from app.pipeline.charts import ChartMeta
from app.pipeline.run import run_plan
from app.schemas.plan import QueryPlan
from app.schemas.request import QueryRequest
from app.schemas.response import Visualization
from evals.cases import (
    GuardCase,
    NarratorCase,
    PlannerCase,
    load_guard_cases,
    load_narrator_cases,
    load_planner_cases,
)
from evals.report import render
from evals.scoring import (
    GuardRun,
    NarratorRun,
    PlannerRun,
    guard_summary,
    narrator_summary,
    planner_summary,
    score_plan,
)

log = logging.getLogger("evals")
STAGES = ("guard", "planner", "narrator")
# Design Q20's candidates, as model[:reasoning effort].
CANDIDATES = {
    "guard": ["gpt-5.4-nano:low", "gpt-4o-mini", "gpt-4.1-mini"],
    "planner": [
        "gpt-5.4-mini:low",
        "gpt-5.4-mini:medium",
        "gpt-5.4:low",
        "gpt-5-mini:low",
        "gpt-4.1-mini",
    ],
    "narrator": ["gpt-5.4-nano:low", "gpt-4o-mini", "gpt-4.1-mini"],
}
DOCS = Path(__file__).resolve().parents[2] / "docs" / "eval"


class MeteredLLM(LLM, Protocol):
    usage: UsageLog


Factory = Callable[[], MeteredLLM]
Facts = tuple[QueryPlan, Visualization, ChartMeta]


def _cost(llm: MeteredLLM) -> float | None:
    costs = [c.cost_usd for c in llm.usage.calls]
    return None if None in costs else round(sum(c for c in costs if c is not None), 6)


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


async def run_guard(
    cases: Sequence[GuardCase], make: Factory, *, runs: int, sem: asyncio.Semaphore
) -> list[GuardRun]:
    async def one(case: GuardCase, run: int) -> GuardRun:
        async with sem:
            llm, start = make(), time.perf_counter()
            try:
                verdict: str = (
                    await check_request(llm, QueryRequest.model_validate(case.request))
                ).verdict
            except SafetyCheckUnavailable:
                verdict = "error"
            return GuardRun(case.id, run, case.expected, verdict, _ms(start), _cost(llm))

    return list(await asyncio.gather(*(one(c, r) for c in cases for r in range(1, runs + 1))))


async def run_planner(
    cases: Sequence[PlannerCase],
    make: Factory,
    ctgov: CtgovClient,
    *,
    max_steps: int,
    runs: int,
    sem: asyncio.Semaphore,
) -> list[PlannerRun]:
    async def one(case: PlannerCase, run: int) -> PlannerRun:
        async with sem:
            llm, start = make(), time.perf_counter()
            request = QueryRequest.model_validate(case.request)
            try:
                result = await plan_request(llm, request, ctgov, max_steps=max_steps)
            except Exception:
                log.exception("planner failed on %s", case.id)
                return PlannerRun(
                    case.id,
                    run,
                    score_plan(case.expect, None),
                    False,
                    False,
                    0,
                    _ms(start),
                    _cost(llm),
                )
            plan = result.plan.model_dump(mode="json") if result.plan else None
            submits = [c for c in result.tool_calls if c["tool"] == "submit_plan"]
            return PlannerRun(
                case.id,
                run,
                score_plan(case.expect, plan),
                plan is not None,
                bool(submits) and bool(submits[0]["ok"]),
                result.steps,
                _ms(start),
                _cost(llm),
            )

    return list(await asyncio.gather(*(one(c, r) for c in cases for r in range(1, runs + 1))))


async def fact_sheets(
    cases: Sequence[NarratorCase], ctgov: CtgovClient, base_url: str
) -> dict[str, Facts]:
    """Each narrator case's plan run once on live data; what the narrator would be given."""
    sheets: dict[str, Facts] = {}
    for case in cases:

        async def capture(
            plan: QueryPlan, viz: Visualization, meta: ChartMeta, case_id: str = case.id
        ) -> Narration:
            sheets[case_id] = (plan, viz, meta)
            return Narration(viz.title, None, 1, False)

        await run_plan(
            QueryPlan.model_validate(case.plan), ctgov, base_url=base_url, narrator=capture
        )
        if case.id not in sheets:
            log.warning("%s gave no chart to narrate; skipped", case.id)
    return sheets


async def run_narrator(
    sheets: dict[str, Facts], make: Factory, *, runs: int, sem: asyncio.Semaphore
) -> list[NarratorRun]:
    async def one(case_id: str, facts: Facts, run: int) -> NarratorRun:
        async with sem:
            llm, start = make(), time.perf_counter()
            out = await narrate(llm, *facts)
            return NarratorRun(
                case_id, run, out.title, out.attempts, out.fallback, _ms(start), _cost(llm)
            )

    return list(
        await asyncio.gather(*(one(i, f, r) for i, f in sheets.items() for r in range(1, runs + 1)))
    )


def _stage_settings(base: StageSettings, candidate: str) -> StageSettings:
    model, _, effort = candidate.partition(":")
    update: dict[str, Any] = {"model": model, "fallback_model": None}
    if effort:
        update["reasoning_effort"] = effort
    return base.model_copy(update=update)


def _configured(settings: Settings, stage: str) -> str:
    s: StageSettings = getattr(settings, stage)
    return f"{s.model}:{s.reasoning_effort}"


async def main(args: argparse.Namespace) -> Path:
    settings = Settings()
    pricing = load_pricing()
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    ctgov = CtgovClient(
        settings.ctgov_base_url,
        http,
        RateLimiter(
            settings.ctgov_rate_limit_per_min,
            settings.ctgov_max_concurrency,
            burst=settings.ctgov_rate_burst,
        ),
        count_ttl=settings.ctgov_count_cache_seconds,
    )
    overrides = dict(m.split("=", 1) for m in args.model)
    stages = [s for s in args.stages.split(",") if s]
    sem = asyncio.Semaphore(args.concurrency)

    def factory(stage: str, candidate: str) -> Factory:
        stage_settings = _stage_settings(getattr(settings, stage), candidate)
        return lambda: OpenAILLM(
            client, stage_settings, stage=stage, pricing=pricing, usage=UsageLog()
        )

    sheets: dict[str, Facts] = {}
    if "narrator" in stages:
        sheets = await fact_sheets(load_narrator_cases(), ctgov, settings.ctgov_base_url)
    result: dict[str, Any] = {
        "label": args.label,
        "date": datetime.now().astimezone().date().isoformat(),
        "runs_per_case": args.runs,
        "cases": {},
        "stages": {},
    }
    for stage in stages:
        candidates = (
            CANDIDATES[stage]
            if args.bakeoff
            else [overrides.get(stage) or _configured(settings, stage)]
        )
        result["stages"][stage] = {}
        for candidate in candidates:
            make = factory(stage, candidate)
            log.info("running %s with %s", stage, candidate)
            summary: dict[str, Any]
            runs: Sequence[Any]
            if stage == "guard":
                cases_g = load_guard_cases()
                runs = await run_guard(cases_g, make, runs=args.runs, sem=sem)
                summary, result["cases"]["guard"] = guard_summary(runs), len(cases_g)
            elif stage == "planner":
                cases_p = load_planner_cases()
                runs = await run_planner(
                    cases_p,
                    make,
                    ctgov,
                    max_steps=settings.planner.max_steps,
                    runs=args.runs,
                    sem=sem,
                )
                summary, result["cases"]["planner"] = planner_summary(runs), len(cases_p)
            else:
                runs = await run_narrator(sheets, make, runs=args.runs, sem=sem)
                summary, result["cases"]["narrator"] = narrator_summary(runs), len(sheets)
            costs: list[float | None] = [r.cost_usd for r in runs]
            known = [c for c in costs if c is not None]
            result["stages"][stage][candidate] = {
                "summary": summary,
                "total_cost_usd": None if len(known) < len(costs) else round(sum(known), 6),
                "runs": [asdict(r) for r in runs],
            }
    await http.aclose()
    out = Path(args.out)
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "results" / f"{args.label}.json").write_text(json.dumps(result, indent=2) + "\n")
    report = out / f"{args.label}.md"
    report.write_text(render(result))
    return report


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stages", default=",".join(STAGES), help="comma-separated")
    parser.add_argument("--runs", type=int, default=1, help="runs per case (Q20: 3)")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="stage=model[:effort], e.g. planner=gpt-5.4:low",
    )
    parser.add_argument("--bakeoff", action="store_true", help="every Q20 candidate per stage")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--label", default="eval")
    parser.add_argument("--out", default=str(DOCS))
    return parser.parse_args(argv)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    print(asyncio.run(main(parse())))
