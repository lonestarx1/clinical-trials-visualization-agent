"""The QueryPlan the planning agent must submit (design Q4a).

Every field is an enum or a bounded number, except entity terms. Unknown keys
are rejected. OR within a filter, AND across filters.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.registry import DIMENSIONS, MEASURES, ChartType, DimensionKind, Intent
from app.registry.enums import (
    AgencyClass,
    Allocation,
    Masking,
    Phase,
    PrimaryPurpose,
    Sex,
    StandardAge,
    Status,
    StudyType,
)
from app.schemas.common import TermList, Year

SponsorRole = Literal["lead", "any"]
MatchMode = Literal["strict", "broad"]
PhaseMode = Literal["combined", "split"]
ConditionSource = Literal["mesh", "raw"]
EdgeMetric = Literal["count", "jaccard"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(Strict):
    drugs: TermList = []
    conditions: TermList = []
    sponsors: TermList = []
    countries: TermList = []
    us_states: TermList = []
    sponsor_role: SponsorRole = "lead"
    match_mode: MatchMode = "strict"
    phases: list[Phase] = []
    statuses: list[Status] = []
    study_types: list[StudyType] = []
    sponsor_classes: list[AgencyClass] = []
    age_groups: list[StandardAge] = []
    sexes: list[Sex] = []
    allocations: list[Allocation] = []
    maskings: list[Masking] = []
    primary_purposes: list[PrimaryPurpose] = []
    healthy_volunteers: bool | None = None
    has_results: bool | None = None
    start_year_min: Year | None = None
    start_year_max: Year | None = None

    @model_validator(mode="after")
    def _ordered_years(self) -> Self:
        lo, hi = self.start_year_min, self.start_year_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("start_year_min must not be after start_year_max")
        return self


class Group(Strict):
    label: str = Field(min_length=1, max_length=100)
    filters: Filters = Filters()


class PlanOptions(Strict):
    top_n: int | None = Field(default=None, ge=1, le=50)
    histogram_bins: int | None = Field(default=None, ge=2, le=50)
    phase_mode: PhaseMode | None = None
    condition_source: ConditionSource | None = None
    include_unknown: bool | None = None
    show_empty: bool | None = None
    network_min_edge_weight: int | None = Field(default=None, ge=1)
    edge_metric: EdgeMetric | None = None
    hide_query_entity: bool | None = None
    count_entity: str | None = None  # measure distinct_count: the entity dimension to count
    min_trials: int | None = Field(default=None, ge=1, le=1000)  # ... with at least this many


class QueryPlan(Strict):
    scope: Literal["in_scope", "out_of_scope"]
    scope_reason: str | None = Field(default=None, max_length=500)
    intent: Intent
    chart_type: ChartType
    filters: Filters = Filters()
    groups: list[Group] = []
    dimension: str | None = None
    dimension_2: str | None = None
    measure: str = "trial_count"
    options: PlanOptions = PlanOptions()
    assumptions: list[str] = Field(default=[], max_length=10)

    @field_validator("dimension", "dimension_2")
    @classmethod
    def _known_dimension(cls, key: str | None) -> str | None:
        if key is not None and key not in DIMENSIONS:
            raise ValueError(f"unknown dimension {key!r}")
        return key

    @field_validator("measure")
    @classmethod
    def _known_measure(cls, key: str) -> str:
        if key not in MEASURES:
            raise ValueError(f"unknown measure {key!r}")
        return key

    @field_validator("groups")
    @classmethod
    def _group_count(cls, groups: list[Group]) -> list[Group]:
        if groups and not 2 <= len(groups) <= 4:
            raise ValueError("comparisons need 2-4 groups")
        labels = [g.label for g in groups]
        if len(set(labels)) != len(labels):
            raise ValueError("group labels must be unique")
        return groups

    @model_validator(mode="after")
    def _entity_to_count(self) -> Self:
        entity = self.options.count_entity
        if self.measure == "distinct_count":
            if entity not in DIMENSIONS or DIMENSIONS[entity].kind is not DimensionKind.ENTITY:
                raise ValueError(
                    "measure distinct_count needs options.count_entity: an entity dimension "
                    "(sponsor, collaborator, drug, condition, country, site, investigator)"
                )
        elif entity is not None or self.options.min_trials is not None:
            raise ValueError("options.count_entity and min_trials apply only to distinct_count")
        return self

    @model_validator(mode="after")
    def _reason_when_out_of_scope(self) -> Self:
        if self.scope == "out_of_scope" and not self.scope_reason:
            raise ValueError("scope_reason is required when scope is out_of_scope")
        return self
