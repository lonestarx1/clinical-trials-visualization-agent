"""Response envelope (design Q12), shared by every chart type."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.registry import ChartType

SCHEMA_VERSION = "1.0"

Status = Literal["ok", "no_matching_trials", "out_of_scope", "could_not_interpret"]


class Channel(BaseModel):
    """Maps a data key to a visual channel (Vega-Lite style)."""

    field: str
    type: Literal["quantitative", "nominal", "ordinal", "temporal"]
    label: str
    unit: str | None = None
    sort: Literal["ascending", "descending", "natural"] | None = None
    time_unit: Literal["year"] | None = None


class Visualization(BaseModel):
    type: ChartType
    title: str
    summary: str
    encoding: dict[str, Channel]
    # Flat records keyed by the encoding fields, plus `key`, `citation_count`,
    # `citations` and `citations_truncated` on every data point.
    data: list[dict[str, Any]]


class Excluded(BaseModel):
    reason: str
    count: int


class Sort(BaseModel):
    by: Literal["x", "y"]
    order: Literal["asc", "desc", "natural"]


class ApiQuery(BaseModel):
    group: str | None
    url: str
    total_count: int


class Interpretation(BaseModel):
    intent: str
    chart_type: str
    dimension: str | None
    dimension_2: str | None = None
    measure: str
    chart_type_source: Literal["ai", "user", "fallback", "plan"] = "plan"


class CitationsMeta(BaseModel):
    requested: Literal["sample", "full"] = "sample"
    applied: Literal["sample", "full"] = "sample"
    per_datum: int
    reason: str | None = None


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interpretation: Interpretation | None = None
    filters: dict[str, Any] = {}
    assumptions: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    counting_rule: str | None = None
    additive: bool | None = None
    unique_trials: int | None = None
    excluded: list[Excluded] = []
    sort: Sort | None = None
    api_queries: list[ApiQuery] = []
    group_overlap: list[dict[str, Any]] | None = None
    citations: CitationsMeta | None = None
    data_timestamp: str | None = None
    retrieved_at: str | None = None
    source: str = "clinicaltrials.gov"
    trace_id: str | None = None
    timings_ms: dict[str, int] = {}
    details: dict[str, Any] = Field(default={}, description="Status-specific details")


class QueryResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    result_id: str | None = None
    status: Status
    visualization: Visualization | None
    meta: Meta
