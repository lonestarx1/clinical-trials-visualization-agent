# Design Q5b: Input Guard (rejecting obviously malicious requests)

Status: **Decided** (2026-10-24)

## Principle

The guard is **defence in depth**, not the main defence. An AI classifier can be fooled, so the system must stay safe even when the guard misses something. The main defences are structural:

- The planner can only output a strict, enum-based QueryPlan (Q3, Q4a).
- Agent tools are read-only and return no chart data (Q3).
- Every user term is escaped/quoted before entering an Essie expression (Q5).
- No secrets or internal configuration are ever placed in model context.

## Layers

| Order | Layer | What it does |
|---|---|---|
| 1 | **Code checks** | Request schema and length limits (Q5); reject control characters; per-client rate limiting |
| 2 | **AI guard** | A small, fast model (e.g. `gpt-5.4-nano`, configurable) labels the request: `ok` \| `off_topic` \| `malicious` |

**Malicious** includes:
- prompt injection ("ignore previous instructions...")
- attempts to extract system prompts, keys or configuration
- abusive content
- attempts to use the service for something other than trial analytics, such as code execution or acting as a general chatbot

## Behaviour

| Decision | Detail |
|---|---|
| D5b.1 | The guard runs **in parallel** with the planning agent. If the guard rejects, the planner is cancelled, so no extra latency on the happy path. |
| D5b.2 | `malicious` -> **400** with a short, generic reason (`"Request rejected by input policy"`). The full classification and reason are logged only, so attackers don't learn what to avoid. |
| D5b.3 | `off_topic` is **not** rejected by the guard. It's passed on so the planner can return the structured "out of scope" response from Q1 (more helpful to the user). |
| D5b.4 | **Fail closed, with retry.** On guard timeout/error: retry once (short backoff; optionally on a fallback model). If it still fails, the request is rejected with **503** `"Safety check unavailable, please retry"`. Not a 400, because it isn't the user's fault. |
| D5b.5 | The guard sees the `query` **and** all free-text structured fields (entity names can also carry injection text). |
| D5b.6 | The guard verdict, model and latency are recorded in the trace / `meta.guard` (verdict only for accepted requests). |

## Tradeoffs

- **Fail closed** puts safety first: if the guard is down, the service is down. This is mitigated by the retry and a short timeout. We accept the availability cost, as the user decided.
- **False positives** (a real question flagged as malicious) are possible. Mitigation: a narrow prompt focused on clearly malicious patterns, plus test cases with real questions to measure them.

## Requirement links

P7-4, P7-5 (validation/constraints), P7-8 (robustness).
