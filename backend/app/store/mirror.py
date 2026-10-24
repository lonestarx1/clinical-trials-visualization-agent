"""The mirror of ClinicalTrials.gov (design Q22): trials, slice counts, sync runs, the lock."""

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, func, select, text, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.mirror.slices import YearSlice, start_year
from app.store.models import MirrorTrial, SyncRun

SYNC_LOCK = 2_200_001  # pg advisory lock key: one sync at a time, across pods
UPSERT_BATCH = 1000


def _ts(data_timestamp: str) -> datetime:
    return datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC)


def _row(study: dict[str, Any]) -> dict[str, Any]:
    section = study["protocolSection"]
    updated = section.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date")
    return {
        "nct_id": section["identificationModule"]["nctId"],
        "record": study,
        "start_year": start_year(study),
        "last_update_post_date": date.fromisoformat(updated) if updated else None,
        "synced_at": datetime.now(UTC),
    }


async def upsert_trials(session: AsyncSession, studies: list[dict[str, Any]]) -> int:
    """Insert or replace each study by NCT ID. Returns the number of studies saved."""
    rows = list({r["nct_id"]: r for r in map(_row, studies)}.values())
    for i in range(0, len(rows), UPSERT_BATCH):
        stmt = pg_insert(MirrorTrial).values(rows[i : i + UPSERT_BATCH])
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["nct_id"],
                set_={c: stmt.excluded[c] for c in rows[0] if c != "nct_id"},
            )
        )
    return len(rows)


def _in(sl: YearSlice) -> ColumnElement[bool]:
    year = MirrorTrial.start_year
    if sl.missing:
        return year.is_(None)
    lo = year >= sl.lo if sl.lo is not None else true()
    hi = year <= sl.hi if sl.hi is not None else true()
    return and_(year.is_not(None), lo, hi)


async def count_trials(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(MirrorTrial)) or 0)


async def count_in(session: AsyncSession, sl: YearSlice) -> int:
    query = select(func.count()).select_from(MirrorTrial).where(_in(sl))
    return int(await session.scalar(query) or 0)


async def ids_in(session: AsyncSession, sl: YearSlice) -> set[str]:
    return set(await session.scalars(select(MirrorTrial.nct_id).where(_in(sl))))


async def changed_since(session: AsyncSession, day: date) -> set[str]:
    """Trials whose LastUpdatePostDate is on or after `day`."""
    query = select(MirrorTrial.nct_id).where(MirrorTrial.last_update_post_date >= day)
    return set(await session.scalars(query))


async def delete_trials(session: AsyncSession, nct_ids: Iterable[str]) -> int:
    ids = list(nct_ids)
    if not ids:
        return 0
    result = await session.execute(delete(MirrorTrial).where(MirrorTrial.nct_id.in_(ids)))
    return int(result.rowcount)  # type: ignore[attr-defined]


async def start_run(
    session: AsyncSession, *, kind: str, data_timestamp: str, since: date | None = None
) -> int:
    run = SyncRun(kind=kind, data_timestamp=_ts(data_timestamp), since=since)
    session.add(run)
    await session.flush()
    return run.run_id


async def finish_run(
    session: AsyncSession,
    run_id: int,
    *,
    status: str,
    upserted: int = 0,
    removed: int = 0,
    error: str | None = None,
    data_timestamp: str | None = None,
) -> None:
    """Close a run. `data_timestamp` replaces the run's when it caught up to newer data."""
    values: dict[str, Any] = {
        "status": status,
        "upserted": upserted,
        "removed": removed,
        "error": error,
        "finished_at": datetime.now(UTC),
    }
    if data_timestamp is not None:
        values["data_timestamp"] = _ts(data_timestamp)
    await session.execute(update(SyncRun).where(SyncRun.run_id == run_id).values(**values))


async def oldest_sync(session: AsyncSession) -> datetime | None:
    """When the mirror's least recently saved trial was saved; None for an empty mirror."""
    oldest: datetime | None = await session.scalar(select(func.min(MirrorTrial.synced_at)))
    return oldest


async def close_interrupted(session: AsyncSession) -> int:
    """Mark runs still `running` as failed: the sync lock is held, so their process stopped."""
    result = await session.execute(
        update(SyncRun)
        .where(SyncRun.status == "running")
        .values(
            status="failed",
            error="interrupted: the process stopped before the run finished",
            finished_at=datetime.now(UTC),
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def last_success(session: AsyncSession) -> SyncRun | None:
    """The run that made the mirror current: its data timestamp is the mirror's."""
    return await session.scalar(
        select(SyncRun)
        .where(SyncRun.status == "succeeded")
        .order_by(SyncRun.finished_at.desc())
        .limit(1)
    )


async def try_lock(conn: AsyncConnection) -> bool:
    """Take the sync lock on this connection, if no other connection holds it."""
    return bool(await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": SYNC_LOCK}))


async def unlock(conn: AsyncConnection) -> None:
    await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SYNC_LOCK})
