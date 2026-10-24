"""A scripted stand-in for the LLM: replies are given in order; every call is recorded."""

import json
from typing import Any

from app.llm.client import LLMCall, LLMReply, LLMUnavailable, ToolCall, UsageLog


def text(value: Any, model: str = "fake-model") -> LLMReply:
    body = value if isinstance(value, str) else json.dumps(value)
    item = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": body}],
    }
    return LLMReply(body, [], [item], model)


def calls(*tool_calls: tuple[str, dict[str, Any]], model: str = "fake-model") -> LLMReply:
    parsed = [
        ToolCall(f"call_{i}", name, json.dumps(args)) for i, (name, args) in enumerate(tool_calls)
    ]
    items = [
        {"type": "function_call", "call_id": c.call_id, "name": c.name, "arguments": c.arguments}
        for c in parsed
    ]
    return LLMReply("", parsed, items, model)


class ScriptedLLM:
    def __init__(self, *replies: LLMReply | Exception, stage: str = "fake") -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.usage = UsageLog()
        self.stage = stage

    async def respond(
        self,
        items: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
        instructions: str | None = None,
    ) -> LLMReply:
        self.requests.append(
            {
                "items": list(items),
                "tools": tools,
                "json_schema": json_schema,
                "instructions": instructions,
            }
        )
        if not self.replies:
            raise LLMUnavailable("script exhausted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        self.usage.calls.append(LLMCall(self.stage, reply.model, False, 100, 0, 20, 0, 0.0001, 5))
        return reply

    def prompt_text(self, index: int = -1) -> str:
        """Everything sent on one call, as text (instructions + input)."""
        request = self.requests[index]
        parts = [request["instructions"] or ""]
        for item in request["items"]:
            content = item.get("content", item.get("output", ""))
            parts.append(content if isinstance(content, str) else json.dumps(content))
        return "\n".join(parts)
