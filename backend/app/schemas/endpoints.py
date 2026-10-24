"""Bodies of the other endpoints, for the OpenAPI reference (design Q12, Q14, Q17).

The routes build these bodies as plain dicts; the models only document them, and
tests/contract/test_openapi.py checks real bodies against them.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.response import QueryResponse

ErrorCode = Literal[
    "invalid_request",
    "rejected_by_policy",
    "unauthorized",
    "not_found",
    "method_not_allowed",
    "expired",
    "too_many_requests",
    "upstream_unavailable",
    "llm_unavailable",
    "safety_check_unavailable",
    "budget_exceeded",
    "internal_error",
    "cancelled",  # only in a cancelled job's `error`, never an HTTP error
]


class ErrorBody(BaseModel):
    """A real error. Never contains stack traces, prompts, model output or keys."""

    code: ErrorCode = Field(description="Stable, machine-readable error code.")
    message: str = Field(
        description="Short message safe to show to a user.",
        examples=["ClinicalTrials.gov is not responding. Please retry later."],
    )
    details: Any = Field(
        description="`invalid_request`: one `{loc, msg}` per invalid field. Otherwise null.",
        examples=[None],
    )
    trace_id: str = Field(
        description="Trace id; quote it when reporting a problem.",
        examples=["5b3f9a1e-2c4d-4e8f-9a7b-1c2d3e4f5a6b"],
    )


class ErrorResponse(BaseModel):
    """The one body every real error shares."""

    error: ErrorBody = Field(description="The error.")


class JobAccepted(BaseModel):
    """A broad question is running as a background job (202)."""

    job_id: str = Field(description="Job id.", examples=["8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11"])
    status: Literal["pending"] = Field(description="Always `pending` when accepted.")
    poll_url: str = Field(
        description="Where to poll, relative to the API root.",
        examples=["/v1/jobs/8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11"],
    )
    estimated_seconds: int = Field(
        description="Rough estimate of the run time, from the number of pages to fetch.",
        examples=[240],
    )


class JobProgress(BaseModel):
    """Retrieval progress; empty until the job starts fetching."""

    stage: str | None = Field(default=None, description="Current stage.", examples=["retrieve"])
    pages_done: int | None = Field(
        default=None, description="ClinicalTrials.gov pages fetched.", examples=[12]
    )
    pages_total: int | None = Field(
        default=None, description="Pages to fetch in total.", examples=[34]
    )


class JobStatus(BaseModel):
    """A background job and, once it has finished, its result or error."""

    job_id: str = Field(description="Job id.", examples=["8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11"])
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"] = Field(
        description="`pending` (queued, or waiting for a retry), `running`, `succeeded` "
        "(see `result`), `failed` (see `error`) or `cancelled` (by `DELETE`; `error.code` "
        "is `cancelled`)."
    )
    progress: JobProgress = Field(description="Retrieval progress.")
    estimated_seconds: int = Field(description="Estimate given when accepted.", examples=[240])
    result: QueryResponse | None = Field(
        description="The normal `POST /v1/query` response once `succeeded`; otherwise null."
    )
    error: ErrorBody | None = Field(
        description="The error once `failed` (same body as a synchronous error) or "
        "`cancelled` (code `cancelled`); otherwise null."
    )


class Evidence(BaseModel):
    """A field of the trial record that places the trial in the data point."""

    field: str = Field(
        description="Path in the ClinicalTrials.gov study record.",
        examples=["protocolSection.designModule.phases[0]"],
    )
    excerpt: Any = Field(description="The value found there.", examples=["PHASE2"])


class Citation(BaseModel):
    """One trial behind a data point."""

    rank: int = Field(description="Position in the data point's citation order.", examples=[0])
    nct_id: str = Field(description="ClinicalTrials.gov id.", examples=["NCT04430595"])
    url: str = Field(
        description="The trial's page on ClinicalTrials.gov.",
        examples=["https://clinicaltrials.gov/study/NCT04430595"],
    )
    title: str | None = Field(
        description="Brief title.", examples=["Multi-4SCAR-T Therapy Targeting Breast Cancer"]
    )
    evidence: list[Evidence] = Field(description="Why this trial is in the data point.")


class CitationPage(BaseModel):
    """One page of every trial behind one data point."""

    result_id: str = Field(
        description="Stored result id.", examples=["d70db059-8f32-49a2-9fdc-231f5e3fd056"]
    )
    datum: str = Field(description="The data point's `key`.", examples=["PHASE2"])
    label: str = Field(description="The data point's label.", examples=["Phase 2"])
    citation_count: int = Field(description="Trials behind the data point.", examples=[3546])
    citations: list[Citation] = Field(description="This page, in citation order.")
    next_cursor: int | None = Field(
        description="Pass as `cursor` for the next page; null on the last page.",
        examples=[50],
    )


class OptionValue(BaseModel):
    value: str = Field(description="Code to send.", examples=["PHASE3"])
    label: str = Field(description="Label to show.", examples=["Phase 3"])


class DimensionOption(BaseModel):
    key: str = Field(description="Dimension key.", examples=["phase"])
    label: str = Field(description="Label to show.", examples=["Phase"])
    kind: Literal["categorical", "entity", "time", "numeric"] = Field(
        description="`categorical` (fixed values), `entity` (open-ended names such as drugs), "
        "`time` (years) or `numeric` (per-trial numbers for histograms and scatter plots)."
    )
    multi_valued: bool = Field(description="Whether a trial can have several values.")
    counting_rule: str = Field(description="How a trial is counted when grouped by it.")
    values: list[OptionValue] | None = Field(
        description="Possible values for enum dimensions; null otherwise."
    )


class MeasureOption(BaseModel):
    key: str = Field(description="Measure key.", examples=["trial_count"])
    label: str = Field(description="Label to show.", examples=["Number of trials"])
    unit: str = Field(description="Unit.", examples=["trials"])


class ChartTypeOption(BaseModel):
    key: str = Field(description="Chart type.", examples=["bar_chart"])


class FilterOptions(BaseModel):
    trial_phase: list[OptionValue] = Field(description="Values for `trial_phase`.")
    status: list[OptionValue] = Field(description="Values for `status`.")
    country: list[str] = Field(description="Country names for `country`.")


class Options(BaseModel):
    """The registry, for building pickers."""

    dimensions: list[DimensionOption] = Field(description="What data can be grouped by.")
    measures: list[MeasureOption] = Field(description="What can be counted or summed.")
    chart_types: list[ChartTypeOption] = Field(description="Chart types.")
    filters: FilterOptions = Field(description="Values accepted by the filter fields.")


class UsageSummary(BaseModel):
    """Today's AI calls and cost (UTC day)."""

    day: str = Field(description="The UTC day.", examples=["2026-10-24"])
    calls: int = Field(description="AI calls today.", examples=[412])
    cost_usd: float = Field(description="Cost today in USD.", examples=[0.731])
    unknown_cost_calls: int = Field(description="Calls whose model has no price.", examples=[0])
    fallback_calls: int = Field(description="Calls answered by a fallback model.", examples=[3])
    by_model: dict[str, dict[str, float]] = Field(
        description="Calls and cost per model.",
        examples=[{"gpt-5.4-nano": {"calls": 260, "cost_usd": 0.104}}],
    )
    budget_usd: float = Field(
        description="Daily budget; at it, questions that need a model call get 503 "
        "`budget_exceeded` (cached answers are still served).",
        examples=[100.0],
    )
