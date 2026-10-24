# Requirement Coverage: Assignment -> Design

Maps every requirement ID from [`docs/parts/README.md`](../parts/README.md) to the design decisions that cover it. Reviewed 2026-10-24 after all 19 design questions.

**Coverage status:**
- **Designed**: fully covered by a decision
- **Designed (verify)**: covered, but depends on a live check
- **Planned**: covered by a deliverable that is produced during implementation, not by the system design itself
- **Gap**: not covered

## Summary

| Status | Count (requirement rows P0-P8) |
|---|---|
| Designed | 56 |
| Designed + Planned (README section still to write) | 3 |
| Designed, pending a live check or user action (O4, O8) | 2 |
| Planned | 11 |
| Gap | **0** |
| **Total** | **72** (+ 9 appendix questions, all Designed) |

No requirement is uncovered. The "Planned" items are deliverables (README sections, example runs, submission, demo video) that the implementation plan must schedule explicitly.

## Part 0: Preamble

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P0-1 | Backend service: question -> structured visualization output | Q2 pipeline, Q12 schema | Designed |
| P0-2 | Backed by ClinicalTrials.gov API data | Q6 (live only), Q14 (citations) | Designed |
| P0-3 | Scope fits ~24 h | Implementation plan (milestones, always-submittable order) | Planned |
| P0-4 | Any tools allowed | Q15 stack | Designed |

## Part 1: Problem overview

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P1-0 | AI-enabled backend | Q2 (Guard, Plan agent, Narrate), Q15 LangGraph | Designed |
| P1-1 | NL query + optional structured fields | Q5 request fields + merge rules | Designed |
| P1-2 | Interpret the question | Q3 planning agent, Q4a QueryPlan | Designed |
| P1-3 | Retrieve relevant data | Q6 strategies, Q7 compilation (strict matching) | Designed |
| P1-4a | Identify whether a visualization is needed | Q1 (`metric`, `out_of_scope`), Q3 intent, Q17 statuses | Designed |
| P1-4b | Choose the suitable chart type | Q3 (AI picks from enum + compatibility rules + fallback) | Designed |
| P1-5 | Spec that **answers** the question | Q4b V1-V4 plan checks, Q18 AI eval + live E2E (expected chart/dimension) | Designed |
| P1-6 | Clear, structured, reliably renderable | Q12 schema, Q17 predictable shapes, Q19 reference renderer | Designed |
| P1-7 | Frontend optional | Q19 (built as a bonus) | Designed |

## Part 2: Data source

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P2-1 | Use the ClinicalTrials.gov Data API | Q6 D6.1, `docs/api/contract.md`, `docs/api/live-probe.md` | Designed |
| P2-2 | Authoritative: every fact from the API | Q3 (code computes numbers), Q4b fact sheet, Q14 exactness check, Q6 (no mirror) | Designed |
| P2-3 | Any endpoints/fields | Q6 S1-S3 (`/studies`, `/stats/field/values`, `/version`) | Designed (verify: O4 S1 semantics) |

## Part 3: Functional requirements

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P3-1 | Required `query` string | Q5 | Designed |
| P3-2 / 3-2a | Optional structured fields | Q5 (PDF names + extras) | Designed |
| P3-3 | Document request schema (names, types, required, validation) | Q5 table; OpenAPI generated (Q12); README section | Designed + Planned (README) |
| P3-4 | Example request works | Q5 merge rule 3 ("this drug" -> `drug_name`); Q18 E2E case | Designed |
| P3-5 | Structured response describing a visualization | Q12 envelope | Designed |
| P3-6 | `type` | Q12 | Designed |
| P3-7 | Human-readable `title` | Q2 D2.2 (AI-written), Q4b checks + template fallback | Designed |
| P3-8 | `encoding` (incl. nodes/edges) | Q12 per-type channels, Q13 node/edge encoding | Designed |
| P3-9 | `data` with everything needed to render | Q12 (flat rows; nodes/edges; no extra calls needed to draw) | Designed |
| P3-10 | Render metadata (units, sorting, granularity, grouping) | Q12 channel descriptor (`unit`, `sort`, `time_unit`), `meta.sort`, Q9 `additive`/`counting_rule` | Designed |
| P3-11 | Notes on assumptions, filters, interpretation | Q4a `assumptions`, Q12 `meta` (interpretation, filters, warnings, excluded, api_queries) | Designed |
| P3-12 | Document response schema (no guessing) | Q12 + OpenAPI + README section; Q19 renderer as proof | Designed + Planned (README) |
| P3-13 | Simple frontend demo (bonus) | Q19 | Designed |
| P3-14 | Focus on backend + structured outputs | Q15/Q19 (frontend is a reference renderer; backend first in the plan) | Designed |

## Part 4: Visualization requirements

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P4-1 | Answer is a visualization spec | Q1, Q12 (incl. `metric` for single numbers) | Designed |
| P4-2a | Bar / grouped bar | Q1, Q12 | Designed |
| P4-2b | Time series | Q1, Q10 (zero-fill, estimated flags), Q12 | Designed |
| P4-2c | Scatter | Q1, Q12 (one point per trial) | Designed |
| P4-2d | Histogram | Q1, Q10 (overflow bin), Q12 | Designed |
| P4-2e | Network graph (drugs, sponsors, conditions, investigators, sites) | Q13 (6 network types, incl. investigator ↔ site) | Designed |
| P4-3 | Single coherent approach | Q1 shape, Q15 registry-driven engine | Designed |
| P4-4 | Meaningful networks | Q13 (distinct-trial weights, Jaccard, pruning, communities, citations) | Designed |
| P4-5 | Broad query coverage | Q1 (9 types + 9 extra dimensions), Q18 (~60 live E2E questions) | Designed |

