"""Example bodies for the OpenAPI reference, trimmed from real runs (docs/examples).

Data lists are shortened (two data points, one citation each); the numbers, ids and
URLs are from the recorded responses. tests/contract/test_openapi.py validates each
example against its model.
"""

from typing import Any

from app.schemas.response import SCHEMA_VERSION

RESULT_ID = "d70db059-8f32-49a2-9fdc-231f5e3fd056"
JOB_ID = "8c1f6c52-4a8e-4d3b-9a51-0f2e7b6d9c11"
TRACE_ID = "f99e189b-ed92-498b-909d-51252c63d1cd"

GUARD = {"verdict": "ok", "model": "gpt-5.4-nano"}


def _citation(nct_id: str, title: str, field: str, excerpt: str) -> dict[str, Any]:
    return {
        "nct_id": nct_id,
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "title": title,
        "evidence": [{"field": field, "excerpt": excerpt}],
    }


# docs/examples/2-condition-phases.json
QUERY_OK: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "result_id": RESULT_ID,
    "status": "ok",
    "visualization": {
        "type": "bar_chart",
        "title": "ClinicalTrials.gov breast cancer trials by phase",
        "encoding": {
            "x": {"field": "phase", "type": "ordinal", "label": "Phase", "sort": "natural"},
            "y": {
                "field": "trial_count",
                "type": "quantitative",
                "label": "Number of trials",
                "unit": "trials",
            },
        },
        "data": [
            {
                "key": "PHASE2",
                "phase": "Phase 2",
                "trial_count": 3546,
                "citation_count": 3546,
                "citations": [
                    _citation(
                        "NCT07729046",
                        "Neu Direction: Testing the Efficacy of Adding HER Inhibition to "
                        "Standard of Care in Metastatic MLH1-low Endocrine-resistant ER+/HER2- "
                        "Breast Cancer",
                        "protocolSection.designModule.phases[0]",
                        "PHASE2",
                    )
                ],
                "citations_truncated": True,
            },
            {
                "key": "PHASE3",
                "phase": "Phase 3",
                "trial_count": 1408,
                "citation_count": 1408,
                "citations": [
                    _citation(
                        "NCT07578116",
                        "Adding Surgery and Radiation to the Usual Treatment for HER2-Positive "
                        "Breast Cancer That Had Already Spread at Diagnosis",
                        "protocolSection.designModule.phases[0]",
                        "PHASE3",
                    )
                ],
                "citations_truncated": True,
            },
        ],
    },
    "meta": {
        "interpretation": {
            "intent": "distribution",
            "chart_type": "bar_chart",
            "dimension": "phase",
            "dimension_2": None,
            "measure": "trial_count",
            "chart_type_source": "ai",
        },
        "filters": {"conditions": ["breast cancer"]},
        "assumptions": [
            "Interpreting 'breast cancer trials' as trials with condition 'breast cancer'."
        ],
        "warnings": [],
        "notes": [],
        "counting_rule": "Each trial is counted once; trials with two phases get a combined "
        "bucket (e.g. Phase 2/Phase 3).",
        "additive": True,
        "unique_trials": 16765,
        "excluded": [],
        "sort": {"by": "x", "order": "natural"},
        "api_queries": [
            {
                "group": None,
                "url": "https://clinicaltrials.gov/api/v2/studies?query.cond=%22breast+cancer%22",
                "total_count": 16765,
            }
        ],
        "citations": {"requested": "sample", "applied": "sample", "per_datum": 3, "reason": None},
        "data_timestamp": "2026-10-23T09:00:04",
        "retrieved_at": "2026-10-24T12:07:55+00:00",
        "source": "clinicaltrials.gov",
        "guard": GUARD,
        "planner": {"steps": 2, "model": "gpt-5.4-mini"},
        "narration": {"model": "gpt-5.4-nano", "attempts": 2, "fallback": False, "errors": []},
        "usage": {
            "llm_calls": 5,
            "input_tokens": 3878,
            "output_tokens": 422,
            "cost_usd": 0.00198,
            "models": ["gpt-5.4-mini", "gpt-5.4-nano"],
        },
        "cache": {"plan": "miss", "result": "miss"},
        "trace_id": TRACE_ID,
        "timings_ms": {
            "plan": 2840,
            "count": 610,
            "retrieve": 25949,
            "aggregate": 326,
            "narrate": 2523,
            "total": 32260,
        },
        "details": {},
    },
}

