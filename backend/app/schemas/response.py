"""Response envelope (design Q12), shared by every chart type."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.registry import ChartType

SCHEMA_VERSION = "2.0"  # 2.0: visualization.summary removed

Status = Literal["ok", "no_matching_trials", "out_of_scope", "could_not_interpret"]


class Channel(BaseModel):
    """Maps a data key to a visual channel (Vega-Lite style)."""

    field: str = Field(
        description="The key in each data record that holds this channel's value.",
        examples=["trial_count"],
    )
    type: Literal["quantitative", "nominal", "ordinal", "temporal"] = Field(
        description="Vega-Lite measurement type of the field.", examples=["quantitative"]
    )
    label: str = Field(description="Axis or legend title.", examples=["Number of trials"])
    unit: str | None = Field(
        default=None, description="Unit of a quantitative value.", examples=["trials"]
    )
    sort: Literal["ascending", "descending", "natural"] | None = Field(
        default=None,
        description="Order of the categories; `natural` is the domain order, e.g. phases.",
        examples=["natural"],
    )
    time_unit: Literal["year"] | None = Field(
        default=None, description="Time unit of a temporal field.", examples=["year"]
    )


class Visualization(BaseModel):
    """The chart: its type, title, channel encoding and data records."""

    type: ChartType = Field(description="Chart type.", examples=["bar_chart"])
    title: str = Field(
        description="Chart title, written by the AI narrator and checked against the data "
        "(a template title when the check fails).",
        examples=["ClinicalTrials.gov breast cancer trials by phase"],
    )
    encoding: dict[str, Channel] = Field(
        description="Visual channel name -> data key: every key a renderer needs is named "
        "here. Channels: `x`, `y` and an optional `color` for bar, grouped bar, time series, "
        "histogram and scatter charts; `value` for a metric; `node_id`, `node_label`, "
        "`node_size`, `node_color`, `edge_source`, `edge_target` and `edge_width` for a "
        "network.",
        examples=[
            {
                "x": {"field": "phase", "type": "ordinal", "label": "Phase", "sort": "natural"},
                "y": {
                    "field": "trial_count",
                    "type": "quantitative",
                    "label": "Number of trials",
                    "unit": "trials",
                },
            }
        ],
    )
    # Flat records keyed by the encoding fields, plus `key`, `citation_count`,
    # `citations` and `citations_truncated` on every data point.
    data: list[dict[str, Any]] | dict[str, list[dict[str, Any]]] = Field(
        description="Flat records whose keys are named in `encoding`; a network has "
        "`{nodes: [...], edges: [...]}` instead. Every record, node and edge also has a "
        "stable `key` (for the citations endpoint), `citation_count` (all contributing "
        "trials), `citations` (up to `citations_per_datum` of them, each with `nct_id`, "
        "`url`, `title` and `evidence`: the record fields that place the trial in this data "
        "point) and `citations_truncated` (more exist than are inlined). Time series records "
        "also have `estimated_count`: trials placed by an estimated, not actual, date.",
        examples=[
            [
                {
                    "key": "PHASE2",
                    "phase": "Phase 2",
                    "trial_count": 3546,
                    "citation_count": 3546,
                    "citations": [
                        {
                            "nct_id": "NCT07729046",
                            "url": "https://clinicaltrials.gov/study/NCT07729046",
                            "title": "Neu Direction: Testing the Efficacy of Adding HER "
                            "Inhibition to Standard of Care in Metastatic MLH1-low "
                            "Endocrine-resistant ER+/HER2- Breast Cancer",
                            "evidence": [
                                {
                                    "field": "protocolSection.designModule.phases[0]",
                                    "excerpt": "PHASE2",
                                }
                            ],
                        }
                    ],
                    "citations_truncated": True,
                }
            ]
        ],
    )


class Excluded(BaseModel):
    """Trials left out of the chart for one reason."""

    reason: str = Field(description="Why they were left out.", examples=["no start date"])
    count: int = Field(description="How many trials.", examples=[5])


class Sort(BaseModel):
    """How the categories are ordered."""

    by: Literal["x", "y"] = Field(description="By the category (`x`) or the value (`y`).")
    order: Literal["asc", "desc", "natural"] = Field(
        description="Direction; `natural` is the domain order."
    )


class ApiQuery(BaseModel):
    """One ClinicalTrials.gov search behind the numbers."""

    group: str | None = Field(
        description="Comparison group label; null for a single search.", examples=[None]
    )
    url: str = Field(
        description="The ClinicalTrials.gov API v2 request, to reproduce the numbers.",
        examples=["https://clinicaltrials.gov/api/v2/studies?query.cond=%22breast+cancer%22"],
    )
    total_count: int = Field(description="Trials the search matched.", examples=[16765])


class Interpretation(BaseModel):
    """How the question was read."""

    intent: str = Field(
        description="Kind of question: trend, distribution, top_n, comparison, geographic, "
        "network, numeric_distribution, numeric_relationship or single_number.",
        examples=["distribution"],
    )
    chart_type: str = Field(description="The chart type used.", examples=["bar_chart"])
    dimension: str | None = Field(
        description="What the data is grouped by (see `GET /v1/options`).", examples=["phase"]
    )
    dimension_2: str | None = Field(
        default=None,
        description="Second dimension: the series of a grouped chart, or a network's second "
        "node type.",
        examples=[None],
    )
    measure: str = Field(description="What is counted or summed.", examples=["trial_count"])
    chart_type_source: Literal["ai", "user", "fallback", "plan"] = Field(
        default="plan",
        description="Who chose the chart type: `ai`; `user` (the `chart_type` field); "
        "`fallback` (the AI's choice did not fit, so the intent's default was used); or "
        "`plan` (a hand-written plan on the debug endpoint).",
        examples=["ai"],
    )


class CitationsMeta(BaseModel):
    """How citations were inlined."""

    requested: Literal["sample", "full"] = Field(
        default="sample", description="Citation mode asked for."
    )
    applied: Literal["sample", "full"] = Field(default="sample", description="Citation mode used.")
    per_datum: int = Field(description="Maximum citations inlined per data point.", examples=[5])
    reason: str | None = Field(
        default=None,
        description="Why `applied` differs from `requested`, or why a sample was all there "
        "was: e.g. the full-citation size limit was exceeded, or years were counted.",
    )


class Meta(BaseModel):
    """Everything needed to trust and reproduce the answer."""

    model_config = ConfigDict(extra="forbid")

    interpretation: Interpretation | None = Field(
        default=None, description="How the question was read; null when there is no chart."
    )
    filters: dict[str, Any] = Field(
        default={},
        description="Filters applied, after merging the request fields into the AI's plan "
        "(e.g. `drugs`, `conditions`, `phases`, `start_year_min`, `groups`). Terms are shown "
        "as cleaned.",
        examples=[{"conditions": ["breast cancer"]}],
    )
    assumptions: list[str] = Field(
        default=[],
        description="How ambiguous parts of the question were read.",
        examples=[
            ["Interpreting 'breast cancer trials' as trials with condition 'breast cancer'."]
        ],
    )
    warnings: list[str] = Field(
        default=[],
        description="Things to know, e.g. a request field overriding the question, or a "
        "chart type replaced by a better fit.",
    )
    notes: list[str] = Field(
        default=[],
        description="Facts about the chart, e.g. `Showing the top 10 of 84 countries.`",
    )
    counting_rule: str | None = Field(
        default=None,
        description="How a trial is counted in the chart.",
        examples=[
            "Each trial is counted once; trials with two phases get a combined bucket "
            "(e.g. Phase 2/Phase 3)."
        ],
    )
    additive: bool | None = Field(
        default=None,
        description="Whether the values add up to `unique_trials`. False when a trial can "
        "count in several categories (e.g. countries, split phases).",
        examples=[True],
    )
    unique_trials: int | None = Field(
        default=None, description="Distinct trials behind the chart.", examples=[16765]
    )
    excluded: list[Excluded] = Field(
        default=[], description="Trials left out of the chart, by reason."
    )
    sort: Sort | None = Field(default=None, description="How the categories are ordered.")
    api_queries: list[ApiQuery] = Field(
        default=[], description="Every ClinicalTrials.gov search behind the numbers."
    )
    group_overlap: list[dict[str, Any]] | None = Field(
        default=None,
        description="Comparisons only: trials shared by each pair of groups.",
        examples=[[{"groups": ["pembrolizumab", "nivolumab"], "trials": 174}]],
    )
    network: dict[str, Any] | None = Field(
        default=None,
        description="Networks only: node and edge counts before and after pruning, the "
        "thresholds and the community algorithm.",
    )
    citations: CitationsMeta | None = Field(default=None, description="How citations were inlined.")
    data_timestamp: str | None = Field(
        default=None,
        description="ClinicalTrials.gov data version the answer was computed from.",
        examples=["2026-10-23T09:00:04"],
    )
    retrieved_at: str | None = Field(
        default=None,
        description="When the trials were fetched.",
        examples=["2026-10-24T12:07:55+00:00"],
    )
    source: str = Field(default="clinicaltrials.gov", description="Data source.")
    guard: dict[str, Any] | None = Field(
        default=None,
        description="Input guard verdict and model.",
        examples=[{"verdict": "ok", "model": "gpt-5.4-nano"}],
    )
    planner: dict[str, Any] | None = Field(
        default=None, description="Planning agent trace: steps, tool calls and model."
    )
    narration: dict[str, Any] | None = Field(
        default=None,
        description="Title narrator: model, attempts, and `fallback: true` when the template "
        "title was used.",
    )
    usage: dict[str, Any] | None = Field(
        default=None,
        description="AI calls, tokens and cost in USD for this answer.",
        examples=[
            {
                "llm_calls": 5,
                "input_tokens": 3878,
                "output_tokens": 422,
                "cost_usd": 0.00198,
                "models": ["gpt-5.4-mini", "gpt-5.4-nano"],
            }
        ],
    )
    cache: dict[str, str] | None = Field(
        default=None,
        description="Whether the plan (`hit`, `miss`) and the result (`hit`, `revalidated`, "
        "`miss`) came from cache.",
        examples=[{"plan": "miss", "result": "miss"}],
    )
    trace_id: str | None = Field(
        default=None,
        description="Trace id of the request; quote it when reporting a problem.",
        examples=["f99e189b-ed92-498b-909d-51252c63d1cd"],
    )
    timings_ms: dict[str, int] = Field(
        default={},
        description="Time per stage in milliseconds.",
        examples=[{"retrieve": 25949, "aggregate": 326, "narrate": 2523, "total": 28799}],
    )
    details: dict[str, Any] = Field(
        default={},
        description="Status-specific details. `no_matching_trials`: `search_counts` per "
        "group. `out_of_scope`: `reason` and an optional `suggestion`. "
        "`could_not_interpret`: the validation `errors` and the planner's `best_attempt`.",
    )


class QueryResponse(BaseModel):
    """The answer to a question: a chart specification, or why there is none."""

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="Response schema version; changes when the shape changes in a way that "
        "can break a client.",
        examples=[SCHEMA_VERSION],
    )
    result_id: str | None = Field(
        default=None,
        description="Id of the stored result, for the citations endpoint. Null for "
        "`out_of_scope` and `could_not_interpret`, or when the deployment has no database.",
        examples=["d70db059-8f32-49a2-9fdc-231f5e3fd056"],
    )
    status: Status = Field(
        description="`ok`: `visualization` has the chart. `no_matching_trials`, "
        "`out_of_scope`, `could_not_interpret`: `visualization` is null and `meta.details` "
        "says why.",
        examples=["ok"],
    )
    visualization: Visualization | None = Field(
        description="The chart; null when `status` is not `ok`."
    )
    meta: Meta = Field(description="Interpretation, filters, counting rules and provenance.")
