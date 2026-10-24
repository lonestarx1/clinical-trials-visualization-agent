"""Country names -> the API's canonical LocationCountry values (design Q7, D7.3).

Location fields have no synonym expansion in the API, so aliases are resolved
here by a fixed table, never by the AI.
"""

import json
from pathlib import Path

CANONICAL: tuple[str, ...] = tuple(
    json.loads((Path(__file__).parent / "data" / "location-countries.json").read_text())["values"]
)

# The API spells it with a typographic apostrophe (U+2019).
_IVORY_COAST = "C\u00f4te d\u2019Ivoire"

ALIASES: dict[str, str] = {
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "united states of america": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "korea, republic of": "South Korea",
    "dprk": "North Korea",
    "turkey": "Turkey (Türkiye)",
    "türkiye": "Turkey (Türkiye)",
    "turkiye": "Turkey (Türkiye)",
    "russian federation": "Russia",
    "czech republic": "Czechia",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
    "uae": "United Arab Emirates",
    "prc": "China",
    "mainland china": "China",
    "viet nam": "Vietnam",
    "ivory coast": _IVORY_COAST,
    "cote d'ivoire": _IVORY_COAST,
    "côte d'ivoire": _IVORY_COAST,
    "iran, islamic republic of": "Iran",
    "drc": "Democratic Republic of the Congo",
}

_BY_LOWER = {name.lower(): name for name in CANONICAL} | ALIASES


def resolve_country(name: str) -> tuple[str, bool]:
    """(canonical name, True) if known; otherwise (name unchanged, False)."""
    found = _BY_LOWER.get(" ".join(name.split()).lower())
    return (found, True) if found else (name, False)