# docs/examples/5-drug-network.json
QUERY_NETWORK: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "result_id": "d351b949-6832-4d8b-a127-c2e16573f0cf",
    "status": "ok",
    "visualization": {
        "type": "network_graph",
        "title": "ClinicalTrials.gov network of melanoma trials by drug, showing trial counts",
        "encoding": {
            "node_id": {"field": "id", "type": "nominal", "label": "Entity"},
            "node_label": {"field": "label", "type": "nominal", "label": "Name"},
            "node_size": {
                "field": "weight",
                "type": "quantitative",
                "label": "Trials",
                "unit": "trials",
            },
            "node_color": {"field": "community", "type": "nominal", "label": "Community"},
            "edge_source": {"field": "source", "type": "nominal", "label": "From"},
            "edge_target": {"field": "target", "type": "nominal", "label": "To"},
            "edge_width": {
                "field": "weight",
                "type": "quantitative",
                "label": "Shared trials",
                "unit": "trials",
            },
        },
        "data": {
            "nodes": [
                {
                    "key": "drug:nivolumab",
                    "id": "drug:nivolumab",
                    "label": "Nivolumab",
                    "type": "drug",
                    "weight": 231,
                    "degree": 16,
                    "community": 2,
                    "is_query_entity": False,
                    "citation_count": 231,
                    "citations": [
                        _citation(
                            "NCT07862530",
                            "Neoadjuvant RP2 + Nivolumab in Patients With Melanoma",
                            "protocolSection.armsInterventionsModule.interventions[1].name",
                            "Nivolumab",
                        )
                    ],
                    "citations_truncated": True,
                },
                {
                    "key": "drug:ipilimumab",
                    "id": "drug:ipilimumab",
                    "label": "Ipilimumab",
                    "type": "drug",
                    "weight": 206,
                    "degree": 18,
                    "community": 2,
                    "is_query_entity": False,
                    "citation_count": 206,
                    "citations": [
                        _citation(
                            "NCT07838974",
                            "Adding Anakinra and Tocilizumab to Nivolumab and Ipilimumab for "
                            "the Treatment of Melanoma Patients 50 Years of Age or Older",
                            "protocolSection.armsInterventionsModule.interventions[4].name",
                            "Ipilimumab",
                        )
                    ],
                    "citations_truncated": True,
                },
            ],
            "edges": [
                {
                    "key": "drug:ipilimumab|drug:nivolumab",
                    "source": "drug:ipilimumab",
                    "target": "drug:nivolumab",
                    "weight": 122,
                    "jaccard": 0.3873,
                    "citation_count": 122,
                    "citations": [
                        _citation(
                            "NCT07838974",
                            "Adding Anakinra and Tocilizumab to Nivolumab and Ipilimumab for "
                            "the Treatment of Melanoma Patients 50 Years of Age or Older",
                            "protocolSection.armsInterventionsModule.interventions[4].name",
                            "Ipilimumab",
                        )
                        | {
                            "evidence": [
                                {
                                    "field": "protocolSection.armsInterventionsModule"
                                    ".interventions[4].name",
                                    "excerpt": "Ipilimumab",
                                },
                                {
                                    "field": "protocolSection.armsInterventionsModule"
                                    ".interventions[6].name",
                                    "excerpt": "Nivolumab",
                                },
                            ]
                        }
                    ],
                    "citations_truncated": True,
                }
            ],
        },
    },
    "meta": {
        "interpretation": {
            "intent": "network",
            "chart_type": "network_graph",
            "dimension": "drug",
            "dimension_2": "drug",
            "measure": "trial_count",
            "chart_type_source": "ai",
        },
        "filters": {"conditions": ["melanoma"]},
        "assumptions": [
            "Interpreting 'combination studies' as trials involving more than one drug "
            "intervention."
        ],
        "counting_rule": "Node size = distinct trials with that entity; edge width = distinct "
        "trials with both.",
        "additive": False,
        "unique_trials": 1446,
        "network": {
            "nodes_before": 1439,
            "edges_before": 4049,
            "nodes": 38,
            "edges": 130,
            "min_edge_weight": 3,
            "top_n_per_type": 40,
            "trials_with_data": 2758,
            "trials_without_links": 2334,
            "community_algorithm": "greedy modularity (networkx), weighted by edge weight",
        },
        "data_timestamp": "2026-10-23T09:00:04",
        "guard": GUARD,
        "trace_id": TRACE_ID,
    },
}

