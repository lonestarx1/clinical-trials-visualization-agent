# Design Q2: Overall pipeline

Status: **Decided** (2026-10-24)

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
  9. Narrate             AI    title, from the computed chart data only (the summary was removed, Q4b)
 10. Validate narration  code  sanity checks on the title (Q4b)
 11. Verify output       code  response schema + invariants (e.g. bucket count == citation count)
 12. Respond + trace     code  meta: interpretation, filters, retrieval stats, model calls, timings
```

## Decisions

| # | Decision | Reason |
|---|---|---|
| D2.1 | **The AI is used in exactly three stages: Guard (1b, classification only), Plan (2), and Narrate (9).** Everything else is deterministic code. | Limits hallucination risk to well-defined outputs that can each be checked (Part 7: "avoid hallucination-prone steps", "include validation or constraints"). |
| D2.2 | **The AI writes the chart title**, then a sanity check runs on it. | A natural title reads better than a template. Risk: the title states filters/entities that weren't applied. |
| D2.3 | **Superseded (2026-10-24).** The first design had the AI also write a one-sentence summary of the chart, grounded in the computed numbers and sanity-checked. It was removed after live testing: there is no summary, and the chart, data table, counting rule and method notes explain the result ([Q4b revision](04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)). | The summary was meant to help the frontend. The checks caught wrong numbers but not misleading framing, and the assignment only requires a title. |
| D2.4 | **If no valid plan exists within the agent's step/time limit** (Q3), return a structured "could not interpret" response with the AI's best attempt and the validation errors. | Honest and debuggable. Never an invented chart. |
| D2.5 | Each stage is its **own module with typed input/output**. | Each stage can be tested on its own, models can be swapped, and the trace is clear. |
| D2.6 | Every stage writes to a **trace** that feeds `meta` and the logs. | Traceability (Part 7) and debugging. |

## Validating the AI's output

Which checks run on the AI's output (the plan and the title), and what happens when a check fails (an error back to the planner, a retry, or a template fallback), is decided in [Q4b](04b-ai-validation.md).
