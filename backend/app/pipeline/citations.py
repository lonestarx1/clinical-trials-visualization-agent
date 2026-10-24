"""Per-datum citations and the exactness check (design Q14)."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from app.pipeline.extract import Evidence, parse_partial_date, value_at
from app.schemas.response import Visualization

STUDY_URL = "https://clinicaltrials.gov/study/{}"


class CitationMismatch(AssertionError):
    """A citation excerpt doesn't match its record. Always a bug: fail loudly."""


def _recency(study: dict[str, Any], nct_id: str) -> tuple[int, int, str]:
    """Most recent start first, trials without a start date last, then by NCT ID."""
    start: date | None = parse_partial_date(
        value_at(study, "protocolSection.statusModule.startDateStruct.date")
    )
    return (0, -start.toordinal(), nct_id) if start else (1, 0, nct_id)


def ordered_trials(nct_ids: Iterable[str], studies: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(nct_ids, key=lambda i: _recency(studies[i], i))


def citation(study: dict[str, Any], evidence: Sequence[Evidence]) -> dict[str, Any]:
    nct_id = value_at(study, "protocolSection.identificationModule.nctId")
    return {
        "nct_id": nct_id,
        "url": STUDY_URL.format(nct_id),
        "title": value_at(study, "protocolSection.identificationModule.briefTitle"),
        "evidence": [{"field": e.field, "excerpt": e.excerpt} for e in evidence],
    }


def sample_citations(
    evidence_by_trial: Mapping[str, Sequence[Evidence]],
    studies: dict[str, dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    """`citation_count`, up to `limit` citations in a fixed order, and `citations_truncated`."""
    chosen = ordered_trials(evidence_by_trial, studies)[:limit]
    return {
        "citation_count": len(evidence_by_trial),
        "citations": [citation(studies[i], evidence_by_trial[i]) for i in chosen],
        "citations_truncated": len(evidence_by_trial) > limit,
    }


def _points(visualization: Visualization) -> list[dict[str, Any]]:
    data: Any = visualization.data
    if isinstance(data, dict):  # network graphs
        return [*data.get("nodes", []), *data.get("edges", [])]
    return list(data)


def verify_citations(visualization: Visualization, studies: dict[str, dict[str, Any]]) -> None:
    """Every excerpt must equal the value at its path in the record we fetched."""
    for point in _points(visualization):
        for cited in point.get("citations", []):
            study = studies.get(cited["nct_id"])
            if study is None:
                raise CitationMismatch(f"{cited['nct_id']} is cited but was not retrieved")
            for item in cited["evidence"]:
                actual = value_at(study, item["field"])
                expected = item["excerpt"]
                matches = actual in (None, [], "") if expected is None else actual == expected
                if not matches:
                    raise CitationMismatch(
                        f"{cited['nct_id']} {item['field']}: "
                        f"cited {expected!r}, record has {actual!r}"
                    )