# POST /v1/debug/plan: the same chart without the AI stages and without storage.
DEBUG_OK: dict[str, Any] = QUERY_OK | {
    "result_id": None,
    "meta": {
        key: value
        for key, value in QUERY_OK["meta"].items()
        if key not in ("guard", "planner", "narration", "usage", "cache")
    }
    | {"interpretation": QUERY_OK["meta"]["interpretation"] | {"chart_type_source": "plan"}},
}

QUERY_NO_MATCH: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "result_id": "3e0b7a4c-6f1d-4c2a-8b9e-5d7f0a1c2b3d",
    "status": "no_matching_trials",
    "visualization": None,
    "meta": {
        "interpretation": {
            "intent": "distribution",
            "chart_type": "bar_chart",
            "dimension": "phase",
            "dimension_2": None,
            "measure": "trial_count",
            "chart_type_source": "ai",
        },
        "filters": {"drugs": ["pembrolizumb"]},
        "assumptions": ["No chart was asked for; showing trials by phase."],
        "citations": {"requested": "sample", "applied": "sample", "per_datum": 5, "reason": None},
        "data_timestamp": "2026-10-23T09:00:04",
        "guard": GUARD,
        "cache": {"plan": "miss", "result": "miss"},
        "trace_id": TRACE_ID,
        "timings_ms": {"total": 412},
        "details": {"search_counts": [{"group": None, "count": 0}]},
    },
}

QUERY_OUT_OF_SCOPE: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "result_id": None,
    "status": "out_of_scope",
    "visualization": None,
    "meta": {
        "guard": GUARD,
        "planner": {"steps": 1, "model": "gpt-5.4-mini"},
        "cache": {"plan": "miss"},
        "trace_id": TRACE_ID,
        "details": {
            "reason": "average trial duration isn't a measure we can compute",
            "suggestion": "How are trial durations distributed for trials started since 2015?",
        },
    },
}

QUERY_COULD_NOT_INTERPRET: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "result_id": None,
    "status": "could_not_interpret",
    "visualization": None,
    "meta": {
        "guard": GUARD,
        "planner": {"steps": 6, "model": "gpt-5.4-mini"},
        "cache": {"plan": "miss"},
        "trace_id": TRACE_ID,
        "details": {
            "errors": ["dimension: Value error, unknown dimension 'colour'"],
            "best_attempt": {
                "scope": "in_scope",
                "intent": "distribution",
                "chart_type": "bar_chart",
                "dimension": "colour",
                "measure": "trial_count",
            },
        },
    },
}

JOB_ACCEPTED: dict[str, Any] = {
    "job_id": JOB_ID,
    "status": "pending",
    "poll_url": f"/v1/jobs/{JOB_ID}",
    "estimated_seconds": 240,
}

JOB_RUNNING: dict[str, Any] = {
    "job_id": JOB_ID,
    "status": "running",
    "progress": {"stage": "retrieve", "pages_done": 12, "pages_total": 34},
    "estimated_seconds": 240,
    "result": None,
    "error": None,
}

JOB_SUCCEEDED: dict[str, Any] = JOB_RUNNING | {
    "status": "succeeded",
    "progress": {"stage": "retrieve", "pages_done": 34, "pages_total": 34},
    "result": QUERY_OK,
}

UPSTREAM_ERROR: dict[str, Any] = {
    "code": "upstream_unavailable",
    "message": "ClinicalTrials.gov is not responding. Please retry later.",
    "details": None,
    "trace_id": TRACE_ID,
}

JOB_FAILED: dict[str, Any] = JOB_RUNNING | {"status": "failed", "error": UPSTREAM_ERROR}

