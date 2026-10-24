"""A plain total ("How many trials are there?") through the real client: the count call already
answers it, so only a sample page is read, never every trial."""

from typing import Any

import httpx
import pytest

from app.mirror.fast import FastUnavailable, fetch_from_mirror
from app.pipeline.citations import source_pages
from app.pipeline.run import TOTAL_NOTE, prepare, run_plan
from app.schemas.plan import QueryPlan
from tests.support.fakes import json_response
from tests.support.recorded_api import BASE, VERSION, recorded_client


def study(nct: str) -> dict[str, Any]:
    return {"protocolSection": {"identificationModule": {"nctId": nct, "briefTitle": f"T {nct}"}}}


SAMPLE = [study("N1"), study("N2"), study("N3")]


def handler(total: int):  # type: ignore[no-untyped-def]
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            return json_response(VERSION)
        size = int(request.url.params["pageSize"])
        if request.url.params.get("countTotal") == "true" and size == 1:
            return json_response({"studies": [], "totalCount": total})
        studies = SAMPLE[:size] if size < 1000 else SAMPLE  # a sample page, or the download
        body: dict[str, Any] = {"studies": studies}
        if request.url.params.get("countTotal") == "true":
            body["totalCount"] = len(studies)
        return json_response(body)

    return respond


def plan(**overrides: Any) -> QueryPlan:
    base = {"scope": "in_scope", "intent": "single_number", "chart_type": "metric"}
    return QueryPlan.model_validate(base | overrides)


async def test_a_plain_total_is_counted_not_downloaded() -> None:
    client, transport = recorded_client(handler(608_415))
    response = await run_plan(plan(), client, base_url=BASE, citations_per_datum=2)
    (row,) = response.visualization.data  # type: ignore[union-attr]
    assert (row["value"], row["citation_count"], row["citations_truncated"]) == (  # type: ignore[index]
        608_415,
        608_415,
        True,
    )
    assert [c["nct_id"] for c in row["citations"]] == ["N1", "N2"]  # type: ignore[index]
    assert row["search_url"].startswith(BASE + "/studies?")  # type: ignore[index]
    assert "1000" not in {r.url.params.get("pageSize") for r in transport.requests}
    assert response.meta.unique_trials == 608_415
    assert TOTAL_NOTE in response.meta.notes
    assert response.meta.citations is not None and response.meta.citations.applied == "sample"


async def test_a_plain_total_is_not_a_background_job() -> None:
    client, _ = recorded_client(handler(608_415))
    prepared = await prepare(plan(), client, citations_per_datum=2)
    assert prepared.estimated_seconds < 10


async def test_one_page_of_trials_is_still_downloaded() -> None:
    client, transport = recorded_client(handler(3))
    response = await run_plan(plan(), client, base_url=BASE, citations_per_datum=2)
    assert "1000" in {r.url.params.get("pageSize") for r in transport.requests}
    assert TOTAL_NOTE not in response.meta.notes
    assert response.visualization.data[0]["value"] == 3  # type: ignore[index, union-attr]


async def test_other_measures_and_groups_still_download() -> None:
    for other in (
        plan(measure="total_enrollment"),
        plan(
            intent="comparison",
            chart_type="grouped_bar_chart",
            groups=[
                {"label": "A", "filters": {"conditions": ["asthma"]}},
                {"label": "B", "filters": {"conditions": ["copd"]}},
            ],
        ),
    ):
        client, _ = recorded_client(handler(608_415))
        prepared = await prepare(other, client, citations_per_datum=2)
        assert prepared.estimated_seconds > 10, other


async def test_the_rest_of_a_total_pages_from_its_search() -> None:
    """The citations endpoint lists every trial of a counted total: each one is cited."""
    client, _ = recorded_client(handler(608_415))
    source = {"params": {}, "fields": ["NCTId"], "sort": "LastUpdatePostDate:desc"}
    cited, _ = await source_pages(client)(source | {"dimension": None}, "all", None)
    assert [c["nct_id"] for c in cited] == ["N1", "N2", "N3"]


async def test_fast_mode_leaves_a_plain_total_to_the_count() -> None:
    """Reading every record from our copy would be slower than the count already made."""
    client, _ = recorded_client(handler(50_000))
    prepared = await prepare(plan(), client, citations_per_datum=2)
    with pytest.raises(FastUnavailable, match="count"):
        await fetch_from_mirror(
            prepared,
            client,
            None,
            new_term_max_trials=20_000,
            max_trials=300_000,  # type: ignore[arg-type]
        )
