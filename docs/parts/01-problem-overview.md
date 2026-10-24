# Part 1: Problem overview

## 1. Summary

The service is an AI-enabled backend that answers questions about clinical trials from the ClinicalTrials.gov API. Its user sends a natural-language question, optionally with structured fields that we define. The service must:

1. interpret the question;
2. retrieve the relevant data from ClinicalTrials.gov;
3. decide whether a visualization is needed, and which type suits the question;
4. produce a visualization specification that answers the question.

No frontend is required, but the output must be clear and structured enough for a frontend to render it reliably.

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| P1-0 | MUST | The backend is **AI-enabled**: an AI component is part of the design. |
| P1-1 | MUST | Accept a natural-language query **together with** optional structured fields that we define. |
| P1-2 | MUST | **Interpret** the question: work out the intent, entities, filters and what is being measured. |
| P1-3 | MUST | **Retrieve relevant** data from ClinicalTrials.gov: the right records for the question, not just any records. |
| P1-4a | MUST | **Decide whether** a visualization is needed. |
| P1-4b | MUST | **Choose the chart type** that suits the question. |
| P1-5 | MUST | Produce a **visualization specification** that **answers the question**. A chart that is on-topic but doesn't answer the question fails this. |
| P1-6 | MUST | The output is **clear and structured** so a frontend can render it **reliably**: the same schema every time and no ambiguous fields. |
| P1-7 | MAY | A frontend is not required. |

## 3. What it means

- The four steps map one-to-one to pipeline stages: **interpret -> retrieve -> choose chart -> build spec**. The code and README should make these stages visible by name.
- "Answers the question" sets the bar for correctness. A question about trials "per year since 2015" needs a yearly time series that **starts at 2015**, not a bar chart of phases.
- "Reliably" means **deterministic, schema-valid output**: the same request shape gets the same response shape, and the LLM never writes the final JSON freehand.
- The query and the structured fields work **together**. In the brief's example request, the question says "this drug" and the drug is named only in `drug_name`. The interpreter must resolve that reference.

## 4. Ambiguities and decisions

### Tension: "decide whether a visualization is needed" vs "the answer must be a visualization" (Part 4)

Some questions don't naturally need a chart:
- a single number: "How many trials does pembrolizumab have?"
- a lookup: "What is NCT01234567 about?"
- off-topic: "What's the weather?"

**Decision:** every response has the same top-level shape. The planner classifies each request, and its reasoning is reported in `meta`:

| Case | Response |
|---|---|
| Needs a chart | A normal chart spec. |
| A single number | A minimal chart type (`metric`, a single-value card), with a note in `meta` that no multi-point chart was needed. This still satisfies Part 4, because the answer is a structured visual spec. |
| Not answerable from ClinicalTrials.gov, or not about trials | A structured response with no chart and a clear reason. No invented chart. |

This honours both parts: we **decide** whether a chart is needed (Part 1), and whenever an answer exists it **is** a visualization (Part 4).

**Resolved** in [design Q1](../design/01-scope.md) (the `metric` chart type), [Q3](../design/03-ai-vs-code.md) and [Q17](../design/17-error-handling.md). The no-chart case is a 200 response with `visualization: null` and a `status` such as `out_of_scope`, instead of the `unsupported` status first proposed here.

### Other decisions

- **What "relevant" means.** Use the API's own search parameters (condition, intervention, sponsor, location, status, dates) to filter records on the API side, rather than fetching broadly and filtering in Python. Report the filters used in `meta` ([design Q7](../design/07-query-compilation.md)).
- **What "interpret" covers.** At minimum: entities (drug, condition, sponsor, country), the measure (count of trials), group-by dimensions, time range, status filter, and comparison groups (A vs B) ([design Q4a](../design/04a-plan-schema.md)).

## 5. Acceptance checks

- [ ] The four stages exist as named, separate steps in the code and are described in the README.
- [ ] A test shows that the "this drug" query plus `drug_name` resolves correctly.
- [ ] A single-number question returns a valid response with a note.
- [ ] An off-topic question returns a structured response with no chart, not a made-up chart.
- [ ] The response validates against the published schema on every example run.
