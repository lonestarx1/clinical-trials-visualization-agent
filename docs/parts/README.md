# Assignment parts: requirement breakdown

The brief for this exercise is confidential, so it is not reproduced here. Each file below takes one part of it and breaks it down in the same layout:

1. **Summary:** the part of the brief in our own words.
2. **Atomic requirements:** each requirement gets its own ID (e.g. `P3-12`) and a level (see below). The design docs and [`../design/requirements-coverage.md`](../design/requirements-coverage.md) refer to these IDs.
3. **What it means:** our reading of it.
4. **Ambiguities and decisions:** gaps or tensions, what we first proposed, and where the design settled it.
5. **Acceptance checks:** how we show the requirement is met.

A summary of the whole brief, with our analysis, is in [`../assignment.md`](../assignment.md).

## Requirement levels

| Level | Meaning | How the brief signals it |
|---|---|---|
| MUST | Missing it fails the assignment. | Stated as mandatory |
| SHOULD | Assessed; leaving it out costs points. | Stated as a goal, or as scoring higher |
| MAY | Allowed; we can choose. | Explicitly allowed, or given as an example |
| BONUS | Extra credit. | Marked as a bonus or optional |

## Files

| File | Part | Main content |
|---|---|---|
| [00-preamble.md](00-preamble.md) | Header | Goal, time box, tools |
| [01-problem-overview.md](01-problem-overview.md) | 1 | The 4 steps the system must do; frontend not required |
| [02-data-source.md](02-data-source.md) | 2 | ClinicalTrials.gov API is the only source of truth |
| [03-functional-requirements.md](03-functional-requirements.md) | 3 | Request schema (3.1) and response schema (3.2) |
| [04-visualization-requirements.md](04-visualization-requirements.md) | 4 | Answer is always a chart; support several chart types |
| [05-deep-citations.md](05-deep-citations.md) | 5 | Bonus: per-datum `nct_id` + exact excerpt |
| [06-submission-requirements.md](06-submission-requirements.md) | 6 | Deliverables: code, README, 3-5 example runs, optional demo |
| [07-evaluation-criteria.md](07-evaluation-criteria.md) | 7 | Evaluation weights |
| [08-integrity-note.md](08-integrity-note.md) | 8 | Tool-use disclosure: tools used, validation, designed vs generated |
| [09-appendix-example-queries.md](09-appendix-example-queries.md) | Appendix | 9 example questions in 5 classes |

## Key tensions across parts

**All are resolved in the design** (see [`../design/README.md`](../design/README.md)):

1. Q1, Q3 and Q17: a `metric` chart for single numbers, and an `out_of_scope` status with no chart.
2. Q19: an archive of the repository plus a deployed endpoint.
3. Q14: 5 citations per data point, a paginated citations endpoint, and a size-guarded `full` mode.
4. Q7 and the live probe: the API resolves drug synonyms itself, so the LLM never invents them.
5. Q12: the brief's example shape is kept and extended.

The original list, kept for the record:

These are the places where two parts pull in different directions, or the brief is vague. Each one is discussed in its part file.

1. **Deciding whether a chart is needed (Part 1) vs "the answer is always a visualization" (Part 4).** See 01 and 04.
2. **Submission format:** the brief asks for an archive, and a repository link was also accepted. See 06.
3. **Citations for every contributing trial (Part 5) vs response size**, when a bar covers thousands of trials. See 05.
4. **The API as the authoritative source (Part 2) vs using the LLM to expand drug synonyms** (e.g. Keytruda -> pembrolizumab). See 02.
5. **The example response shape (Part 3.2) is illustrative only**, but staying close to it makes the output familiar to readers of the brief. See 03.

## Master requirement checklist

The status and design coverage of each ID are tracked in [`../design/requirements-coverage.md`](../design/requirements-coverage.md).

| ID | Level | Requirement (short) |
|---|---|---|
| P0-1 | MUST | Backend service: clinical-trial question -> structured visualization output |
| P0-2 | MUST | Data backed by the ClinicalTrials.gov API |
| P0-3 | SHOULD | Scope fits the time box (about 24 hours) |
| P1-1 | MUST | Accept an NL query plus optional structured fields |
| P1-2 | MUST | Interpret the question |
| P1-3 | MUST | Retrieve relevant data from ClinicalTrials.gov |
| P1-4 | MUST | Decide if a visualization is needed and which type fits |
| P1-5 | MUST | Produce a visualization spec that answers the question |
| P1-6 | MUST | Output clear and structured enough for reliable frontend rendering |
| P1-7 | MAY | Frontend (not required) |
| P2-1 | MUST | ClinicalTrials.gov Data API is the authoritative source |
| P2-2 | MAY | Use any endpoints/fields |
| P3-1 | MUST | Accept required `query` (string) |
| P3-2 | MAY | Define optional structured fields |
| P3-3 | MUST | Document request schema: names, types, optional/required, validation |
| P3-4 | SHOULD | Example request (query + `drug_name`) works as given |
| P3-5 | MUST | Return a structured response describing a visualization |
| P3-6 | MUST | Viz spec has `type` |
| P3-7 | MUST | Viz spec has `title` |
| P3-8 | MUST | Viz spec has `encoding` (fields -> channels, incl. nodes/edges) |
| P3-9 | MUST | Viz spec has `data` |
| P3-10 | MUST | Response metadata for rendering (units, sorting, granularity, grouping) |
| P3-11 | MAY | Notes on assumptions, filters, interpretation |
| P3-12 | MUST | Document response schema so a frontend dev needs no guessing |
| P3-13 | BONUS | Simple frontend demo |
| P4-1 | MUST | The answer is a visualization (structured spec) |
| P4-2 | SHOULD | Support multiple viz types |
| P4-3 | SHOULD | Single coherent approach across query types |
| P4-4 | SHOULD | Rich visualizations, e.g. meaningful network graphs |
| P4-5 | SHOULD | Broad query coverage |
| P5-1 | BONUS | Each datum references the contributing trial records |
| P5-2 | BONUS | Each reference has `nct_id` |
| P5-3 | BONUS | Each reference has an exact excerpt or field/value from the API |
| P5-4 | BONUS | Applies to bars, time buckets, nodes and edges |
| P6-1 | MUST | Submit all source code needed to run the service |
| P6-2 | MUST | README: how to run (install, configure, start) |
| P6-3 | MUST | README: request/response schema docs |
| P6-4 | MUST | README: key design decisions and tradeoffs |
| P6-5 | MUST | README: limitations and future improvements |
| P6-6 | MUST | 3-5 example queries with actual JSON outputs |
| P6-7 | BONUS | Small UI |
| P6-8 | BONUS | Deployed endpoint |
| P6-9 | BONUS | Short demo video |
| P6-10 | MUST | Submit within the time box |
| P7-1..13 | SHOULD | Evaluation sub-criteria (see 07) |
| P8-1 | MUST | README: which tools were used |
| P8-2 | MUST | README: how correctness was validated |
| P8-3 | MUST | README: designed deliberately vs generated and adapted |
| P8-4 | SHOULD | Evidence of construction, testing, iteration |
| PA-1..9 | SHOULD | The 9 appendix example questions work |
