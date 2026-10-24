# Design Q2: Overall Pipeline

Status: **Decided** (2026-10-24, with the user)

## Stages

```
request
  1. Validate input      code  typed request schema; 422 on bad input; sanitise + escape terms (Q5)
  1b. Guard              AI    malicious-request classifier, runs in parallel with stage 2;
                               reject -> 400; fail closed after 1 retry -> 503 (Q5b)
  2. Plan (agent)        AI    bounded agent with code tools (list_options, check_plan, count_trials,
                               submit_plan) -> QueryPlan (strict schema). See Q3.
  3. Validate plan       code  final gate: re-runs every check on the submitted plan; merges user fields
  4. Compile             code  QueryPlan -> API searches (one per comparison group) + field list
  5. Retrieve            code  cache, rate limiter, retries/backoff, page cap
  6. Normalize           code  raw study JSON -> typed Trial records, each value keeps its field path
  7. Aggregate           code  buckets / nodes / edges / points, each with contributing trials + evidence
  8. Build chart         code  rule-based chart type -> spec (type, encoding, data, meta)
  9. Narrate             AI    title + one-sentence summary, from the computed chart data only
 10. Validate narration  code  sanity checks on the title and summary (design: see Q on AI validation)
 11. Verify output       code  response schema + invariants (e.g. bucket count == citation count)
 12. Respond + trace     code  meta: interpretation, filters, retrieval stats, model calls, timings
```

## Decisions

| # | Decision | Reason |
|---|---|---|
| D2.1 | **The AI is used in exactly three stages: Guard (1b, classification only), Plan (2), and Narrate (9).** Everything else is deterministic code. | Limits hallucination risk to well-defined outputs that can each be checked (Part 7: "avoid hallucination-prone steps", "include validation or constraints"). |
| D2.2 | **The AI writes the chart title**, then a sanity check runs on it. | A natural title reads better than a template. Risk: the title states filters/entities that weren't applied. |
| D2.3 | **The AI writes a one-sentence summary of the chart, grounded in the computed numbers**, then a sanity check runs on it. | Useful for the frontend. Risk: wrong numbers or claims. The AI only sees the aggregated chart data (never raw text it could misquote), and every number it states must be checkable. |
| D2.4 | **If no valid plan exists within the agent's step/time limit** (Q3), return a structured "could not interpret" response with the AI's best attempt and the validation errors. | Honest and debuggable. Never an invented chart. |
| D2.5 | Each stage is its **own module with typed input/output**. | Each stage can be tested on its own, models can be swapped, and the trace is clear. |
| D2.6 | Every stage writes to a **trace** that feeds `meta` and the logs. | Traceability (Part 7) and debugging. |

## Open, decided in a later question

- **How to validate AI output** (plan, title, summary): which checks run, and what happens when a check fails (repair, retry, or fallback to a template). The user wants to ideate this together at that step.
