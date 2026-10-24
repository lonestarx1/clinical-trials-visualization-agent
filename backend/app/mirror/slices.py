"""Start-year slices of the whole registry, and what the mirror stores (design Q22).

Page tokens make one search's pages strictly sequential, so the first load pages each
slice on its own. Comparing counts per slice also finds removed trials.
"""

from dataclasses import dataclass
from typing import Any

from app.ctgov.compiler import Search
from app.ctgov.essie import Area, Missing, Node, Range, to_essie
from app.registry import BASE_FIELDS, DIMENSIONS, MEASURES

FIRST_YEAR = 2000  # earlier years are thin: one slice
YEARS_AHEAD = 2  # planned trials start in the future


@dataclass(frozen=True)
class YearSlice:
    lo: int | None  # None: from the earliest date
    hi: int | None  # None: to the latest date
    missing: bool = False  # trials without a start date

    def clause(self) -> Node:
        if self.missing:
            return Area("StartDate", Missing())
        lo = f"{self.lo}-01-01" if self.lo is not None else "MIN"
        hi = f"{self.hi}-12-31" if self.hi is not None else "MAX"
        return Area("StartDate", Range(lo, hi))

    def search(self) -> Search:
        return Search({"filter.advanced": to_essie(self.clause())})

    def holds(self, year: int | None) -> bool:
        if year is None or self.missing:
            return year is None and self.missing
        return (self.lo is None or year >= self.lo) and (self.hi is None or year <= self.hi)


def year_slices(now_year: int) -> list[YearSlice]:
    last = now_year + YEARS_AHEAD
    return [
        YearSlice(None, FIRST_YEAR - 1),
        *(YearSlice(y, y) for y in range(FIRST_YEAR, last + 1)),
        YearSlice(last + 1, None),
        YearSlice(None, None, missing=True),
    ]


def start_year(study: dict[str, Any]) -> int | None:
    date = study["protocolSection"].get("statusModule", {}).get("startDateStruct", {}).get("date")
    return int(date[:4]) if date else None


def mirror_fields() -> list[str]:
    """Every API field the registry reads, plus the date the daily update filters on."""
    pieces = [*BASE_FIELDS]
    pieces += [f for d in DIMENSIONS.values() for f in d.fields]
    pieces += [f for m in MEASURES.values() for f in m.fields]
    return list(dict.fromkeys([*pieces, "LastUpdatePostDate"]))
