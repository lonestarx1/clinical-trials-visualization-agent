"""A compiled search evaluated over the mirror (design Q22): `to_sql` for the structured clauses,
term sets for the terms. It answers only what it can evaluate exactly; anything else raises
NotInMirror, and the caller answers live.
"""

from typing import Any, cast

from sqlalchemy import ColumnElement, Select, and_, func, not_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.ctgov.compiler import Clause, Search
from app.ctgov.essie import And, Area, Code, Missing, Node, Not, Or, Range
from app.mirror.terms import split
from app.store.models import MirrorTrial, TermMember, TermSet

PS = ("protocolSection",)
DESIGN = (*PS, "designModule")
STATUS = (*PS, "statusModule")
ELIGIBILITY = (*PS, "eligibilityModule")

# Each field a structured clause can name: where it is in the record, and whether it is a list.
FIELDS: dict[str, tuple[tuple[str, ...], bool]] = {
    "Phase": ((*DESIGN, "phases"), True),
    "StudyType": ((*DESIGN, "studyType"), False),
    "DesignAllocation": ((*DESIGN, "designInfo", "allocation"), False),
    "DesignMasking": ((*DESIGN, "designInfo", "maskingInfo", "masking"), False),
    "DesignPrimaryPurpose": ((*DESIGN, "designInfo", "primaryPurpose"), False),
    "OverallStatus": ((*STATUS, "overallStatus"), False),
    "StartDate": ((*STATUS, "startDateStruct", "date"), False),
    "StartDateType": ((*STATUS, "startDateStruct", "type"), False),
    "StudyFirstPostDate": ((*STATUS, "studyFirstPostDateStruct", "date"), False),
    "LastUpdatePostDate": ((*STATUS, "lastUpdatePostDateStruct", "date"), False),
    "LeadSponsorClass": ((*PS, "sponsorCollaboratorsModule", "leadSponsor", "class"), False),
    "StdAge": ((*ELIGIBILITY, "stdAges"), True),
    "Sex": ((*ELIGIBILITY, "sex"), False),
    "HealthyVolunteers": ((*ELIGIBILITY, "healthyVolunteers"), False),
    "HasResults": (("hasResults",), False),
}


class NotInMirror(Exception):
    """The mirror can't evaluate this search exactly (no clauses, an unknown field, no term set)."""


def _day(value: ColumnElement[Any]) -> ColumnElement[str]:
    """A partial date ("2015-03", "2015") as its first day, so it compares like the API's."""
    return func.left(func.concat(value, func.substr("-01-01", func.length(value) - 3)), 10)


def _area(field: str, term: Node) -> ColumnElement[bool]:
    if field not in FIELDS:
        raise NotInMirror(f"the mirror doesn't evaluate {field}")
    path, is_list = FIELDS[field]
    match term:
        case Code(value) if is_list:
            return MirrorTrial.record[path].contains([value])
        case Code(value):
            return cast(ColumnElement[bool], MirrorTrial.record[path].astext == value)
        case Missing():
            return cast(ColumnElement[bool], MirrorTrial.record[path].astext.is_(None))
        case Range(lo, hi) if not is_list:
            day = _day(MirrorTrial.record[path].astext)
            bounds = [MirrorTrial.record[path].astext.is_not(None)]
            if lo != "MIN":
                bounds.append(day >= lo)
            if hi != "MAX":
                bounds.append(day <= hi)
            return and_(*bounds)
    raise NotInMirror(f"the mirror doesn't evaluate {field} {term!r}")


def _sql(node: Node, field: str | None = None) -> ColumnElement[bool]:
    match node:
        case And(items):
            return and_(*(_sql(i, field) for i in items))
        case Or(items):
            return or_(*(_sql(i, field) for i in items))
        case Not(item):
            return not_(_sql(item, field))
        case Area(name, term):
            return _area(name, term)
        case Code() if field is not None:
            return _area(field, node)
    raise NotInMirror(f"the mirror doesn't evaluate {node!r}")


def to_sql(clause: Clause) -> ColumnElement[bool]:
    """One structured clause as a condition on `registry.trials`."""
    field = "OverallStatus" if clause.param == "filter.overallStatus" else None
    return _sql(clause.node, field)


async def _matching(session: AsyncSession, search: Search) -> Select[Any]:
    parts = split(search)
    if parts is None:
        raise NotInMirror("the search has no clauses to evaluate")
    terms, structured = parts
    keys = {t.key for values in terms for t in values}
    if keys:
        known = set(
            await session.scalars(select(TermSet.term_key).where(TermSet.term_key.in_(keys)))
        )
        if missing := keys - known:
            raise NotInMirror(f"no term set for {sorted(missing)}")
    conditions = [to_sql(c) for c in structured]
    for values in terms:  # one filter: any of its terms
        members = select(TermMember.nct_id).where(TermMember.term_key.in_([t.key for t in values]))
        conditions.append(MirrorTrial.nct_id.in_(members))
    return select(MirrorTrial).where(and_(true(), *conditions))


async def matching_ids(session: AsyncSession, search: Search) -> set[str]:
    query = (await _matching(session, search)).with_only_columns(MirrorTrial.nct_id)
    return set(await session.scalars(query))


async def count(session: AsyncSession, search: Search) -> int:
    query = (await _matching(session, search)).with_only_columns(func.count())
    return int(await session.scalar(query) or 0)


async def records(session: AsyncSession, search: Search) -> list[dict[str, Any]]:
    query = (await _matching(session, search)).with_only_columns(MirrorTrial.record)
    return list(await session.scalars(query.order_by(MirrorTrial.nct_id)))
