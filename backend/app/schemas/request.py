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


class CompareGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)
    drug_name: TermList = []
    condition: TermList = []
    sponsor: TermList = []
    country: TermList = []

    @model_validator(mode="after")
    def _has_an_entity(self) -> Self:
        if not (self.drug_name or self.condition or self.sponsor or self.country):
            raise ValueError("each compare group needs a drug_name, condition, sponsor or country")
        return self


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    drug_name: TermList = []
    condition: TermList = []
    sponsor: TermList = []
    country: TermList = []
    trial_phase: list[Annotated[Phase, lenient(Phase)]] = []
    status: list[Annotated[Status, lenient(Status)]] = []
    start_year: Year | None = None
    end_year: Year | None = None
    compare: list[CompareGroup] = []
    chart_type: ChartType | None = None
    top_n: int | None = Field(default=None, ge=1, le=50)
    match_mode: MatchMode = "strict"
    sponsor_role: SponsorRole = "lead"
    citations: Literal["sample", "full"] = "sample"
    citations_per_datum: int = Field(default=5, ge=1, le=50)
    phase_mode: PhaseMode = "combined"
    condition_source: ConditionSource = "mesh"
    include_unknown: bool = True
    edge_metric: EdgeMetric = "count"
    hide_query_entity: bool = False

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
