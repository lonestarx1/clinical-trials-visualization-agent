"""The README example runs (docs/examples) must match the published response schema (Q12, Q18).

They are produced by scripts/run_examples.py against the running system, never by hand.
The citation exactness check already ran on the server before each response was returned.
"""

import json
from pathlib import Path

import pytest

from app.schemas.response import QueryResponse

EXAMPLES = sorted((Path(__file__).resolve().parents[3] / "docs" / "examples").glob("*.json"))


def test_there_are_three_to_five_examples() -> None:
    assert 3 <= len(EXAMPLES) <= 5  # Part 6


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_example_matches_the_schema(path: Path) -> None:
    record = json.loads(path.read_text())
    response = QueryResponse.model_validate(record["response"])
    assert response.status == "ok"
    viz = response.visualization
    assert viz is not None and viz.title and viz.summary
    assert "{" not in viz.title + viz.summary
    for channel in viz.encoding.values():
        assert any(channel.field in row for row in viz.data), channel.field
    for row in viz.data:
        assert len(row["citations"]) <= record["request"]["citations_per_datum"]
        assert len(row["citations"]) == min(row["citation_count"], len(row["citations"]))
        for citation in row["citations"]:
            assert citation["nct_id"].startswith("NCT") and citation["evidence"]
            assert citation["url"].endswith(citation["nct_id"])
