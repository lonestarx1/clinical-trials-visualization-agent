"""The generated OpenAPI document is the API reference (design Q12): it must be complete.

Swagger (/docs) and ReDoc (/redoc) render this document, so every operation needs a
summary, a description and a tag, every documented status needs an example, and the
error examples must use the codes the error handlers really return (Q17).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.errors import _PUBLIC
from app.api.health import Health
from app.main import create_app
from app.schemas.endpoints import (
    CitationPage,
    ErrorResponse,
    JobAccepted,
    JobStatus,
    Options,
    UsageSummary,
)
from app.schemas.request import QueryRequest
from app.schemas.response import QueryResponse
from app.store.results import CODE_VERSION

PRODUCTION = "https://api.cheiron.engineeradriel.com"
LOCAL = "http://localhost:8000"
METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("OPENAI_API_KEY", "test-key-not-real")
        mp.setenv("ENABLE_DEBUG_ENDPOINTS", "true")  # document every route, debug included
        document: dict[str, Any] = TestClient(create_app()).get("/openapi.json").json()
    return document


def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, op)
        for path, item in spec["paths"].items()
        for method, op in item.items()
        if method in METHODS
    ]


def examples(response: dict[str, Any]) -> dict[str, Any]:
    content = response.get("content", {}).get("application/json", {})
    found: dict[str, Any] = content.get("examples", {})
    if "example" in content:
        found = found | {"example": {"value": content["example"]}}
    return found


def resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def test_version_is_the_code_version(spec: dict[str, Any]) -> None:
    assert spec["info"]["version"] == CODE_VERSION


def test_info_describes_the_flow_limits_and_budget(spec: dict[str, Any]) -> None:
    description = spec["info"]["description"]
    for phrase in ("/v1/query", "202", "/v1/jobs/", "/citations", "429", "budget_exceeded"):
        assert phrase in description, phrase


def test_servers_are_production_and_local(spec: dict[str, Any]) -> None:
    assert [s["url"] for s in spec["servers"]] == [PRODUCTION, LOCAL]
    assert all(s.get("description") for s in spec["servers"])


def test_every_tag_used_is_declared_with_a_description(spec: dict[str, Any]) -> None:
    declared = {t["name"]: t.get("description") for t in spec["tags"]}
    assert {"query", "jobs", "citations", "options", "health", "admin"} <= set(declared)
    assert all(declared.values())
    used = {tag for _, _, op in operations(spec) for tag in op.get("tags", [])}
    assert used <= set(declared)


def test_every_operation_has_a_summary_description_and_one_tag(spec: dict[str, Any]) -> None:
    for path, method, op in operations(spec):
        where = f"{method.upper()} {path}"
        assert op.get("summary"), where
        assert op.get("description"), where
        assert len(op.get("tags", [])) == 1, where


def test_every_documented_response_has_an_example(spec: dict[str, Any]) -> None:
    for path, method, op in operations(spec):
        for status, response in op["responses"].items():
            assert response.get("description"), f"{method.upper()} {path} {status}"
            assert examples(response), f"{method.upper()} {path} {status}"


def test_query_documents_its_status_codes(spec: dict[str, Any]) -> None:
    responses = spec["paths"]["/v1/query"]["post"]["responses"]
    assert {"200", "202", "400", "422", "429", "500", "503"} <= set(responses)


def test_query_200_shows_every_status_and_each_example_is_a_valid_response(
    spec: dict[str, Any],
) -> None:
    found = examples(spec["paths"]["/v1/query"]["post"]["responses"]["200"])
    bodies = [QueryResponse.model_validate(e["value"]) for e in found.values()]
    assert {b.status for b in bodies} == {
        "ok",
        "no_matching_trials",
        "out_of_scope",
        "could_not_interpret",
    }


def test_query_202_is_a_background_job(spec: dict[str, Any]) -> None:
    accepted = spec["paths"]["/v1/query"]["post"]["responses"]["202"]
    for example in examples(accepted).values():
        assert example["value"]["status"] == "pending"
        assert example["value"]["poll_url"] == f"/v1/jobs/{example['value']['job_id']}"


def _codes(response: dict[str, Any]) -> set[str]:
    return {e["value"]["error"]["code"] for e in examples(response).values()}


def test_error_examples_use_the_real_codes_and_the_shared_body(spec: dict[str, Any]) -> None:
    real = {(str(status), code) for _, status, code, _ in _PUBLIC} | {
        ("429", "too_many_requests"),  # the rate-limit middleware
        ("500", "internal_error"),
        ("401", "unauthorized"),  # routing and auth errors (HTTPException)
        ("404", "not_found"),
        ("405", "method_not_allowed"),
    }
    for path, method, op in operations(spec):
        for status, response in op["responses"].items():
            if not status.startswith(("4", "5")) or path == "/health":
                continue
            schema = response["content"]["application/json"]["schema"]
            assert resolve(spec, schema).get("title") == "ErrorResponse", (path, status)
            for code in _codes(response):
                assert (status, code) in real, (method.upper(), path, status, code)


def test_query_documents_every_error_it_can_raise(spec: dict[str, Any]) -> None:
    responses = spec["paths"]["/v1/query"]["post"]["responses"]
    assert _codes(responses["400"]) == {"rejected_by_policy"}
    assert _codes(responses["422"]) == {"invalid_request"}
    assert _codes(responses["429"]) == {"too_many_requests"}
    assert _codes(responses["503"]) == {
        "budget_exceeded",
        "upstream_unavailable",
        "llm_unavailable",
        "safety_check_unavailable",
    }


def test_citations_document_not_found_and_expired(spec: dict[str, Any]) -> None:
    responses = spec["paths"]["/v1/results/{result_id}/citations"]["get"]["responses"]
    assert _codes(responses["404"]) == {"not_found"}
    assert _codes(responses["410"]) == {"expired"}


def test_jobs_document_not_found_and_expired(spec: dict[str, Any]) -> None:
    responses = spec["paths"]["/v1/jobs/{job_id}"]["get"]["responses"]
    assert _codes(responses["404"]) == {"not_found"}
    assert _codes(responses["410"]) == {"expired"}


def test_usage_documents_unauthorized_with_the_shared_body(spec: dict[str, Any]) -> None:
    responses = spec["paths"]["/v1/usage"]["get"]["responses"]
    assert _codes(responses["401"]) == {"unauthorized"}


def test_the_error_table_lists_routing_and_auth_errors(spec: dict[str, Any]) -> None:
    for code in ("unauthorized", "method_not_allowed"):
        assert f"`{code}`" in spec["info"]["description"]


def test_every_request_field_has_a_description(spec: dict[str, Any]) -> None:
    for name in ("QueryRequest", "CompareGroup"):
        schema = spec["components"]["schemas"][name]
        missing = [f for f, prop in schema["properties"].items() if not prop.get("description")]
        assert not missing, (name, missing)


@pytest.mark.parametrize(
    "name",
    [
        "QueryResponse",
        "Visualization",
        "Channel",
        "Meta",
        "Interpretation",
        "CitationsMeta",
        "JobAccepted",
        "JobStatus",
        "CitationPage",
        "ErrorResponse",
    ],
)
def test_response_models_describe_every_field(spec: dict[str, Any], name: str) -> None:
    schema = spec["components"]["schemas"][name]
    missing = [f for f, prop in schema["properties"].items() if not prop.get("description")]
    assert not missing, missing


MODELS: dict[str, type[BaseModel]] = {
    "QueryResponse": QueryResponse,
    "JobAccepted": JobAccepted,
    "JobStatus": JobStatus,
    "CitationPage": CitationPage,
    "Options": Options,
    "UsageSummary": UsageSummary,
    "Health": Health,
    "ErrorResponse": ErrorResponse,
}


def test_every_example_is_valid_for_its_schema(spec: dict[str, Any]) -> None:
    """Including the nulls FastAPI would drop (e.g. `visualization: null`)."""
    checked = 0
    for _, _, op in operations(spec):
        for response in op["responses"].values():
            schema = response.get("content", {}).get("application/json", {}).get("schema", {})
            name = schema.get("$ref", "").rsplit("/", 1)[-1]
            if name not in MODELS:
                continue
            for example in examples(response).values():
                MODELS[name].model_validate(example["value"])
                checked += 1
    assert checked >= 20


def test_request_examples_are_valid_requests(spec: dict[str, Any]) -> None:
    body = spec["paths"]["/v1/query"]["post"]["requestBody"]["content"]["application/json"]
    assert body["examples"]
    for example in body["examples"].values():
        QueryRequest.model_validate(example["value"])


def test_the_options_model_matches_the_real_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    Options.model_validate(TestClient(create_app()).get("/v1/options").json())
