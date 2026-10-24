"""Country names resolve deterministically to the API's canonical names (design Q7, D7.3)."""

import json
from pathlib import Path

import pytest

from app.ctgov.countries import ALIASES, CANONICAL, resolve_country

REFERENCE = Path(__file__).resolve().parents[3] / "docs/api/reference/location-countries.json"


def test_canonical_names_are_the_recorded_api_values() -> None:
    assert sorted(CANONICAL) == json.loads(REFERENCE.read_text())["values"]


def test_every_alias_points_to_a_canonical_name() -> None:
    assert set(ALIASES.values()) <= set(CANONICAL)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("United States", "United States"),
        ("united states", "United States"),
        ("USA", "United States"),
        ("U.S.", "United States"),
        ("United States of America", "United States"),
        ("Korea", "South Korea"),
        ("Republic of Korea", "South Korea"),
        ("UK", "United Kingdom"),
        ("Great Britain", "United Kingdom"),
        ("Turkey", "Turkey (Türkiye)"),
        ("Türkiye", "Turkey (Türkiye)"),
    ],
)
def test_known_names_resolve(given: str, expected: str) -> None:
    assert resolve_country(given) == (expected, True)


def test_unknown_names_pass_through_unresolved() -> None:
    assert resolve_country("Narnia") == ("Narnia", False)
