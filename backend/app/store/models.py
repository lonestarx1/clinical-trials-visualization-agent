"""Postgres tables (design Q16). Built: data versions, plan cache (L2), results (L3) with
datums and full citations, jobs, and LLM usage. Not built: the page-level API cache (L1)
and the traces table (traces stay in logs and meta).

The `registry` schema holds the mirror of ClinicalTrials.gov (design Q22): trials, sync runs and
term sets (the trials each search term matches, as resolved by the API).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _now() -> Any:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DataVersion(Base):
    __tablename__ = "data_versions"

    data_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    api_version: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = _now()
    last_checked_at: Mapped[datetime] = _now()


class PlanCache(Base):
    __tablename__ = "plan_cache"

    request_key: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    planner_version: Mapped[str] = mapped_column(Text)
    plan: Mapped[dict[str, Any]]
    planner_trace: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _now()
    last_used_at: Mapped[datetime] = _now()
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Result(Base):
    """Immutable final responses; `result_id` is returned to clients."""

    __tablename__ = "results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok','no_matching_trials','out_of_scope','could_not_interpret')",
            name="results_status",
        ),
        Index("results_key_created", "result_key", text("created_at DESC")),
        Index("results_expires", "expires_at"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    result_key: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(Text)
    request: Mapped[dict[str, Any]]
    plan: Mapped[dict[str, Any]]
    response: Mapped[dict[str, Any]]
    searches: Mapped[list[Any]]  # [{"params": {...}, "total_count": n}] for revalidation
    verified_data_ts: Mapped[datetime | None] = mapped_column(
        ForeignKey("data_versions.data_timestamp")
    )
    schema_version: Mapped[str] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResultDatum(Base):
    __tablename__ = "result_datums"

    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("results.result_id", ondelete="CASCADE"), primary_key=True
    )
    datum_key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float)
    citation_count: Mapped[int] = mapped_column(Integer)
    # When the answer read only a sample: the API search listing every trial, the token of
    # its next unread page, and whether every page has been stored (design Q14).
    source: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    next_page_token: Mapped[str | None] = mapped_column(Text)
    complete: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class ResultCitation(Base):
    """Full citation list per data point, keyset-paginated by rank (design Q14)."""

    __tablename__ = "result_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_id", "datum_key"],
            ["result_datums.result_id", "result_datums.datum_key"],
            ondelete="CASCADE",
        ),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    datum_key: Mapped[str] = mapped_column(Text, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    nct_id: Mapped[str] = mapped_column(CHAR(11))
    title: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[Any]]


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')", name="jobs_status"
        ),
        Index(
            "jobs_one_active_per_request",
            "request_key",
            unique=True,
            postgresql_where=text("status IN ('pending','running')"),
        ),
        Index("jobs_pickup", "status", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_key: Mapped[str] = mapped_column(CHAR(64))
    request: Mapped[dict[str, Any]]
    plan: Mapped[dict[str, Any]]
    context: Mapped[dict[str, Any]]  # meta from the synchronous part (guard, planner, warnings)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    estimated_seconds: Mapped[int] = mapped_column(Integer)
    result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("results.result_id"))
    error: Mapped[dict[str, Any] | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    locked_by: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    client_ip: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (
        CheckConstraint("stage IN ('guard','planner','narrator')", name="llm_usage_stage"),
        Index("llm_usage_created", "created_at"),
        Index("llm_usage_model_created", "model", "created_at"),
        Index("llm_usage_trace", "trace_id"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stage: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    is_fallback: Mapped[bool] = mapped_column(Boolean)
    input_tokens: Mapped[int] = mapped_column(Integer)
    cached_input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    reasoning_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    price_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class MirrorTrial(Base):
    """One study, as the API returns it (only the mirror's fields), keyed by NCT ID."""

    __tablename__ = "trials"
    __table_args__ = (
        Index("trials_start_year", "start_year"),
        {"schema": "registry"},
    )

    nct_id: Mapped[str] = mapped_column(Text, primary_key=True)
    record: Mapped[dict[str, Any]]
    start_year: Mapped[int | None] = mapped_column(Integer)
    last_update_post_date: Mapped[date | None] = mapped_column(Date)
    synced_at: Mapped[datetime] = _now()


class SyncRun(Base):
    """One load or daily update. The last succeeded run's data timestamp is the mirror's."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('load','update')", name="sync_runs_kind"),
        CheckConstraint("status IN ('running','succeeded','failed')", name="sync_runs_status"),
        Index("sync_runs_status_finished", "status", "finished_at"),
        {"schema": "registry"},
    )

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="running", server_default="running")
    data_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    since: Mapped[date | None] = mapped_column(Date)  # updates: LastUpdatePostDate from
    upserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    removed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TermSet(Base):
    """The NCT IDs one search term matches, as the API resolved them (design Q22)."""

    __tablename__ = "term_sets"
    __table_args__ = ({"schema": "registry"},)

    term_key: Mapped[str] = mapped_column(Text, primary_key=True)  # "<param>|<expression>"
    param: Mapped[str] = mapped_column(Text)
    expression: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    data_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # data it matches
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # last full listing
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # last listing or refresh


class TermMember(Base):
    __tablename__ = "term_members"
    __table_args__ = (
        Index("term_members_nct_id", "nct_id"),
        {"schema": "registry"},
    )

    term_key: Mapped[str] = mapped_column(
        ForeignKey("registry.term_sets.term_key", ondelete="CASCADE"), primary_key=True
    )
    nct_id: Mapped[str] = mapped_column(Text, primary_key=True)
