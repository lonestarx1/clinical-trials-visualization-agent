# Assignment Parts: Requirement Breakdown

Each file below takes one part of Cheiron's assignment and breaks it down in the same layout:

1. **Source text:** copied word for word from `docs/assignment.md` Part A. This is the only text that comes from Cheiron.
2. **Atomic requirements:** each requirement gets its own ID and a level (see below), plus the exact phrase it comes from.
3. **What it really means:** our reading of it.
4. **Ambiguities and proposed decisions:** gaps or tensions, and what we plan to do. These are proposals until we confirm them.
5. **Acceptance checks:** how we will prove the requirement is met.

Everything after section 1 is our own work, not Cheiron's.

## Requirement levels

| Level | Meaning | Source wording |
|---|---|---|
| MUST | Missing it fails the assignment. | "must", "required", "Your system must" |
| SHOULD | Graded; leaving it out costs points. | "should aim to", "scored higher", evaluation criteria |
| MAY | Allowed; we can choose. | "may", "examples (not required)" |
| BONUS | Extra credit. | "bonus", "optional" |

## Files

| File | Part | Main content |
|---|---|---|
| [00-preamble.md](00-preamble.md) | Header | Time, tools, primary goal |
| [01-problem-overview.md](01-problem-overview.md) | 1 | The 4 steps the system must do; frontend not required |
| [02-data-source.md](02-data-source.md) | 2 | ClinicalTrials.gov API is the only source of truth |
| [03-functional-requirements.md](03-functional-requirements.md) | 3 | Request schema (3.1) and response schema (3.2) |
| [04-visualization-requirements.md](04-visualization-requirements.md) | 4 | Answer is always a chart; support several chart types |
| [05-deep-citations.md](05-deep-citations.md) | 5 | Bonus: per-datum `nct_id` + exact excerpt |
| [06-submission-requirements.md](06-submission-requirements.md) | 6 | Code, README, 3-5 example runs, optional demo |
| [07-evaluation-criteria.md](07-evaluation-criteria.md) | 7 | Grading weights |
| [08-integrity-note.md](08-integrity-note.md) | 8 | README section on AI tool use and validation |
| [09-appendix-example-queries.md](09-appendix-example-queries.md) | Appendix | 9 example questions in 5 classes |

## Key tensions found across parts

**All resolved in the design** (see [`../design/README.md`](../design/README.md)):
1 -> Q1/Q3/Q17 (`metric` chart, `out_of_scope` status). 2 -> Q19 (zip + deployed endpoint). 3 -> Q14 (5 per data point + paginated endpoint, size-guarded `full`). 4 -> Q7 + live probe (the API resolves drug synonyms; the LLM never invents them). 5 -> Q12 (PDF shape kept, extended).

Original list:

These are the places where two parts pull in different directions, or the text is vague. Each one is discussed in its part file.

1. **"Identify if a visualization is needed" (Part 1) vs "The answer to the query must be a visualization" (Part 4).** See 01 and 04.
2. **"Submit a zip file" (Part 6) vs the email's "A file or GitHub link both work".** See 06.
3. **"Each visualized datum includes references to the underlying trial records" (Part 5) vs response size** when a bar covers thousands of trials. See 05.
4. **"Authoritative data source" (Part 2) vs using the LLM to expand drug synonyms** (e.g. Keytruda -> pembrolizumab). See 02.
5. **Example response shape (Part 3.2) is "illustrative only"**, but staying close to it makes the output easy to read for reviewers. See 03.

## Master requirement checklist

Status: `[ ]` not started, `[~]` in progress, `[x]` done and verified. Design coverage per ID: [`../design/requirements-coverage.md`](../design/requirements-coverage.md).

