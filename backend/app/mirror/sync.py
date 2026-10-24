"""Keep the mirror in step with ClinicalTrials.gov (design Q22): a first load, then daily updates.

The last succeeded run's data timestamp is the mirror's, so a run that fails or stops part way
never marks the mirror current. An update saves the changed trials, reconciles the slices whose
counts differ, and checks the total, all in one transaction.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ctgov.client import CtgovClient, InconsistentResults
from app.ctgov.compiler import Search
from app.ctgov.essie import Area, Range, to_essie
from app.mirror.slices import YearSlice, mirror_fields, year_slices
from app.store import mirror

OVERLAP = timedelta(days=3)  # LastUpdatePostDate is a date: fetch a few days again, to be safe
RELOAD_AFTER = timedelta(days=7)  # a mirror this far behind is loaded again from scratch
LOAD_CONCURRENCY = 4  # slices paged at once; the sync's own limiter sets the pace
EVERYTHING = Search({})

Sessions = async_sessionmaker[AsyncSession]


class MirrorMismatch(InconsistentResults):
    """After a sync, the mirror's number of trials differs from the API's total."""


@dataclass(frozen=True)
class SyncResult:
    kind: str  # load | update
    data_timestamp: str
    upserted: int
    removed: int


def _ts(data_timestamp: str) -> datetime:
    return datetime.fromisoformat(data_timestamp).replace(tzinfo=UTC)


def _nct_id(study: dict[str, Any]) -> str:
    return str(study["protocolSection"]["identificationModule"]["nctId"])


def changed_since(day: date) -> Search:
    clause = Area("LastUpdatePostDate", Range(day.isoformat(), "MAX"))
    return Search({"filter.advanced": to_essie(clause)})


async def sync(
    ctgov: CtgovClient, sessions: Sessions, *, now: datetime | None = None
) -> SyncResult | None:
    """Bring the mirror up to the API's current data. None when it already is."""
    now = now or datetime.now(UTC)
    version = await ctgov.version()
    async with sessions() as s:
        last = await mirror.last_success(s)
    if last is not None and last.data_timestamp >= _ts(version.data_timestamp):
        return None
    since = None
    if last is not None and now - last.started_at <= RELOAD_AFTER:
        since = (last.started_at - OVERLAP).date()
    kind = "update" if since else "load"
    async with sessions() as s:
        await mirror.close_interrupted(s)
        run_id = await mirror.start_run(
            s, kind=kind, data_timestamp=version.data_timestamp, since=since
        )
        await s.commit()
    try:
        if since is None:
            return await _load(ctgov, sessions, run_id, version.data_timestamp, now)
        return await _update(ctgov, sessions, run_id, version.data_timestamp, since, now)
    except Exception as exc:
        async with sessions() as s:
            await mirror.finish_run(
                s, run_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:2000]
            )
            await s.commit()
        raise


async def _update(
    ctgov: CtgovClient,
    sessions: Sessions,
    run_id: int,
    data_timestamp: str,
    since: date,
    now: datetime,
) -> SyncResult:
    async with sessions() as s:
        upserted = await _save_pages(ctgov, s, changed_since(since))
        removed, repaired = await _reconcile(ctgov, s, now.year)
        await _check_total(ctgov, s)
        await mirror.finish_run(
            s, run_id, status="succeeded", upserted=upserted + repaired, removed=removed
        )
        await s.commit()
    return SyncResult("update", data_timestamp, upserted + repaired, removed)


async def _load(
    ctgov: CtgovClient, sessions: Sessions, run_id: int, data_timestamp: str, now: datetime
) -> SyncResult:
    """Every slice, page by page (one commit per page); then catch up, reconcile and check.

    A slice the mirror already holds in full (an interrupted load, or a mirror copied from
    another database) is kept, after one count call; the catch-up then refetches every trial
    changed since the oldest one saved, so kept slices end on this data too.
    """
    gate = asyncio.Semaphore(LOAD_CONCURRENCY)
    kept: list[YearSlice] = []
    async with sessions() as s:
        oldest = await mirror.oldest_sync(s)

    async def load_slice(sl: YearSlice) -> int:
        saved = 0
        async with gate:
            async with sessions() as s:
                have = await mirror.count_in(s, sl)
            if have and have == await ctgov.count(sl.search()):
                kept.append(sl)
                return 0
            async for studies, _ in ctgov.pages(sl.search(), mirror_fields()):
                async with sessions() as s:
                    saved += await mirror.upsert_trials(s, studies)
                    await s.commit()
        return saved

    async with asyncio.TaskGroup() as group:  # one slice failing cancels the others
        tasks = [group.create_task(load_slice(sl)) for sl in year_slices(now.year)]
    upserted = sum(t.result() for t in tasks)

    latest = await ctgov.version()
    catch_up = []
    if latest.data_timestamp != data_timestamp:  # an update was published during the load
        catch_up.append((now - OVERLAP).date())
    if kept and oldest is not None:  # kept slices were saved earlier, maybe from older data
        catch_up.append((oldest - OVERLAP).date())
    async with sessions() as s:
        if catch_up:
            upserted += await _save_pages(ctgov, s, changed_since(min(catch_up)))
        removed, repaired = await _reconcile(ctgov, s, now.year)
        await _check_total(ctgov, s)
        await mirror.finish_run(
            s,
            run_id,
            status="succeeded",
            upserted=upserted + repaired,
            removed=removed,
            data_timestamp=latest.data_timestamp,
        )
        await s.commit()
    return SyncResult("load", latest.data_timestamp, upserted + repaired, removed)


async def _save_pages(ctgov: CtgovClient, session: AsyncSession, search: Search) -> int:
    saved = 0
    async for studies, _ in ctgov.pages(search, mirror_fields()):
        saved += await mirror.upsert_trials(session, studies)
    return saved


async def _reconcile(ctgov: CtgovClient, session: AsyncSession, now_year: int) -> tuple[int, int]:
    """Make every start-year slice hold the API's trials. Returns (removed, saved again).

    Only slices whose counts differ are listed by ID. A trial removed and another added in the
    same slice leave the counts equal; the weekly full re-sync is the net for that.
    """
    if await mirror.count_trials(session) == await ctgov.count(EVERYTHING):
        return 0, 0
    slices = year_slices(now_year)
    live_counts = await asyncio.gather(*(ctgov.count(sl.search()) for sl in slices))
    removed = saved = 0
    for sl, live in zip(slices, live_counts, strict=True):
        if await mirror.count_in(session, sl) == live:
            continue
        live_ids: set[str] = set()
        async for studies, _ in ctgov.pages(sl.search(), ["NCTId"]):
            live_ids.update(_nct_id(study) for study in studies)
        local = await mirror.ids_in(session, sl)
        removed += await mirror.delete_trials(session, local - live_ids)
        if live_ids - local:  # changed without a new LastUpdatePostDate (O5): save the slice again
            saved += await _save_pages(ctgov, session, sl.search())
    return removed, saved


async def _check_total(ctgov: CtgovClient, session: AsyncSession) -> None:
    have, live = await mirror.count_trials(session), await ctgov.count(EVERYTHING)
    if have != live:
        raise MirrorMismatch(f"the mirror has {have} trials, ClinicalTrials.gov {live}")
