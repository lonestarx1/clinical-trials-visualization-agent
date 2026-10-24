"""Planning agent (design Q3): bounded tool loop, gate on every submission."""

import json
from typing import Any

import pytest

from app.agents.planner import plan_request
from app.ctgov.compiler import Search
from app.llm.client import LLMUnavailable
from app.schemas.request import QueryRequest
from tests.support.fake_llm import ScriptedLLM, calls, text

GOOD = {
    "scope": "in_scope",
    "intent": "distribution",
    "chart_type": "bar_chart",
    "filters": {"conditions": ["breast cancer"]},
    "dimension": "phase",
}
REQUEST = QueryRequest(query="How are breast cancer trials distributed across phases?")


class FakeCounter:
    def __init__(self, count: int = 2652) -> None:
        self.n, self.searches = count, []

    async def count(self, search: Search) -> int:
        self.searches.append(search)
        return self.n


def outputs(llm: ScriptedLLM, request_index: int) -> list[dict[str, Any]]:
    """Tool results the agent saw on a given turn."""
    items = llm.requests[request_index]["items"]
    return [json.loads(i["output"]) for i in items if i.get("type") == "function_call_output"]


async def test_a_valid_plan_on_the_first_turn() -> None:
    llm = ScriptedLLM(calls(("submit_plan", {"plan": GOOD})))
    result = await plan_request(llm, REQUEST, FakeCounter(), max_steps=6)
    assert result.plan is not None and result.plan.dimension == "phase"
    assert result.steps == 1
    assert [c["tool"] for c in result.tool_calls] == ["submit_plan"]
    tools = {t["name"] for t in llm.requests[0]["tools"]}
    assert tools == {"list_options", "count_trials", "check_plan", "submit_plan"}


async def test_count_trials_runs_a_real_count() -> None:
    counter = FakeCounter(2652)
    llm = ScriptedLLM(
        calls(("count_trials", {"filters": {"drugs": ["keytruda"]}})),
        calls(("submit_plan", {"plan": GOOD})),
    )
    result = await plan_request(llm, REQUEST, counter, max_steps=6)
    assert counter.searches[0].params == {
        "filter.advanced": 'AREA[InterventionNameSearch]"keytruda"'
    }
    assert outputs(llm, 1) == [{"count": 2652}]
    assert result.steps == 2


async def test_gate_errors_go_back_to_the_agent() -> None:
    bad = GOOD | {"filters": {"conditions": ["breast cancer"], "drugs": ["trastuzumab"]}}
    llm = ScriptedLLM(calls(("submit_plan", {"plan": bad})), calls(("submit_plan", {"plan": GOOD})))
    result = await plan_request(llm, REQUEST, FakeCounter(), max_steps=6)
    assert result.plan is not None
    [feedback] = outputs(llm, 1)
    assert feedback["accepted"] is False
    assert any("trastuzumab" in e for e in feedback["errors"])
    first = result.tool_calls[0]
    assert (first["tool"], first["ok"]) == ("submit_plan", False)
    assert any("trastuzumab" in e for e in first["errors"])  # kept in the trace (meta.planner)


async def test_check_plan_does_not_end_the_loop() -> None:
    llm = ScriptedLLM(calls(("check_plan", {"plan": GOOD})), calls(("submit_plan", {"plan": GOOD})))
    result = await plan_request(llm, REQUEST, FakeCounter(), max_steps=6)
    assert outputs(llm, 1) == [{"ok": True, "errors": [], "warnings": []}]
    assert result.steps == 2


async def test_step_limit_gives_could_not_interpret_with_the_best_attempt() -> None:
    bad = GOOD | {"dimension": "colour"}
    llm = ScriptedLLM(*[calls(("submit_plan", {"plan": bad}))] * 3)
    result = await plan_request(llm, REQUEST, FakeCounter(), max_steps=3)
    assert result.plan is None
    assert result.best_attempt == bad
    assert any("unknown dimension" in e for e in result.errors)
    assert result.steps == 3


async def test_a_text_answer_gets_a_nudge() -> None:
    llm = ScriptedLLM(text("I think it's a bar chart."), calls(("submit_plan", {"plan": GOOD})))
    result = await plan_request(llm, REQUEST, FakeCounter(), max_steps=6)
    assert result.plan is not None
    assert "submit_plan" in llm.prompt_text(1)


async def test_out_of_scope_plans_are_accepted() -> None:
    plan = {
        "scope": "out_of_scope",
        "scope_reason": "asks whether a drug works",
        "intent": "single_number",
        "chart_type": "metric",
    }
    llm = ScriptedLLM(calls(("submit_plan", {"plan": plan})))
    result = await plan_request(
        llm, QueryRequest(query="Does pembrolizumab work?"), FakeCounter(), max_steps=6
    )
    assert result.plan is not None and result.plan.scope == "out_of_scope"


async def test_list_options_returns_the_registry() -> None:
    llm = ScriptedLLM(calls(("list_options", {})), calls(("submit_plan", {"plan": GOOD})))
    await plan_request(llm, REQUEST, FakeCounter(), max_steps=6)
    [options] = outputs(llm, 1)
    assert "phase" in {d["key"] for d in options["dimensions"]}
    assert "trial_count" in options["measures"]
    assert {"network_graph", "scatter_plot"} <= set(options["chart_types"])
    assert "network_graph" in options["chart_rules"] and "scatter_plot" in options["chart_rules"]


async def test_structured_fields_are_given_as_fixed_facts() -> None:
    request = QueryRequest(query="Trials per year for this drug", drug_name="Pembrolizumab")
    trend = {
        "scope": "in_scope",
        "intent": "trend",
        "chart_type": "time_series",
        "dimension": "start_year",
    }
    llm = ScriptedLLM(calls(("submit_plan", {"plan": trend})))
    result = await plan_request(llm, request, FakeCounter(), max_steps=6)
    assert '"drug_name": ["Pembrolizumab"]' in llm.prompt_text(0)
    assert result.plan is not None and result.plan.filters.drugs == ["Pembrolizumab"]


async def test_model_outages_propagate() -> None:
    with pytest.raises(LLMUnavailable):
        await plan_request(ScriptedLLM(LLMUnavailable("down")), REQUEST, FakeCounter(), max_steps=6)
