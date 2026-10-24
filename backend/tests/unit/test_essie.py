"""Essie expression tree (design Q7, D7.1): user text can never change the query's structure."""

import pytest

from app.ctgov.essie import And, Area, Code, Missing, Not, Or, Phrase, Range, to_essie


def test_phrase_is_quoted() -> None:
    assert to_essie(Phrase("lung cancer")) == '"lung cancer"'


def test_phrase_is_cleaned() -> None:
    assert to_essie(Phrase("  Pembrolizumab\n\t ")) == '"Pembrolizumab"'
    assert to_essie(Phrase("ｐｅｍｂｒｏ")) == '"pembro"'  # full-width letters (NFKC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('aspirin" OR ALL', '"aspirin OR ALL"'),
        ('x") OR AREA[Phase]PHASE3 OR ("y', '"x ) OR AREA[Phase]PHASE3 OR ( y"'),
        ("back\\slash", '"back slash"'),
        ("tab\x00null", '"tab null"'),
    ],
)
def test_phrase_cannot_break_out_of_its_quotes(raw: str, expected: str) -> None:
    out = to_essie(Phrase(raw))
    assert out == expected
    assert out.count('"') == 2


@pytest.mark.parametrize("raw", ["", "   ", '""', "\\"])
def test_empty_phrase_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        Phrase(raw)


def test_area_with_phrase_and_code() -> None:
    assert to_essie(Area("LocationCountry", Phrase("South Korea"))) == (
        'AREA[LocationCountry]"South Korea"'
    )
    assert to_essie(Area("Phase", Code("PHASE3"))) == "AREA[Phase]PHASE3"


@pytest.mark.parametrize("bad", ["Phase]X", "Phase Name", "", "AREA[x"])
def test_area_field_must_be_a_plain_name(bad: str) -> None:
    with pytest.raises(ValueError):
        Area(bad, Code("X"))


@pytest.mark.parametrize("bad", ["phase 3", "PHASE3 OR ALL", "", "a]b"])
def test_code_must_be_an_enum_token(bad: str) -> None:
    with pytest.raises(ValueError):
        Code(bad)


def test_boolean_codes_are_allowed() -> None:
    assert to_essie(Area("HealthyVolunteers", Code("true"))) == "AREA[HealthyVolunteers]true"


def test_range_and_missing() -> None:
    assert to_essie(Area("StartDate", Range("2015-01-01", "MAX"))) == (
        "AREA[StartDate]RANGE[2015-01-01,MAX]"
    )
    assert to_essie(Area("StartDate", Missing())) == "AREA[StartDate]MISSING"


@pytest.mark.parametrize(("lo", "hi"), [("2015", "MAX"), ("MIN", "2020-13-01"), ("x", "y")])
def test_range_bounds_must_be_dates_or_min_max(lo: str, hi: str) -> None:
    with pytest.raises(ValueError):
        Range(lo, hi)


def test_boolean_operators_are_parenthesised() -> None:
    expr = And(
        [
            Or([Area("Phase", Code("PHASE2")), Area("Phase", Code("PHASE3"))]),
            Not(Area("StudyType", Code("OBSERVATIONAL"))),
        ]
    )
    assert to_essie(expr) == (
        "((AREA[Phase]PHASE2 OR AREA[Phase]PHASE3) AND NOT AREA[StudyType]OBSERVATIONAL)"
    )


def test_single_item_groups_collapse() -> None:
    assert to_essie(Or([Phrase("x")])) == '"x"'
    assert to_essie(And([Or([Phrase("x")])])) == '"x"'


def test_empty_groups_are_rejected() -> None:
    with pytest.raises(ValueError):
        And([])