JOB_CANCELLED: dict[str, Any] = JOB_RUNNING | {
    "status": "cancelled",
    "error": {
        "code": "cancelled",
        "message": "This job was cancelled.",
        "details": None,
        "trace_id": TRACE_ID,
    },
}

CITATION_PAGE: dict[str, Any] = {
    "result_id": RESULT_ID,
    "datum": "PHASE2",
    "label": "Phase 2",
    "citation_count": 3546,
    "citations": [
        {"rank": 0, **QUERY_OK["visualization"]["data"][0]["citations"][0]},
    ],
    "next_cursor": 1,
}

OPTIONS: dict[str, Any] = {
    "dimensions": [
        {
            "key": "phase",
            "label": "Phase",
            "kind": "categorical",
            "multi_valued": False,
            "counting_rule": "Each trial is counted once; trials with two phases get a "
            "combined bucket (e.g. Phase 2/Phase 3).",
            "values": [{"value": "PHASE3", "label": "Phase 3"}],
        }
    ],
    "measures": [{"key": "trial_count", "label": "Number of trials", "unit": "trials"}],
    "chart_types": [{"key": "bar_chart"}, {"key": "network_graph"}],
    "filters": {
        "trial_phase": [{"value": "PHASE3", "label": "Phase 3"}],
        "status": [{"value": "RECRUITING", "label": "Recruiting"}],
        "country": ["Germany", "United States"],
    },
}

USAGE: dict[str, Any] = {
    "day": "2026-10-24",
    "calls": 412,
    "cost_usd": 0.731,
    "unknown_cost_calls": 0,
    "fallback_calls": 3,
    "by_model": {
        "gpt-5.4-mini": {"calls": 152, "cost_usd": 0.627},
        "gpt-5.4-nano": {"calls": 260, "cost_usd": 0.104},
    },
    "budget_usd": 100.0,
}

HEALTH_OK: dict[str, Any] = {
    "status": "ok",
    "checks": {"database": "ok", "ctgov": "ok"},
    "data_timestamp": "2026-10-23T09:00:04",
    "fast_mode": {"status": "ready", "data_timestamp": "2026-10-23T09:00:04"},
}

HEALTH_CTGOV_DOWN: dict[str, Any] = {
    "status": "ok",
    "checks": {"database": "ok", "ctgov": "error"},
    "data_timestamp": None,
    "fast_mode": {"status": "unknown", "data_timestamp": None},
}

HEALTH_UNAVAILABLE: dict[str, Any] = {
    "status": "unavailable",
    "checks": {"database": "error", "ctgov": "ok"},
    "data_timestamp": "2026-10-23T09:00:04",
    "fast_mode": {"status": "unknown", "data_timestamp": None},
}

# Request bodies for the Swagger "Try it out" dropdown (from docs/examples).
QUERY_REQUESTS: dict[str, dict[str, Any]] = {
    "condition_phases": {
        "summary": "Distribution: breast cancer trials by phase",
        "value": {
            "query": "How are breast cancer trials distributed across phases?",
            "citations_per_datum": 3,
        },
    },
    "drug_trend": {
        "summary": "Trend with a field: the drug comes from drug_name",
        "value": {
            "query": "How has the number of trials for this drug changed per year since 2015?",
            "drug_name": "Pembrolizumab",
            "citations_per_datum": 3,
        },
    },
    "comparison": {
        "summary": "Comparison: two drugs by phase",
        "value": {"query": "Compare phases for trials involving pembrolizumab vs nivolumab."},
    },
    "compare_field": {
        "summary": "Comparison with explicit groups and filters",
        "value": {
            "query": "Compare these drugs by phase",
            "compare": [
                {"label": "Pembrolizumab", "drug_name": "pembrolizumab"},
                {"label": "Nivolumab", "drug_name": "nivolumab"},
            ],
            "condition": "melanoma",
            "start_year": 2015,
        },
    },
    "countries": {
        "summary": "Geographic: top countries for recruiting lung cancer trials",
        "value": {
            "query": "Which countries have the most recruiting trials for lung cancer?",
            "top_n": 10,
        },
    },
    "network": {
        "summary": "Network: drugs that co-occur in melanoma trials",
        "value": {
            "query": "Which drugs frequently co-occur in combination studies for melanoma?",
            "citations_per_datum": 2,
        },
    },
}
