"""A search split into terms (the API decides) and structured clauses (the mirror decides), Q22."""

from typing import Any

from app.ctgov.compiler import Clause, Search, compile_filters, compile_plan
from app.ctgov.essie import Area, Code, Or, Phrase, Range, to_essie
from app.mirror.terms import Term, split
from app.schemas.plan import Filters, QueryPlan


def search(**filters: Any):  # type: ignore[no-untyped-def]
    return compile_filters(Filters.model_validate(filters))


def test_a_search_keeps_the_clauses_its_parameters_were_built_from() -> None:
    s = search(conditions=["melanoma"], phases=["PHASE2"], statuses=["RECRUITING"])
    assert s.clauses == (
        Clause("query.cond", Or([Phrase("melanoma")])),
        Clause("filter.advanced", Or([Area("Phase", Code("PHASE2"))])),
        Clause("filter.overallStatus", Or([Code("RECRUITING")])),
    )
    narrowed = s.narrow(Area("StartDate", Range("2015-01-01", "2015-12-31")))
    assert narrowed.clauses[-1] == Clause(
        "filter.advanced", Area("StartDate", Range("2015-01-01", "2015-12-31"))
    )


def test_each_filter_value_of_a_searched_parameter_is_one_term() -> None:
    terms, structured = split(search(conditions=["breast cancer", "lung cancer"]))
    assert terms == [[Term("query.cond", '"breast cancer"'), Term("query.cond", '"lung cancer"')]]
    assert structured == []


def test_a_broad_condition_is_one_term_with_its_words() -> None:
    terms, _ = split(search(conditions=["lung cancer"], match_mode="broad"))
    assert terms == [[Term("query.cond", '("lung" AND "cancer")')]]


def test_phrase_areas_are_terms_and_codes_ranges_and_statuses_are_structured() -> None:
    s = search(
        drugs=["pembrolizumab"],
        countries=["Japan"],
        sponsors=["Pfizer"],
        phases=["PHASE2", "PHASE3"],
        statuses=["RECRUITING"],
        start_year_min=2015,
    )
    terms, structured = split(s)
    assert terms == [
        [Term("query.lead", '"Pfizer"')],
        [Term("filter.advanced", 'AREA[InterventionNameSearch]"pembrolizumab"')],
        [Term("filter.advanced", 'AREA[LocationCountry]"Japan"')],
    ]
    assert [(c.param, to_essie(c.node)) for c in structured] == [
        ("filter.advanced", "(AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)"),
        ("filter.advanced", "AREA[StartDate]RANGE[2015-01-01,MAX]"),
        ("filter.overallStatus", "RECRUITING"),
    ]


def test_a_term_is_searched_on_its_own_and_keyed_by_parameter_and_text() -> None:
    term = Term("query.cond", '"lung cancer"')
    assert term.search().params == {"query.cond": '"lung cancer"'}
    assert term.key == 'query.cond|"lung cancer"'


def test_a_group_search_splits_into_shared_and_group_clauses() -> None:
    plan = QueryPlan.model_validate(
        {
            "scope": "in_scope",
            "intent": "comparison",
            "chart_type": "grouped_bar_chart",
            "dimension": "phase",
            "filters": {"conditions": ["melanoma"]},
            "groups": [
                {"label": "Keytruda", "filters": {"drugs": ["pembrolizumab"]}},
                {"label": "Opdivo", "filters": {"drugs": ["nivolumab"]}},
            ],
        }
    )
    first, _ = compile_plan(plan)
    terms, _ = split(first)
    assert terms == [
        [Term("query.cond", '"melanoma"')],
        [Term("filter.advanced", 'AREA[InterventionNameSearch]"pembrolizumab"')],
    ]


def test_a_search_built_by_hand_has_no_clauses_to_split() -> None:
    assert split(Search({"query.cond": '"x"'})) is None  # the mirror can't evaluate it


def test_a_compiled_search_without_filters_splits_into_nothing() -> None:
    assert split(search()) == ([], [])  # every trial: the mirror alone answers
