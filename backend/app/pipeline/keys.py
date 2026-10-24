"""Cache keys (design Q16): SHA-256 of canonical JSON, so the same logical input gives one key."""

import hashlib
import json
from typing import Any

from app.agents import guard, narrator, planner
from app.core.config import Settings
from app.schemas.plan import QueryPlan
from app.schemas.request import QueryRequest
from app.schemas.response import SCHEMA_VERSION
from app.store.results import CODE_VERSION


def _hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def planner_version(settings: Settings) -> str:
    """Model + prompt + registry/code version: a change gives new plan-cache keys (Q8)."""
    prompts = _hash([planner.INSTRUCTIONS, guard.INSTRUCTIONS, narrator.INSTRUCTIONS])[:12]
    return f"{settings.planner.model}|{prompts}|{CODE_VERSION}"


def request_key(request: QueryRequest, settings: Settings) -> str:
    fields = request.model_dump(mode="json", exclude={"query"} | _RENDER_ONLY)
    query = " ".join(request.query.lower().split())
    return _hash({"query": query, "fields": fields, "planner": planner_version(settings)})


def result_key(plan: QueryPlan, citations_per_datum: int) -> str:
    return _hash(
        {
            "plan": plan.model_dump(mode="json"),
            "citations_per_datum": citations_per_datum,
            "code": CODE_VERSION,
            "schema": SCHEMA_VERSION,
        }
    )


# Request fields that change only how much citation detail is inlined, not the plan.
_RENDER_ONLY = {"citations", "citations_per_datum"}
