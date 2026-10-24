"""POST /v1/query request body (design Q5). Field names follow the assignment."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.registry import ChartType
from app.registry.enums import Phase, Status
from app.schemas.common import TermList, Year, lenient
from app.schemas.plan import (
    ConditionSource,
    EdgeMetric,
    MatchMode,
    PhaseMode,
    SponsorRole,
)

_TERMS = (
    "A string or a list of up to 10 strings (1-200 characters each), matched with OR. "
    "Authoritative: it overrides what the AI reads in the question, and a conflict is "
    "reported in `meta.warnings`."
)
_GROUP_TERMS = "A string or a list of up to 10 strings, matched with OR within this group."
_NETWORK_ONLY = "Network graphs only."


class CompareGroup(BaseModel):
    """One side of a comparison. Needs at least one of drug_name, condition, sponsor, country."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"label": "Pembrolizumab", "drug_name": "pembrolizumab"}]},
    )

    label: str = Field(
        min_length=1,
        max_length=100,
        description="Name of the group, shown as the series in the chart. Unique per request.",
        examples=["Pembrolizumab"],
    )
    drug_name: TermList = Field(
        default=[], description=f"{_GROUP_TERMS} Drug or intervention.", examples=["pembrolizumab"]
    )
    condition: TermList = Field(
        default=[], description=f"{_GROUP_TERMS} Condition or disease.", examples=["melanoma"]
    )
    sponsor: TermList = Field(
        default=[], description=f"{_GROUP_TERMS} Sponsor name.", examples=["Merck Sharp & Dohme"]
    )
    country: TermList = Field(
        default=[], description=f"{_GROUP_TERMS} Country with a trial site.", examples=["Germany"]
    )

    @model_validator(mode="after")
    def _has_an_entity(self) -> Self:
        if not (self.drug_name or self.condition or self.sponsor or self.country):
            raise ValueError("each compare group needs a drug_name, condition, sponsor or country")
        return self


class QueryRequest(BaseModel):
    """A question plus optional structured fields. Unknown fields are rejected (422)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=1000,
        description="The question in plain language, 1-1,000 characters after trimming. "
        "May refer to the fields, e.g. 'this drug'.",
        examples=["How are breast cancer trials distributed across phases?"],
    )
    drug_name: TermList = Field(
        default=[],
        description=f"Drug or intervention name(s). {_TERMS}",
        examples=["Pembrolizumab", ["pembrolizumab", "nivolumab"]],
    )
    condition: TermList = Field(
        default=[],
        description=f"Condition or disease name(s). {_TERMS}",
        examples=["breast cancer"],
    )
    sponsor: TermList = Field(
        default=[],
        description=f"Sponsor name(s); see `sponsor_role`. {_TERMS}",
        examples=["Merck Sharp & Dohme LLC"],
    )
    country: TermList = Field(
        default=[],
        description=f"Country name(s): trials with at least one site there. {_TERMS} "
        "`GET /v1/options` lists the country names.",
        examples=["United States"],
    )
    trial_phase: list[Annotated[Phase, lenient(Phase)]] = Field(
        default=[],
        description="Only trials in any of these phases. Codes (`PHASE3`) or labels "
        "(`Phase 3`), ignoring case and punctuation. Overrides the question.",
        examples=[["PHASE2", "Phase 3"]],
    )
    status: list[Annotated[Status, lenient(Status)]] = Field(
        default=[],
        description="Only trials with any of these overall statuses. Codes (`RECRUITING`) "
        "or labels (`Recruiting`). Overrides the question.",
        examples=[["RECRUITING"]],
    )
    start_year: Year | None = Field(
        default=None,
        description="Only trials that started in or after this year (1900 to 10 years from "
        "now). Overrides the question.",
        examples=[2015],
    )
    end_year: Year | None = Field(
        default=None,
        description="Only trials that started in or before this year. Must not be before "
        "`start_year`. Overrides the question.",
        examples=[2024],
    )
    compare: list[CompareGroup] = Field(
        default=[],
        description="2-4 groups to compare side by side (unique labels). Each group is "
        "searched separately; overlapping trials are reported in `meta.group_overlap`.",
        examples=[
            [
                {"label": "Pembrolizumab", "drug_name": "pembrolizumab"},
                {"label": "Nivolumab", "drug_name": "nivolumab"},
            ]
        ],
    )
    chart_type: ChartType | None = Field(
        default=None,
        description="Force a chart type instead of the AI's choice "
        "(`meta.interpretation.chart_type_source` is then `user`). If it cannot show the "
        "question, the answer is `could_not_interpret` with the reason in `meta.details`.",
        examples=["bar_chart"],
    )
    top_n: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Keep the N largest categories of a ranked chart, or the N nodes with "
        "the most trials per node type in a network. Overrides the AI; `meta.notes` says "
        "when categories were cut.",
        examples=[10],
    )
    match_mode: MatchMode = Field(
        default="strict",
        description="Drug and condition matching. `strict`: a drug must match an "
        "intervention name and a condition matches as an exact phrase. `broad`: "
        "ClinicalTrials.gov's wider intervention search, and a condition's words may match "
        "separately.",
    )
    sponsor_role: SponsorRole = Field(
        default="lead",
        description="`lead`: the sponsor is the lead sponsor. `any`: lead sponsor or collaborator.",
    )
    citations: Literal["sample", "full"] = Field(
        default="sample",
        description="Accepted for compatibility; inline citations are currently always a "
        "sample of up to `citations_per_datum` per data point. The full list for any data "
        "point comes from `GET /v1/results/{result_id}/citations`.",
    )
    citations_per_datum: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum citations inlined per data point (bar, bucket, node, edge). "
        "`citation_count` always gives the full number; `citations_truncated` says whether "
        "more exist.",
        examples=[3],
    )
    phase_mode: PhaseMode = Field(
        default="combined",
        description="Trials with two phases. `combined`: one bucket such as "
        "`PHASE2/PHASE3`. `split`: counted once in each phase (the chart is then not "
        "additive).",
    )
    condition_source: ConditionSource = Field(
        default="mesh",
        description="Condition names for charts by condition. `mesh`: normalised MeSH "
        "terms. `raw`: the names as the sponsor entered them.",
    )
    include_unknown: bool = Field(
        default=True,
        description="Show a 'Not reported' bucket for trials missing the charted value. "
        "When false, they are excluded and counted in `meta.excluded`.",
    )
    edge_metric: EdgeMetric = Field(
        default="count",
        description=f"{_NETWORK_ONLY} Edge weight: `count` (shared trials) or `jaccard` "
        "(shared trials / trials with either).",
    )
    hide_query_entity: bool = Field(
        default=False,
        description=f"{_NETWORK_ONLY} Hide the node for the entity the question is about "
        "(e.g. melanoma in a melanoma drug network), since it links to everything.",
    )

    @field_validator("query", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("compare")
    @classmethod
    def _compare_groups(cls, groups: list[CompareGroup]) -> list[CompareGroup]:
        if groups and not 2 <= len(groups) <= 4:
            raise ValueError("compare needs 2-4 groups")
        labels = [g.label for g in groups]
        if len(set(labels)) != len(labels):
            raise ValueError("compare labels must be unique")
        return groups

    @model_validator(mode="after")
    def _ordered_years(self) -> Self:
        if self.start_year and self.end_year and self.start_year > self.end_year:
            raise ValueError("start_year must not be after end_year")
        return self
