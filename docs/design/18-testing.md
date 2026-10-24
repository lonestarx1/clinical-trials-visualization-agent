# Design Q18: Testing Strategy

Status: **Decided** (2026-10-24)

## Layers

| Layer | What it covers | Network / AI? | Runs in CI |
|---|---|---|---|
| **Unit** | Query AST -> Essie compilation (incl. escaping / injection cases), date parsing (partial, estimated, future), phase bucketing (combined/split), name normalisation (drugs, placebo, sponsors, investigators), counting rules (Q9), missing-value handling (Q10), chart builders (per type), network pruning + Jaccard + communities (Q13), fact sheet (Q4b), every plan check (V1-V4) and narration check (V6-V9), citation exactness check (Q14), rate limiter and retry/backoff (fake clock) | No | Yes |
| **Contract** | Every response (every chart type, every `status`, every error code) validates against the published response schema; the OpenAPI document is generated and snapshot-tested | No | Yes |
| **Integration** | The full pipeline / LangGraph graph on **recorded real ClinicalTrials.gov responses** (fixtures from `docs/api/probe-data/samples` plus recorded pages) with a **scripted fake LLM** (fixed planner tool calls and narration). Deterministic and fast. | No | Yes |
| **Database** | Against a real Postgres (Docker): cache revalidation (Q8), job claiming with `SKIP LOCKED`, crash recovery, one-active-job uniqueness, keyset citation pagination, retention cleanup, `llm_usage` cost and budget cap | No | Yes (Postgres service container) |
| **Cross-check** | For real queries, our aggregated counts vs the API's own `countTotal` for the same filter (e.g. our "Phase 3" bucket vs `AREA[Phase]PHASE3` with the same scope): **two independent methods must agree** (exactly for additive single-valued dimensions; per-value for multi-valued ones) | Live API | Opt-in (`-m live`) |
| **AI evaluation** | ~40 questions with expected plan properties (intent, chart type, dimension(s), filters, scope verdict). Covers the 9 appendix questions, the Q1 "beyond appendix" types, ambiguous phrasings, out-of-scope questions, **prompt-injection attempts**, and structured-field conflicts. Scored per property; guard precision/recall reported. | Real OpenAI | Opt-in (`-m eval`) |
| **Live end-to-end** (expanded on the user's request) | **~60 questions** run through the **full pipeline with the real ClinicalTrials.gov API and real OpenAI models**, over HTTP against the running Docker Compose stack. See "Live end-to-end suite" below. | Live API + real AI | Opt-in (`-m e2e`); run before submission and after major changes |
| **Smoke** | `docker compose up` -> `/health` ok -> one real question end to end -> valid response | Yes | Manual / pre-submit |

## Live end-to-end suite

Unlike the AI evaluation (which scores the **plan** only), every case here runs the **whole system** on real data.

**Coverage targets (~60 questions):**
- all 9 appendix questions (PA-1..PA-9) with real entities
- every chart type at least 3 times
- every registry dimension and measure at least once (incl. the Q1 "beyond appendix" dimensions)
- every network type
- comparisons with 2, 3 and 4 groups
- structured-field cases: fields only, fields + query, field/query conflicts, `chart_type` override, `sponsor_role`, `match_mode`
- edge cases: no matching trials, out of scope, could-not-interpret, a typo entity, an injection attempt (expect 400), a broad question that becomes a background job (poll to completion), a revalidated cache hit

**Assertions per case:**
1. HTTP status and `status` as expected
2. response validates against the schema
3. expected chart type / dimension (where the question is unambiguous)
4. **citation exactness re-checked against freshly fetched live records** (a sample of citations per response)
5. **count cross-check** against the API's own `countTotal` for the same filters (where applicable)
6. invariants: `citation_count == value` for count charts; bars sum to `unique_trials` when `additive`; no silent exclusions (`meta.excluded` present when needed)
7. narration passed its checks (or the fallback is flagged)

**Budget:**
- Runs through the same global rate limiter, so roughly 10-20 minutes per full run.
- LLM cost is read from `llm_usage` and reported per run.
- A `--subset` flag runs a fast ~15-question slice.

**Output:** a report (pass/fail per case, latency, API calls, cache hits, LLM cost) saved under `docs/eval/`. Summarised in the README as validation evidence. The Part 6 example runs are picked from passing cases.

## Supporting decisions

| # | Decision |
|---|---|
| D18.1 | **Fixtures are real API data**, recorded once (live-probe samples + recorded pages), never hand-written JSON. Messy cases (multi-phase, missing start, future estimated start, 576 sites, placebo, combo) are covered by the saved samples. |
| D18.2 | **The LLM is a dependency we fake in offline tests** (scripted responses via the LangGraph model interface), so CI never needs a key and runs deterministically. |
| D18.3 | **Example runs (Part 6) are produced by a script** against the real system and then validated by the contract tests and the citation exactness check. They're never edited by hand. |
| D18.4 | **CI:** GitHub Actions runs lint (`ruff`), type checks (`mypy` or `pyright`), and the offline layers (unit, contract, integration, database) on every push. |
| D18.5 | **AI eval results** (scores per property, guard precision/recall, cost per question from `llm_usage`) are published in the README as validation evidence (Part 8). They're described honestly as new work for this project. |
| D18.6 | **Bug -> test:** every bug found during development gets a regression test (evidence of iteration, Part 8). |

## Requirement links

P7-7, P7-8 (code quality, correctness, robustness), P8-2, P8-4 (how correctness was validated, evidence of testing and iteration), P6-6 (actual example outputs), P5 (citation exactness).
