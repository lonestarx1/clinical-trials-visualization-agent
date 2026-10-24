# Part 1: Problem Overview

## 1. Source text (verbatim)

> You will build an AI-enabled backend that answers questions about clinical trials using the **ClinicalTrials.gov API**. The user will provide a natural-language query, along with optional structured fields (which you may define). Your system must:
>
> 1. Interpret the user's question.
> 2. Retrieve relevant data from ClinicalTrials.gov.
> 3. Identify if a visualization is needed and what type of visualization is suitable for the given question.
> 4. Produce a **visualization specification** that answers the question.
>
> A frontend is **not required**, but your output must be clear and structured so that a frontend can render the visualization reliably.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P1-0 | MUST | The backend is **AI-enabled** (an AI component is part of the design). | "AI-enabled backend" |
| P1-1 | MUST | Accept a natural-language query **together with** optional structured fields we define. | "natural-language query, along with optional structured fields (which you may define)" |
| P1-2 | MUST | **Interpret** the question: work out the intent, entities, filters and what is being measured. | "Interpret the user's question." |
| P1-3 | MUST | **Retrieve relevant** data from ClinicalTrials.gov: the right records for the question, not just any records. | "Retrieve relevant data from ClinicalTrials.gov." |
| P1-4a | MUST | **Decide whether** a visualization is needed. | "Identify if a visualization is needed" |
| P1-4b | MUST | **Choose the suitable chart type** for the question. | "what type of visualization is suitable for the given question" |
| P1-5 | MUST | Produce a **visualization specification** that **answers the question**. A chart that is on-topic but doesn't answer the question fails this. | "Produce a visualization specification that answers the question." |
| P1-6 | MUST | Output is **clear and structured** so a frontend can render it **reliably**: the same schema every time and no ambiguous fields. | "your output must be clear and structured so that a frontend can render the visualization reliably" |
| P1-7 | MAY | A frontend is not required. | "A frontend is not required" |

## 3. What it really means

- The four steps map one-to-one to pipeline stages: **interpret -> retrieve -> choose chart -> build spec**. The README and code should make these four stages visible by name, because a grader will look for them.
- "Answers the question" sets the bar for correctness. Example: "How has the number changed **per year since 2015**?" needs a yearly time series that **starts at 2015**, not a bar chart of phases.
- "Reliably" means **deterministic, schema-valid output**: the same request shape gets the same response shape, and the LLM never writes the final JSON freehand.
- The query and the structured fields work **together**. The Part 3 example says "this drug" in the query, with the drug only named in `drug_name`. The interpreter must resolve that reference.

## 4. Ambiguities and proposed decisions

### Tension: "Identify if a visualization is needed" vs Part 4 "The answer to the query must be a visualization"

Some questions don't naturally need a chart:
- a single number: "How many trials does pembrolizumab have?"
- a lookup: "What is NCT01234567 about?"
- off-topic: "What's the weather?"

**Proposed decision:** every response has the same top-level shape. The planner classifies each request, and its reasoning is reported in `meta`:

| Case | Response |
|---|---|
| Needs a chart | A normal chart spec. |
| A single number | A minimal chart type (e.g. `metric` / single-value card) or a one-bar chart, with a note in `meta` saying no multi-point chart was needed. This still satisfies Part 4 because the answer is a structured visual spec. |
| Not answerable from ClinicalTrials.gov, or not about trials | A structured response with no chart and a clear reason (e.g. `visualization: null` plus `meta.status = "unsupported"` and a message). No invented chart. |

This honours both parts: we **identify** need (Part 1), and whenever an answer exists it **is** a visualization (Part 4).

### Other decisions

- **What "relevant" means.** Use the API's own search parameters (condition, intervention, sponsor, location, status, dates) to filter records on the API side, rather than fetching broadly and filtering in Python. Report the filters used in `meta`.
- **What "interpret" covers.** At minimum: entities (drug, condition, sponsor, country), the measure (count of trials), group-by dimension(s), time range, status filter, and comparison groups (A vs B).

## 5. Acceptance checks

- [ ] The four stages exist as named, separate steps in the code and are described in the README.
- [ ] A test shows the "this drug" query plus `drug_name` resolves correctly.
- [ ] A single-number question returns a valid response with a note.
- [ ] An off-topic question returns a structured "unsupported" response, not a made-up chart.
- [ ] The response validates against the published schema on every example run.
