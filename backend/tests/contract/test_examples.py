"""The README example runs (docs/examples) must match the published response schema (Q12, Q18).

They are produced by scripts/run_examples.py against the running system, never by hand.
The citation exactness check already ran on the server before each response was returned.
"""

import json
from pathlib import Path

import pytest

from app.schemas.response import SCHEMA_VERSION, QueryResponse

EXAMPLES = sorted((Path(__file__).resolve().parents[3] / "docs" / "examples").glob("*.json"))


def test_there_are_three_to_five_examples() -> None:
    assert 3 <= len(EXAMPLES) <= 5  # Part 6


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_example_matches_the_schema(path: Path) -> None:
    record = json.loads(path.read_text())
    assert record["response"]["schema_version"] == SCHEMA_VERSION
    assert "summary" not in record["response"]["visualization"]  # removed in schema 2.0
    response = QueryResponse.model_validate(record["response"])
    assert response.status == "ok"
    viz = response.visualization
    assert viz is not None and viz.title
    assert "{" not in viz.title
    rows = [*viz.data["nodes"], *viz.data["edges"]] if isinstance(viz.data, dict) else viz.data
    for channel in viz.encoding.values():
        assert any(channel.field in row for row in rows), channel.field
    for row in rows:
        assert len(row["citations"]) <= record["request"]["citations_per_datum"]
        assert len(row["citations"]) == min(row["citation_count"], len(row["citations"]))
        for citation in row["citations"]:
            assert citation["nct_id"].startswith("NCT") and citation["evidence"]
            assert citation["url"].endswith(citation["nct_id"])
