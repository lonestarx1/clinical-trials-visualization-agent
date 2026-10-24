"""Stored results and their full citation lists (design Q14, Q16)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.response import SCHEMA_VERSION
from app.store.models import DataVersion, Result, ResultCitation, ResultDatum

CODE_VERSION = "0.4.0"
_CHUNK = 2000


class NotFound(LookupError):
    pass


class Expired(LookupError):
    pass


@dataclass
class Datum:
    key: str
    label: str
    value: float | None
    citations: list[dict[str, Any]]  # every contributing trial, in citation order


@dataclass
class CitationPage:
    result_id: uuid.UUID
    datum_key: str
    label: str
    citation_count: int
    citations: list[dict[str, Any]]
    next_cursor: int | None


def _ts(data_timestamp: str) -> datetime:
    return datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC)


async def remember_version(
    session: AsyncSession, data_timestamp: str, api_version: str
) -> datetime:
    ts = _ts(data_timestamp)
    await session.execute(
        pg_insert(DataVersion)
        .values(data_timestamp=ts, api_version=api_version)
        .on_conflict_do_update(
            index_elements=["data_timestamp"], set_={"last_checked_at": datetime.now(UTC)}
        )
    )
    return ts


async def save_result(
    session: AsyncSession,
    *,
    result_key: str,
    response: dict[str, Any],
    request: dict[str, Any],
    plan: dict[str, Any],
    datums: list[Datum],
    searches: list[dict[str, Any]],
    data_timestamp: str | None,
    api_version: str,
    ttl: timedelta,
) -> uuid.UUID:
    result_id = uuid.UUID(response["result_id"]) if response.get("result_id") else uuid.uuid4()
    verified = (
        await remember_version(session, data_timestamp, api_version) if data_timestamp else None
    )
    session.add(
        Result(
            result_id=result_id,
            result_key=result_key,
            status=response["status"],
            request=request,
            plan=plan,
            response=response,
            searches=searches,
            verified_data_ts=verified,
            schema_version=SCHEMA_VERSION,
            code_version=CODE_VERSION,
            expires_at=datetime.now(UTC) + ttl,
        )
    )
    await session.flush()
    if datums:
        await session.execute(
            insert(ResultDatum),
            [
                {
                    "result_id": result_id,
                    "datum_key": d.key,
                    "label": d.label,
                    "value": d.value,
                    "citation_count": len(d.citations),
                }
                for d in datums
            ],
        )
        rows = [
            {
                "result_id": result_id,
                "datum_key": d.key,
                "rank": rank,
                "nct_id": c["nct_id"],
                "title": c.get("title"),
                "evidence": c["evidence"],
            }
            for d in datums
            for rank, c in enumerate(d.citations)
        ]
        for start in range(0, len(rows), _CHUNK):
            await session.execute(insert(ResultCitation), rows[start : start + _CHUNK])
    return result_id


async def _live_result(session: AsyncSession, result_id: uuid.UUID) -> Result:
    result = await session.get(Result, result_id)
    if result is None:
        raise NotFound(f"no result {result_id}")
    if result.expires_at <= datetime.now(UTC):
        raise Expired(f"result {result_id} has expired")
    return result


async def citation_page(
    session: AsyncSession, result_id: uuid.UUID, datum_key: str, *, after: int | None, limit: int
) -> CitationPage:
    """Keyset pagination on (result_id, datum_key, rank): no OFFSET scans."""
    await _live_result(session, result_id)
    datum = await session.get(ResultDatum, (result_id, datum_key))
    if datum is None:
        raise NotFound(f"no data point {datum_key!r} in result {result_id}")
    start = -1 if after is None else after - 1
    rows = (
        await session.scalars(
            select(ResultCitation)
            .where(
                ResultCitation.result_id == result_id,
                ResultCitation.datum_key == datum_key,
                ResultCitation.rank > start,
            )
            .order_by(ResultCitation.rank)
            .limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    return CitationPage(
        result_id,
        datum_key,
        datum.label,
        datum.citation_count,
        [
            {
                "rank": r.rank,
                "nct_id": r.nct_id,
                "url": f"https://clinicaltrials.gov/study/{r.nct_id}",
                "title": r.title,
                "evidence": r.evidence,
            }
            for r in page
        ],
        rows[limit].rank if len(rows) > limit else None,
    )


async def latest_valid(session: AsyncSession, result_key: str) -> Result | None:
    return await session.scalar(
        select(Result)
        .where(Result.result_key == result_key, Result.expires_at > datetime.now(UTC))
        .order_by(Result.created_at.desc())
        .limit(1)
    )


async def restamp(
    session: AsyncSession, result_id: uuid.UUID, data_timestamp: str, api_version: str
) -> None:
    ts = await remember_version(session, data_timestamp, api_version)
    await session.execute(
        update(Result).where(Result.result_id == result_id).values(verified_data_ts=ts)
    )


async def expire_now(session: AsyncSession, result_id: uuid.UUID) -> None:
    await session.execute(
        update(Result).where(Result.result_id == result_id).values(expires_at=datetime.now(UTC))
    )


async def delete(session: AsyncSession, result_id: uuid.UUID) -> None:
    await session.execute(sql_delete(Result).where(Result.result_id == result_id))