| ID | Level | Requirement (short) | Status |
|---|---|---|---|
| P0-1 | MUST | Backend service: clinical-trial question -> structured visualization output | [ ] |
| P0-2 | MUST | Data backed by the ClinicalTrials.gov API | [ ] |
| P0-3 | SHOULD | Scope fits ~24h | [ ] |
| P1-1 | MUST | Accept an NL query plus optional structured fields | [ ] |
| P1-2 | MUST | Interpret the question | [ ] |
| P1-3 | MUST | Retrieve relevant data from ClinicalTrials.gov | [ ] |
| P1-4 | MUST | Decide if a visualization is needed and which type fits | [ ] |
| P1-5 | MUST | Produce a visualization spec that answers the question | [ ] |
| P1-6 | MUST | Output clear and structured enough for reliable frontend rendering | [ ] |
| P1-7 | MAY | Frontend (not required) | [ ] |
| P2-1 | MUST | ClinicalTrials.gov Data API is the authoritative source | [ ] |
| P2-2 | MAY | Use any endpoints/fields | [ ] |
| P3-1 | MUST | Accept required `query` (string) | [ ] |
| P3-2 | MAY | Define optional structured fields | [ ] |
| P3-3 | MUST | Document request schema: names, types, optional/required, validation | [ ] |
| P3-4 | SHOULD | Example request (query + `drug_name`) works as given | [ ] |
| P3-5 | MUST | Return a structured response describing a visualization | [ ] |
| P3-6 | MUST | Viz spec has `type` | [ ] |
| P3-7 | MUST | Viz spec has `title` | [ ] |
| P3-8 | MUST | Viz spec has `encoding` (fields -> channels, incl. nodes/edges) | [ ] |
| P3-9 | MUST | Viz spec has `data` | [ ] |
| P3-10 | MUST | Response metadata for rendering (units, sorting, granularity, grouping) | [ ] |
| P3-11 | MAY | Notes on assumptions, filters, interpretation | [ ] |
| P3-12 | MUST | Document response schema so a frontend dev needs no guessing | [ ] |
| P3-13 | BONUS | Simple frontend demo | [ ] |
| P4-1 | MUST | The answer is a visualization (structured spec) | [ ] |
| P4-2 | SHOULD | Support multiple viz types | [ ] |
| P4-3 | SHOULD | Single coherent approach across query types | [ ] |
| P4-4 | SHOULD | Rich visualizations, e.g. meaningful network graphs | [ ] |
| P4-5 | SHOULD | Broad query coverage | [ ] |
| P5-1 | BONUS | Each datum references the contributing trial records | [ ] |
| P5-2 | BONUS | Each reference has `nct_id` | [ ] |
| P5-3 | BONUS | Each reference has an exact excerpt or field/value from the API | [ ] |
| P5-4 | BONUS | Applies to bars, time buckets, nodes and edges | [ ] |
| P6-1 | MUST | Submit all source code needed to run the service | [ ] |
| P6-2 | MUST | README: how to run (install, configure, start) | [ ] |
| P6-3 | MUST | README: request/response schema docs | [ ] |
| P6-4 | MUST | README: key design decisions and tradeoffs | [ ] |
| P6-5 | MUST | README: limitations and future improvements | [ ] |
| P6-6 | MUST | 3-5 example queries with actual JSON outputs | [ ] |
| P6-7 | BONUS | Small UI | [ ] |
| P6-8 | BONUS | Deployed endpoint | [ ] |
| P6-9 | BONUS | Short demo video | [ ] |
| P6-10 | MUST | Submit before Sun 10/25 15:00 KST via Ashby | [ ] |
| P7-1..13 | SHOULD | Grading sub-criteria (see 07) | [ ] |
| P8-1 | MUST | README: which tools were used | [ ] |
| P8-2 | MUST | README: how correctness was validated | [ ] |
| P8-3 | MUST | README: designed deliberately vs generated and adapted | [ ] |
| P8-4 | SHOULD | Evidence of construction, testing, iteration | [ ] |
| PA-1..9 | SHOULD | The 9 appendix example questions work | [ ] |
