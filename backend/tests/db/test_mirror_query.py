"""A compiled search evaluated over the mirror (design Q22): structured clauses in SQL, terms from
term sets. Run with: make test-db."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ctgov.compiler import Search, compile_filters
from app.ctgov.essie import Area, Code, Range
from app.mirror import query
from app.mirror.terms import Term
from app.schemas.plan import Filters
from app.store import mirror
from app.store import terms as term_store

pytestmark = pytest.mark.db
Sessions = async_sessionmaker[AsyncSession]
TS = "2026-10-23T09:00:04"


def study(nct: str, **f: Any) -> dict[str, Any]:
    design: dict[str, Any] = {"studyType": f.get("type", "INTERVENTIONAL")}
    if "phases" in f:
        design["phases"] = f["phases"]
    design["designInfo"] = {
        "allocation": f.get("allocation", "RANDOMIZED"),
        "maskingInfo": {"masking": f.get("masking", "NONE")},
        "primaryPurpose": f.get("purpose", "TREATMENT"),
    }
    status: dict[str, Any] = {"overallStatus": f.get("status", "COMPLETED")}
    if f.get("start"):
        status["startDateStruct"] = {"date": f["start"], "type": f.get("start_type", "ACTUAL")}
    eligibility: dict[str, Any] = {"sex": f.get("sex", "ALL"), "stdAges": f.get("ages", ["ADULT"])}
    if "healthy" in f:
        eligibility["healthyVolunteers"] = f["healthy"]
    return {
        "hasResults": f.get("results", False),
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": nct},
            "designModule": design,
            "statusModule": status,
            "eligibilityModule": eligibility,
            "sponsorCollaboratorsModule": {"leadSponsor": {"class": f.get("cls", "INDUSTRY")}},
        },
    }


TRIALS = [
    study("NCT1", phases=["PHASE2"], start="2015-03", status="RECRUITING", healthy=True),
    study("NCT2", phases=["PHASE2", "PHASE3"], start="2016-11-02", results=True, cls="NIH"),
    study("NCT3", phases=["PHASE1"], start="2014", start_type="ESTIMATED", sex="FEMALE"),
    study("NCT4", type="OBSERVATIONAL", start=None, ages=["CHILD", "ADULT"], healthy=False),
    study("NCT5", phases=["PHASE3"], start="2015-12-31", masking="DOUBLE", purpose="PREVENTION"),
]


@pytest.fixture
async def loaded(sessions: Sessions) -> Sessions:
    async with sessions() as s:
        await mirror.upsert_trials(s, TRIALS)
        await s.commit()
    return sessions


def search(**filters: Any) -> Search:
    return compile_filters(Filters.model_validate(filters))


async def ids(sessions: Sessions, s: Search) -> set[str]:
    async with sessions() as session:
        return await query.matching_ids(session, s)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, {"NCT1", "NCT2", "NCT3", "NCT4", "NCT5"}),
        ({"phases": ["PHASE2"]}, {"NCT1", "NCT2"}),
        ({"phases": ["PHASE2", "PHASE3"]}, {"NCT1", "NCT2", "NCT5"}),
        ({"statuses": ["RECRUITING", "COMPLETED"]}, {"NCT1", "NCT2", "NCT3", "NCT4", "NCT5"}),
        ({"statuses": ["RECRUITING"]}, {"NCT1"}),
        ({"study_types": ["OBSERVATIONAL"]}, {"NCT4"}),
        ({"sponsor_classes": ["NIH"]}, {"NCT2"}),
        ({"age_groups": ["CHILD"]}, {"NCT4"}),
        ({"sexes": ["FEMALE"]}, {"NCT3"}),
        # Measured (live cross-check): the API's AREA[Sex]ALL matches every trial.
        ({"sexes": ["ALL"]}, {"NCT1", "NCT2", "NCT3", "NCT4", "NCT5"}),
        ({"sexes": ["ALL"], "phases": ["PHASE1"]}, {"NCT3"}),
        ({"healthy_volunteers": True}, {"NCT1"}),
        ({"healthy_volunteers": False}, {"NCT4"}),
        ({"has_results": True}, {"NCT2"}),
        ({"maskings": ["DOUBLE"]}, {"NCT5"}),
        ({"primary_purposes": ["PREVENTION"]}, {"NCT5"}),
        ({"allocations": ["RANDOMIZED"]}, {"NCT1", "NCT2", "NCT3", "NCT4", "NCT5"}),
        ({"start_year_min": 2015}, {"NCT1", "NCT2", "NCT5"}),  # no start date: excluded
        ({"start_year_min": 2015, "start_year_max": 2015}, {"NCT1", "NCT5"}),
        ({"start_year_max": 2014}, {"NCT3"}),  # "2014" alone counts as 2014
        ({"phases": ["PHASE2"], "start_year_min": 2016}, {"NCT2"}),
    ],
)
async def test_structured_filters_select_the_same_trials_as_the_api_would(
    loaded: Sessions, filters: dict[str, Any], expected: set[str]
) -> None:
    assert await ids(loaded, search(**filters)) == expected


async def test_narrowed_searches_are_evaluated_too(loaded: Sessions) -> None:
    s = search().narrow(Area("StartDate", Range("2015-01-01", "2015-12-31")))
    assert await ids(loaded, s) == {"NCT1", "NCT5"}
    estimated = search().narrow(Area("StartDateType", Code("ESTIMATED")))
    assert await ids(loaded, estimated) == {"NCT3"}


async def test_terms_come_from_term_sets(loaded: Sessions) -> None:
    melanoma, glioma = Term("query.cond", '"melanoma"'), Term("query.cond", '"glioma"')
    async with loaded() as s:
        for term, members in ((melanoma, {"NCT1", "NCT2", "NCT9"}), (glioma, {"NCT5"})):
            await term_store.save(
                s,
                term_key=term.key,
                param=term.param,
                expression=term.expression,
                ids=members,
                old=set(),
                data_timestamp=TS,
                checked_at=datetime.now(UTC),
                resolved_at=datetime.now(UTC),
            )
        await s.commit()
    assert await ids(loaded, search(conditions=["melanoma"])) == {"NCT1", "NCT2"}  # NCT9: gone
    assert await ids(loaded, search(conditions=["melanoma", "glioma"])) == {"NCT1", "NCT2", "NCT5"}
    assert await ids(loaded, search(conditions=["melanoma"], phases=["PHASE3"])) == {"NCT2"}
    async with loaded() as s:
        assert await query.count(s, search(conditions=["melanoma"])) == 2
        records = await query.records(s, search(conditions=["glioma"]))
    assert [r["protocolSection"]["identificationModule"]["nctId"] for r in records] == ["NCT5"]


async def test_a_term_without_a_set_cannot_be_answered(loaded: Sessions) -> None:
    async with loaded() as s:
        with pytest.raises(query.NotInMirror):
            await query.matching_ids(s, search(conditions=["melanoma"]))


async def test_a_search_without_clauses_cannot_be_answered(loaded: Sessions) -> None:
    async with loaded() as s:
        with pytest.raises(query.NotInMirror):
            await query.matching_ids(s, Search({"query.cond": '"melanoma"'}))
        with pytest.raises(query.NotInMirror):  # a field the mirror can't evaluate
            await query.matching_ids(
                s, search().narrow(Area("CompletionDate", Range("2015-01-01", "MAX")))
            )
