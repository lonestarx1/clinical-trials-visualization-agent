"""LLM client (design Q8, Q16, Q20): per-model parameters, cost, retries and the fallback model."""

import json
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI

from app.core.config import StageSettings
from app.core.pricing import load_pricing
from app.llm.client import LLMUnavailable, OpenAILLM, UsageLog, is_reasoning_model

TOOL = {"type": "function", "name": "count_trials", "parameters": {"type": "object"}}


def response_body(
    model: str, output: list[dict[str, Any]], usage: dict[str, int] | None = None
) -> dict:
    u = {"input_tokens": 1000, "cached": 200, "output_tokens": 500, "reasoning": 100} | (
        usage or {}
    )
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": "completed",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": u["input_tokens"],
            "input_tokens_details": {"cached_tokens": u["cached"]},
            "output_tokens": u["output_tokens"],
            "output_tokens_details": {"reasoning_tokens": u["reasoning"]},
            "total_tokens": u["input_tokens"] + u["output_tokens"],
        },
    }


MESSAGE = {
    "type": "message",
    "id": "m1",
    "role": "assistant",
    "status": "completed",
    "content": [{"type": "output_text", "text": '{"verdict": "ok"}', "annotations": []}],
}
CALL = {
    "type": "function_call",
    "id": "fc1",
    "call_id": "call_1",
    "name": "count_trials",
    "arguments": '{"drug": "keytruda"}',
    "status": "completed",
}


class FakeOpenAI:
    """Records request bodies; answers per model from a script."""

    def __init__(self, script: dict[str, list[httpx.Response]]) -> None:
        self.script, self.bodies = script, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        return self.script[body["model"]].pop(0)

    def llm(self, **stage: Any) -> tuple[OpenAILLM, UsageLog]:
        client = AsyncOpenAI(
            api_key="test",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )
        log = UsageLog()
        settings = StageSettings(
            **(
                {
                    "model": "gpt-5.4-mini",
                    "max_output_tokens": 800,
                    "timeout_seconds": 5,
                    "max_retries": 0,
                }
                | stage
            )
        )
        return OpenAILLM(client, settings, stage="planner", pricing=load_pricing(), usage=log), log


def ok(model: str, *output: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=response_body(model, list(output)))


def test_reasoning_models() -> None:
    assert is_reasoning_model("gpt-5.4-mini") and is_reasoning_model("gpt-5")
    assert not is_reasoning_model("gpt-4.1-mini") and not is_reasoning_model("gpt-4o-mini")


async def test_reasoning_model_request_parameters() -> None:
    fake = FakeOpenAI({"gpt-5.4-mini": [ok("gpt-5.4-mini", CALL)]})
    llm, _ = fake.llm(reasoning_effort="medium", temperature=0.3)
    reply = await llm.respond([{"role": "user", "content": "hi"}], tools=[TOOL])

    body = fake.bodies[0]
    assert body["reasoning"] == {"effort": "medium"}
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["store"] is False
    assert body["max_output_tokens"] == 800
    assert "temperature" not in body  # reasoning models don't take it
    assert [(c.name, c.arguments) for c in reply.tool_calls] == [
        ("count_trials", '{"drug": "keytruda"}')
    ]
    assert reply.output_items[0]["call_id"] == "call_1"


async def test_non_reasoning_model_request_parameters() -> None:
    fake = FakeOpenAI({"gpt-4.1-mini": [ok("gpt-4.1-mini", MESSAGE)]})
    llm, _ = fake.llm(model="gpt-4.1-mini", fallback_model=None, temperature=0.0)
    reply = await llm.respond(
        [{"role": "user", "content": "hi"}, {"type": "reasoning", "id": "r1", "summary": []}],
        json_schema={"name": "verdict", "schema": {"type": "object"}},
    )
    body = fake.bodies[0]
    assert body["temperature"] == 0.0
    assert "reasoning" not in body and "include" not in body
    assert body["input"] == [{"role": "user", "content": "hi"}]  # reasoning items stripped
    assert body["text"]["format"]["type"] == "json_schema"
    assert reply.text == '{"verdict": "ok"}'


async def test_usage_and_cost_are_recorded() -> None:
    fake = FakeOpenAI({"gpt-5.4-mini": [ok("gpt-5.4-mini", MESSAGE)]})
    llm, log = fake.llm()
    await llm.respond([{"role": "user", "content": "hi"}])
    [call] = log.calls
    assert (call.stage, call.model, call.fallback) == ("planner", "gpt-5.4-mini", False)
    assert (call.input_tokens, call.cached_tokens, call.output_tokens) == (1000, 200, 500)
    # 800 uncached x 0.75 + 200 cached x 0.075 + 500 output x 4.50, per 1M tokens
    assert call.cost_usd == pytest.approx((800 * 0.75 + 200 * 0.075 + 500 * 4.50) / 1e6)
    assert log.summary()["llm_calls"] == 1


async def test_unknown_prices_are_recorded_as_unknown_not_zero() -> None:
    fake = FakeOpenAI({"gpt-4o-2024-08-06": [ok("gpt-4o-2024-08-06", MESSAGE)]})
    llm, log = fake.llm(model="gpt-4o-2024-08-06")
    await llm.respond([{"role": "user", "content": "hi"}])
    assert log.calls[0].cost_usd is None
    assert log.summary()["cost_usd"] is None


async def test_falls_back_to_the_other_model() -> None:
    fake = FakeOpenAI(
        {
            "gpt-5.4-mini": [httpx.Response(500, json={"error": {"message": "boom"}})],
            "gpt-4.1-mini": [ok("gpt-4.1-mini", MESSAGE)],
        }
    )
    llm, log = fake.llm()
    reply = await llm.respond([{"role": "user", "content": "hi"}])
    assert reply.model == "gpt-4.1-mini"
    assert [c.fallback for c in log.calls] == [True]
    assert [b["model"] for b in fake.bodies] == ["gpt-5.4-mini", "gpt-4.1-mini"]


async def test_raises_when_both_models_fail() -> None:
    fail = httpx.Response(503, json={"error": {"message": "down"}})
    fake = FakeOpenAI({"gpt-5.4-mini": [fail], "gpt-4.1-mini": [fail]})
    llm, _ = fake.llm()
    with pytest.raises(LLMUnavailable):
        await llm.respond([{"role": "user", "content": "hi"}])
