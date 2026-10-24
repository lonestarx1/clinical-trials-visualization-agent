"""Retrieval building blocks (design Q6): which fields to fetch, and exact counts per bucket."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.ctgov.client import InconsistentResults
from app.ctgov.compiler import Search
from app.ctgov.essie import Area, Code, Missing, Range
from app.registry import BASE_FIELDS, DIMENSIONS, MEASURES, Dimension, DimensionKind
from app.schemas.plan import QueryPlan


class Counter(Protocol):
    async def count(self, search: Search) -> int: ...


def fields_for(plan: QueryPlan) -> list[str]:
    """API pieces needed for this plan: citation basics, dimensions, then the measure."""
    pieces = list(BASE_FIELDS)
    for key in (plan.dimension, plan.dimension_2):
        if key:
            pieces += DIMENSIONS[key].fields
    pieces += MEASURES[plan.measure].fields
    if plan.options.count_entity:
        pieces += DIMENSIONS[plan.options.count_entity].fields
    return list(dict.fromkeys(pieces))


@dataclass(frozen=True)
class BucketCounts:
    total: int
    buckets: dict[str, int]  # enum code -> number of matching trials
    missing: int  # trials with no value for the dimension


async def count_per_bucket(counter: Counter, search: Search, dimension: Dimension) -> BucketCounts:
    """Strategy S2: one count call per enum value, plus one for trials with no value.

    Exact without downloading trials. For single-valued dimensions the buckets
    must add up to the total; otherwise the counts are inconsistent and rejected.
    """
    if dimension.enum is None or dimension.filter_piece is None:
        raise ValueError(
            f"{dimension.key} is not a bounded dimension; it can't be counted per bucket"
        )
    piece = dimension.filter_piece
    values = [member.value for member in dimension.enum]
    total, missing, *per_value = await asyncio.gather(
        counter.count(search),
        counter.count(search.narrow(Area(piece, Missing()))),
        *(counter.count(search.narrow(Area(piece, Code(v)))) for v in values),
    )
    buckets = dict(zip(values, per_value, strict=True))
    if not dimension.multi_valued and sum(buckets.values()) + missing != total:
        raise InconsistentResults(
            f"{dimension.key} buckets add up to {sum(buckets.values()) + missing}, "
            f"but the total is {total}"
        )
    return BucketCounts(total, buckets, missing)


# Date fields whose value can be an estimate, by time dimension.
DATE_TYPE_PIECE = {"start_year": "StartDateType"}


@dataclass(frozen=True)
class YearCounts:
    within: int  # trials dated anywhere in the span
    years: dict[int, int]  # year -> trials dated that year
    estimated: dict[int, int]  # year -> of those, trials whose date is an estimate


def _years(lo: int, hi: int) -> Range:
    return Range(f"{lo}-01-01", f"{hi}-12-31")


async def count_per_year(
    counter: Counter, search: Search, dimension: Dimension, span: tuple[int, int]
) -> YearCounts:
    """Strategy S2 for a time dimension: one count per year (and per year with an estimated date).

    Exact without downloading trials. The years must add up to the count for the whole span.
    """
    if dimension.kind is not DimensionKind.TIME or dimension.filter_piece is None:
        raise ValueError(f"{dimension.key} is not a time dimension")
    piece, (lo, hi) = dimension.filter_piece, span
    years = list(range(lo, hi + 1))
    per_year = [search.narrow(Area(piece, _years(y, y))) for y in years]
    type_piece = DATE_TYPE_PIECE.get(dimension.key)
    estimated_searches = (
        [s.narrow(Area(type_piece, Code("ESTIMATED"))) for s in per_year] if type_piece else []
    )
    within, *counts = await asyncio.gather(
        counter.count(search.narrow(Area(piece, _years(lo, hi)))),
        *(counter.count(s) for s in [*per_year, *estimated_searches]),
    )
    by_year = dict(zip(years, counts[: len(years)], strict=True))
    estimated = dict(zip(years, counts[len(years) :] or [0] * len(years), strict=True))
    if sum(by_year.values()) != within:
        raise InconsistentResults(
            f"{dimension.key} years add up to {sum(by_year.values())}, but the span has {within}"
        )
    return YearCounts(within, by_year, estimated)
