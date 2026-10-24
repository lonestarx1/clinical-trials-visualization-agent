"""Fast per-year counts: one count call per year instead of downloading every trial.

Hand-made table: 2015 has 10 trials (1 with an estimated start), 2016 has 20 (none
estimated); 30 start in 2015-2016, so the years add up.
"""

from typing import Any

import pytest

from app.ctgov.client import InconsistentResults
from app.ctgov.compiler import Search
from app.ctgov.retrieval import YearCounts, count_per_year
from app.pipeline.charts import counted_time_series
from app.pipeline.citations import verify_citations
from app.pipeline.run import yearly_span
from app.registry import DIMENSIONS
from app.schemas.plan import QueryPlan

Y15 = "AREA[StartDate]RANGE[2015-01-01,2015-12-31]"
Y16 = "AREA[StartDate]RANGE[2016-01-01,2016-12-31]"
BOTH = "AREA[StartDate]RANGE[2015-01-01,2016-12-31]"
EST = "AREA[StartDateType]ESTIMATED"
TABLE = {BOTH: 30, Y15: 10, Y16: 20, f"({Y15} AND {EST})": 1, f"({Y16} AND {EST})": 0}


class TableCounter:
    def __init__(self, table: dict[str, int]) -> None:
        self.table, self.asked = table, []  # type: ignore[var-annotated]

    async def count(self, search: Search) -> int:
        advanced = search.params.get("filter.advanced", "")
        self.asked.append(advanced)
        return self.table[advanced]


def plan(**overrides: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "trend",
        "chart_type": "time_series",
        "dimension": "start_year",
        "filters": {"start_year_min": 2015, "start_year_max": 2016},
    }
    return QueryPlan.model_validate(base | overrides)


async def test_counts_each_year_and_its_estimated_starts() -> None:
    counts = await count_per_year(
        TableCounter(TABLE), Search({}), DIMENSIONS["start_year"], (2015, 2016)
    )
    assert counts == YearCounts(within=30, years={2015: 10, 2016: 20}, estimated={2015: 1, 2016: 0})


async def test_years_that_do_not_add_up_are_rejected() -> None:
    with pytest.raises(InconsistentResults):
        await count_per_year(
            TableCounter(TABLE | {Y16: 19}), Search({}), DIMENSIONS["start_year"], (2015, 2016)
        )


async def test_first_posted_years_have_no_estimated_dates() -> None:
    table = {
        "AREA[StudyFirstPostDate]RANGE[2015-01-01,2016-12-31]": 5,
        "AREA[StudyFirstPostDate]RANGE[2015-01-01,2015-12-31]": 2,
        "AREA[StudyFirstPostDate]RANGE[2016-01-01,2016-12-31]": 3,
    }
    counter = TableCounter(table)
    counts = await count_per_year(
        counter, Search({}), DIMENSIONS["first_posted_year"], (2015, 2016)
    )
    assert counts.estimated == {2015: 0, 2016: 0}
    assert len(counter.asked) == 3


@pytest.mark.parametrize(
    ("overrides", "span"),
    [
        ({}, (2015, 2016)),
        ({"filters": {"start_year_min": 2010}}, (2010, 2026)),
        ({"filters": {}}, None),  # no first year: download as before
        ({"filters": {"start_year_min": 1950}}, None),  # more than 60 years
        ({"measure": "total_enrollment"}, None),
        ({"dimension_2": "phase", "chart_type": "time_series"}, None),
        (
            {
                "groups": [
                    {"label": "A", "filters": {"drugs": ["a"]}},
                    {"label": "B", "filters": {"drugs": ["b"]}},
                ]
            },
            None,
        ),
        ({"intent": "distribution", "chart_type": "bar_chart", "dimension": "phase"}, None),
    ],
)
def test_the_fast_path_is_for_plain_yearly_trial_counts(
    overrides: dict[str, Any], span: tuple[int, int] | None
) -> None:
    assert yearly_span(plan(**overrides), now_year=2026) == span


def study(nct: str, date: str, kind: str = "ACTUAL") -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
            "statusModule": {"startDateStruct": {"date": date, "type": kind}},
        }
    }


def test_rows_carry_the_counts_and_a_sample_of_cited_trials() -> None:
    samples = {
        2015: [study("N1", "2015-12-31"), study("N2", "2015-06-01", "ESTIMATED")],
        2016: [study("N3", "2016-11-02")],
    }
    counts = YearCounts(within=30, years={2015: 10, 2016: 20}, estimated={2015: 1, 2016: 0})
    result = counted_time_series(plan(), counts, samples, limit=2)
    rows = result.visualization.data
    assert [(r["start_year"], r["trial_count"], r["estimated_count"]) for r in rows] == [  # type: ignore[index]
        ("2015", 10, 1),
        ("2016", 20, 0),
    ]
    assert [r["citation_count"] for r in rows] == [10, 20]  # type: ignore[index]
    assert [[c["nct_id"] for c in r["citations"]] for r in rows] == [["N1", "N2"], ["N3"]]  # type: ignore[index]
    assert all(r["citations_truncated"] for r in rows)  # type: ignore[index]
    verify_citations(
        result.visualization,
        {
            s["protocolSection"]["identificationModule"]["nctId"]: s
            for v in samples.values()
            for s in v
        },
    )
    assert result.meta.unique_trials == 30 and result.meta.additive is True
    assert result.visualization.type == "time_series"