## Part 5: Deep citations (bonus)

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P5-1 / 5-1a | Every datum (incl. node/edge weights) references its trials | Q14 (all chart types), Q13, Q16 `result_datums` | Designed |
| P5-2 | `nct_id` | Q14 | Designed |
| P5-3 | Exact excerpt or field/value | Q14 (`field` + exact `excerpt`, raw bytes kept, exactness check) | Designed |
| P5-4 | Citations inside the data row | Q12 / Q14 | Designed |

Count-only strategies (S1/S2) cite the reproducing API query and fetch trial citations on demand (Q14): **Designed (verify: O4)**.

## Part 6: Submission

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P6-1 | All source code needed to run | Q15 Compose stack | Planned |
| P6-2 | README: install, configure, start | Q15 one-command demo (`make up`) | Planned |
| P6-3 | README: request/response schema docs | Q5, Q12 | Planned |
| P6-4 | README: design decisions + tradeoffs | `docs/design/` (this folder) | Planned |
| P6-5 | README: limitations + future work | Collected across Q6, Q8, Q11, Q13, Q15, Q19 | Planned |
| P6-6 | 3-5 example queries with actual JSON outputs | Q18 D18.3 (script-generated, schema- and citation-checked; picked from passing E2E cases) | Planned |
| P6-7 | Small UI (bonus) | Q19 | Designed |
| P6-8 | Deployed endpoint (bonus) | Q19 (`api.engineeradriel.com`) | Designed (O8 DNS) |
| P6-9 | Demo video (bonus) | Q19 (optional) | Planned |
| P6-10 | Submit before Sun 10/25 15:00 KST via Ashby | Logistics | Planned |
| P6-11 | Zip or GitHub link | Q19 (zip + endpoint) | Designed |

## Part 7: Evaluation criteria

| ID | Criterion | Covered by | Status |
|---|---|---|---|
| P7-1 | Clear, rational design decisions | `docs/design/` (every decision with reasons + alternatives) | Designed |
| P7-2 | Maintainable structure, extensibility | Q15 (modules, registry), Q2 typed stages | Designed |
| P7-3 | Real-world API data handling | Q6-Q11, live probe | Designed |
| P7-4 | Avoid hallucination-prone steps | Q3 (AI never produces numbers), Q4b fact sheet | Designed |
| P7-5 | Validation / constraints | Q4a strict plan, Q4b V1-V9, Q5/Q5b | Designed |
| P7-6 | Planning, reasoning, appropriate tools | Q3 planning agent + tools, Q15 LangGraph | Designed |
| P7-7 | Readability, organisation, docs | Q15 structure, Q18 lint/types in CI | Designed |
| P7-8 | Correctness, robustness | Q8, Q17, Q18 | Designed |
| P7-9 | Breadth of query types | Q1 | Designed |
| P7-10 | No one-off hacks | Q15 registry | Designed |
| P7-11 | Rich visualizations | Q13 | Designed |
| P7-12 | Unambiguous schemas | Q4a, Q5, Q12 | Designed |
| P7-13 | Frontend-friendly spec | Q12, Q19 renderer | Designed |
| P7-B | Deep citations bonus | Q14 | Designed |

## Part 8: Integrity note

| ID | Requirement | Covered by | Status |
|---|---|---|---|
| P8-1 | README: tools used | O7 README outline | Planned |
| P8-2 | README: how correctness was validated | Q18 (test layers, AI eval, live E2E report, citation exactness), Q16 `traces`/`llm_usage` | Designed + Planned (README) |
| P8-3 | README: designed vs generated | O7 README outline; `docs/design/` records which decisions the user made | Planned |
| P8-4 | Evidence of construction, testing, iteration | `docs/` history, git commits, Q18 D18.6 (bug -> regression test) | Designed |

## Appendix: example questions

| ID | Question | Plan (Q1/Q3/Q4a) | Chart | Notes |
|---|---|---|---|---|
| PA-1 | [drug] trials per year since 2015 | drug filter + `start_year_min=2015`, dimension `start_year` | time_series | Q10 zero-fill, estimated flags, ends at current year |
| PA-2 | Trials started each year for [condition] | condition filter, `start_year` | time_series | Broad conditions -> parallel slices / job (Q6) |
| PA-3 | [condition] trials across phases | condition, `phase` | bar_chart | Combined phase buckets (Q9) |
| PA-4 | Most common intervention types | drug/condition, `intervention_type` | bar_chart (sorted) | Once per distinct type per trial (Q9) |
| PA-5 | Phases: Drug A vs Drug B | 2 groups, `phase` | grouped_bar_chart | `group_overlap` (Q9) |
| PA-6 | Sponsor categories across two conditions | 2 groups, `sponsor_class` | grouped_bar_chart | Lead sponsor class (Q7) |
| PA-7 | Countries with most recruiting trials for [condition] | condition + status RECRUITING, `country` | bar_chart (top-N) | Overall status; once per country (Q7, Q9) |
| PA-8 | Sponsors ↔ drugs network for [condition] | condition, `sponsor` × `drug` | network_graph | MeSH drugs, placebo excluded, pruning (Q11, Q13) |
| PA-9 | Drug ↔ drug co-occurrence (unscoped) | `drug` co-occurrence, no scope | network_graph | ~289k candidate trials -> **background job** (Q6); the planner may suggest a scope in `assumptions` |

All 9: **Designed**. They're also the first cases in the live E2E suite (Q18).
