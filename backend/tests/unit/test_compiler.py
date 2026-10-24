"""Plan filters -> ClinicalTrials.gov search parameters (design Q7).

Expected strings are written by hand from the design's mapping table.
"""

from typing import Any

from app.ctgov.compiler import compile_filters, compile_plan
from app.schemas.plan import Filters, QueryPlan


def params(**filters: Any) -> dict[str, str]:
    return compile_filters(Filters.model_validate(filters)).params


def test_no_filters_means_all_studies() -> None:
    assert params() == {}


def test_drug_strict_uses_intervention_name_search() -> None:
    assert params(drugs=["pembrolizumab"]) == {
        "filter.advanced": 'AREA[InterventionNameSearch]"pembrolizumab"'
    }


def test_several_drugs_are_or_ed() -> None:
    assert params(drugs=["pembrolizumab", "nivolumab"]) == {
        "filter.advanced": '(AREA[InterventionNameSearch]"pembrolizumab" OR '
        'AREA[InterventionNameSearch]"nivolumab")'
    }


def test_drug_broad_uses_query_intr() -> None:
    assert params(drugs=["pembrolizumab"], match_mode="broad") == {"query.intr": '"pembrolizumab"'}


def test_condition_strict_is_a_quoted_phrase() -> None:
    assert params(conditions=["breast cancer", "lung cancer"]) == {
        "query.cond": '("breast cancer" OR "lung cancer")'
    }


def test_condition_broad_lets_words_match_separately() -> None:
    assert params(conditions=["lung cancer", "melanoma"], match_mode="broad") == {
        "query.cond": '(("lung" AND "cancer") OR "melanoma")'
    }


def test_sponsor_role_picks_the_parameter() -> None:
    assert params(sponsors=["Merck"]) == {"query.lead": '"Merck"'}
    assert params(sponsors=["Merck"], sponsor_role="any") == {"query.spons": '"Merck"'}


def test_countries_use_canonical_names() -> None:
    assert params(countries=["USA", "Korea"]) == {
        "filter.advanced": '(AREA[LocationCountry]"United States" OR '
        'AREA[LocationCountry]"South Korea")'
    }


def test_unknown_country_passes_through_with_a_warning() -> None:
    compiled = compile_filters(Filters(countries=["Narnia"]))
    assert compiled.params == {"filter.advanced": 'AREA[LocationCountry]"Narnia"'}
    assert compiled.warnings == ["Country 'Narnia' is not a known ClinicalTrials.gov name."]


def test_status_is_the_overall_status_filter() -> None:
    assert params(statuses=["RECRUITING", "NOT_YET_RECRUITING"]) == {
        "filter.overallStatus": "RECRUITING|NOT_YET_RECRUITING"
    }


def test_enum_filters_are_or_ed_codes() -> None:
    assert params(phases=["PHASE2", "PHASE3"], sponsor_classes=["INDUSTRY"]) == {
        "filter.advanced": "((AREA[Phase]PHASE2 OR AREA[Phase]PHASE3) AND "
        "AREA[LeadSponsorClass]INDUSTRY)"
    }


def test_boolean_filters() -> None:
    assert params(healthy_volunteers=True, has_results=False) == {
        "filter.advanced": "(AREA[HealthyVolunteers]true AND AREA[HasResults]false)"
    }


def test_year_ranges() -> None:
    assert params(start_year_min=2015) == {
        "filter.advanced": "AREA[StartDate]RANGE[2015-01-01,MAX]"
    }
    assert params(start_year_max=2020) == {
        "filter.advanced": "AREA[StartDate]RANGE[MIN,2020-12-31]"
    }
    assert params(start_year_min=2015, start_year_max=2020) == {
        "filter.advanced": "AREA[StartDate]RANGE[2015-01-01,2020-12-31]"
    }


def test_filters_are_and_ed_in_a_fixed_order() -> None:
    assert params(
        drugs=["pembrolizumab"],
        conditions=["melanoma"],
        countries=["United States"],
        start_year_min=2015,
    ) == {
        "query.cond": '"melanoma"',
        "filter.advanced": '(AREA[InterventionNameSearch]"pembrolizumab" AND '
        'AREA[LocationCountry]"United States" AND AREA[StartDate]RANGE[2015-01-01,MAX])',
    }


def test_injection_attempts_stay_inside_one_phrase() -> None:
    assert params(conditions=['x" OR AREA[Phase]PHASE3 OR "y']) == {
        "query.cond": '"x OR AREA[Phase]PHASE3 OR y"'
    }


def _plan(**overrides: Any) -> QueryPlan:
    base: dict[str, Any] = {
        "scope": "in_scope",
        "intent": "comparison",
        "chart_type": "grouped_bar_chart",
        "dimension": "phase",
    }
    return QueryPlan.model_validate(base | overrides)


def test_single_population_plan_gives_one_search() -> None:
    searches = compile_plan(
        _plan(intent="distribution", chart_type="bar_chart", filters={"conditions": ["x"]})
    )
    assert [(s.group, s.params) for s in searches] == [(None, {"query.cond": '"x"'})]


def test_each_comparison_group_is_its_own_search() -> None:
    searches = compile_plan(
        _plan(
            filters={"conditions": ["melanoma"]},
            groups=[
                {"label": "Pembrolizumab", "filters": {"drugs": ["pembrolizumab"]}},
                {"label": "Nivolumab", "filters": {"drugs": ["nivolumab"]}},
            ],
        )
    )
    assert [(s.group, s.params) for s in searches] == [
        (
            "Pembrolizumab",
            {
                "query.cond": '"melanoma"',
                "filter.advanced": 'AREA[InterventionNameSearch]"pembrolizumab"',
            },
        ),
        (
            "Nivolumab",
            {
                "query.cond": '"melanoma"',
                "filter.advanced": 'AREA[InterventionNameSearch]"nivolumab"',
            },
        ),
    ]


def test_shared_and_group_terms_on_the_same_parameter_are_and_ed() -> None:
    searches = compile_plan(
        _plan(
            filters={"conditions": ["cancer"], "statuses": ["RECRUITING", "COMPLETED"]},
            groups=[
                {"label": "Breast", "filters": {"conditions": ["breast cancer"]}},
                {
                    "label": "Lung",
                    "filters": {"conditions": ["lung cancer"], "statuses": ["RECRUITING"]},
                },
            ],
        )
    )
    assert searches[0].params == {
        "query.cond": '("cancer" AND "breast cancer")',
        "filter.overallStatus": "RECRUITING|COMPLETED",
    }
    assert searches[1].params["filter.overallStatus"] == "RECRUITING"


def test_search_url_is_reproducible() -> None:
    search = compile_filters(Filters(conditions=["breast cancer"], statuses=["RECRUITING"]))
    assert search.url("https://clinicaltrials.gov/api/v2") == (
        "https://clinicaltrials.gov/api/v2/studies?"
        "filter.overallStatus=RECRUITING&query.cond=%22breast+cancer%22"
    )


def test_sex_all_means_trials_open_to_all_sexes() -> None:
    """Not every trial: the unquoted code matched all of them (live mode kept every trial)."""
    assert params(sexes=["ALL"])["filter.advanced"] == 'AREA[Sex]"ALL"'
