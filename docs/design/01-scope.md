# Design Q1: Scope (which questions we support)

Status: **Decided** (2026-10-24)

## Principle

Every supported question has the same shape:

> **measure** of trials matching **filters**, grouped by **one or two dimensions** (or linked as a network)

A question type is a combination of entries from registries (dimensions, measures, network types), not custom code. Adding a new dimension means one registry entry plus a test.

Priority is a **robust** design, not a minimal one. The "stretch" items from the first draft are now core.

## Core question types

| Type | Example | Chart |
|---|---|---|
| Time trend | "Pembrolizumab trials per year since 2015", optionally split into series (e.g. by phase) | `time_series` |
| Distribution | "Breast cancer trials by phase / status / study type / intervention type / sponsor class" | `bar_chart` |
| Top-N | "Top sponsors / drugs / conditions for Alzheimer's" | `bar_chart` (sorted) |
| Comparison | "Phases: Drug A vs Drug B" (2-4 groups of drugs, conditions or sponsors, compared on any dimension) | `grouped_bar_chart` |
| Geographic | "Countries with the most recruiting trials for X" | `bar_chart` (sorted, top-N) |
| Network | sponsor ↔ drug, drug ↔ drug, condition ↔ drug, sponsor ↔ condition, investigator ↔ site | `network_graph` |
| Numeric distribution | "Enrollment sizes / trial durations / number of sites" | `histogram` |
| Numeric relationship | "Enrollment vs duration per trial" | `scatter_plot` |
| Single number | "How many recruiting trials for X?" | `metric` |

All 9 appendix examples (PA-1..PA-9) are covered, as are all chart types listed in Part 4.

## Beyond the appendix (added after brainstorming realistic user questions)

Covered by the shape above with no extra work:
- "Industry vs academic share of X trials per year": time × sponsor class
- "Which conditions is pembrolizumab tested for most?": top-N conditions
- "What phases is Merck running right now?": sponsor + active-status filters
- "How long do Phase 3 Alzheimer's trials take?": duration histogram

Added as new **dimensions** (one registry entry each):

| Dimension | Example question |
|---|---|
| Results reported (yes/no) | "What share of completed X trials posted results?" |
| Age group (child / adult / older adult) | "How many X trials include children?" |
| Sex eligibility | "How many female-only trials for X?" |
| Healthy volunteers accepted | "Do X trials accept healthy volunteers?" |
| Allocation (randomized / non-randomized) | "How many X trials are randomized?" |
| Masking (open label ... quadruple) | "How many X trials are double-blind?" |
| Primary purpose (treatment, prevention, diagnostic, ...) | "Prevention vs treatment trials for X" |
| US state | "Which states have the most X trials?" |
| First-posted year (in addition to start year) | "How many X trials were registered each year?" |

Added as a new **network type**:
- sponsor ↔ collaborator: "Who partners with Merck?"

## Measures

- **Trial count** (default)
- **Total enrollment** and **median enrollment** (e.g. "How many participants are in Phase 3 trials for X?")

## Out of scope (structured "unsupported" response, never an invented chart)

| Request | Why |
|---|---|
| Efficacy / results ("Did drug X work?") | Results data is complex and easy to misread as a clinical conclusion |
| Patient matching ("Which trial fits me?") | Eligibility interpretation and medical-advice risk |
| Text summary of a single trial | Not a visualization |
| Facts outside ClinicalTrials.gov (approvals, mechanisms, prices) | Not in the authoritative source (Part 2) |
| Categorising stop reasons ("Why were X trials stopped?") | `whyStopped` is free text. Categorising it would need the LLM to label data, which is hallucination-prone. |

## Ambiguity policy

Ambiguous questions get a **best-effort chart**, and `meta` states the interpretation and assumptions. We never refuse silently, and we never chart something we can't support.

## Requirement links

P1-2, P1-4, P1-5 (interpret, choose chart, answer), P4-2..P4-5 (multiple types, coherent approach, rich networks, coverage), PA-1..PA-10 (appendix), P7-9..P7-11 (coverage grading).
