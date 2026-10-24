"""Retrieval building blocks (design Q6): which fields to fetch, and exact counts per bucket."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.ctgov.client import InconsistentResults
from app.ctgov.compiler import Search
from app.ctgov.essie import Area, Code, Missing
from app.registry import BASE_FIELDS, DIMENSIONS, MEASURES, Dimension
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
