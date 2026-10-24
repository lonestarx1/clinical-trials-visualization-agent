"""OpenAI Responses API client for one AI stage (design Q8, Q16, Q20).

The primary model gets the stage's retries; if it still fails, the fallback
model is tried once with the same input. Every call's tokens and cost are
recorded. Nothing is stored at OpenAI (store=False); reasoning is passed back
between turns in encrypted form.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai
from openai import AsyncOpenAI

from app.core.config import StageSettings
from app.core.pricing import Pricing

log = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """The primary and fallback models both failed (503 llm_unavailable)."""


def is_reasoning_model(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str

    def parsed(self) -> Any:
        return json.loads(self.arguments or "{}")


@dataclass(frozen=True)
class LLMReply:
    text: str
    tool_calls: list[ToolCall]
    output_items: list[dict[str, Any]]  # to send back as input on the next turn
    model: str


@dataclass(frozen=True)
class LLMCall:
    stage: str
    model: str
    fallback: bool
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float | None
    latency_ms: int


@dataclass
class UsageLog:
    """Every LLM call made while answering one request."""

    calls: list[LLMCall] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        costs = [c.cost_usd for c in self.calls]
        return {
            "llm_calls": len(self.calls),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "cost_usd": None if None in costs else round(sum(c for c in costs if c), 6),
            "models": sorted({c.model for c in self.calls}),
        }


def _cost(pricing: Pricing, model: str, inputs: int, cached: int, outputs: int) -> float | None:
    price = pricing.models.get(model)
    if price is None:
        return None
    return (
        (inputs - cached) * price.input + cached * price.cached_input + outputs * price.output
    ) / 1e6


class LLM(Protocol):
    """What the agents need from a model. OpenAILLM in production, a scripted fake in tests."""

    usage: UsageLog

    async def respond(
        self,
        items: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
        instructions: str | None = None,
    ) -> LLMReply: ...


class OpenAILLM:
    def __init__(
        self,
        client: AsyncOpenAI,
        settings: StageSettings,
        *,
        stage: str,
        pricing: Pricing,
        usage: UsageLog,
    ) -> None:
        self._client = client
        self._settings = settings
        self._stage = stage
        self._pricing = pricing
        self.usage = usage

    async def respond(
        self,
        items: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
        instructions: str | None = None,
    ) -> LLMReply:
        models = [self._settings.model]
        if self._settings.fallback_model:
            models.append(self._settings.fallback_model)
        problem: Exception | None = None
        for attempt, model in enumerate(models):
            try:
                return await self._call(model, items, tools, json_schema, instructions, attempt > 0)
            except openai.OpenAIError as exc:
                problem = exc
                log.warning("%s: %s failed (%s)", self._stage, model, type(exc).__name__)
        raise LLMUnavailable(f"{self._stage}: all models failed") from problem

    async def _call(
        self,
        model: str,
        items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        json_schema: dict[str, Any] | None,
        instructions: str | None,
        fallback: bool,
    ) -> LLMReply:
        s = self._settings
        reasoning = is_reasoning_model(model)
        params: dict[str, Any] = {
            "model": model,
            "input": items if reasoning else [i for i in items if i.get("type") != "reasoning"],
            "max_output_tokens": s.max_output_tokens,
            "store": False,
        }
        if instructions:
            params["instructions"] = instructions
        if tools:
            params["tools"] = tools
        if json_schema:
            params["text"] = {"format": {"type": "json_schema", "strict": True, **json_schema}}
        if reasoning:
            params["reasoning"] = {"effort": s.reasoning_effort}
            params["include"] = ["reasoning.encrypted_content"]
        elif s.temperature is not None:
            params["temperature"] = s.temperature

        client = self._client.with_options(max_retries=s.max_retries, timeout=s.timeout_seconds)
        started = time.perf_counter()
        response = await client.responses.create(**params)
        latency = round((time.perf_counter() - started) * 1000)

        usage = response.usage
        inputs = usage.input_tokens if usage else 0
        cached = usage.input_tokens_details.cached_tokens if usage else 0
        outputs = usage.output_tokens if usage else 0
        self.usage.calls.append(
            LLMCall(
                stage=self._stage,
                model=model,
                fallback=fallback,
                input_tokens=inputs,
                cached_tokens=cached,
                output_tokens=outputs,
                reasoning_tokens=usage.output_tokens_details.reasoning_tokens if usage else 0,
                cost_usd=_cost(self._pricing, model, inputs, cached, outputs),
                latency_ms=latency,
            )
        )
        output_items = [o.model_dump(exclude_none=True) for o in response.output]
        calls = [
            ToolCall(o["call_id"], o["name"], o.get("arguments", ""))
            for o in output_items
            if o.get("type") == "function_call"
        ]
        return LLMReply(response.output_text, calls, output_items, model)
