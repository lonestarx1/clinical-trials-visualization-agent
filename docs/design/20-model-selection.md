# Design Q20 (O2): Selecting the AI model for each task

Status: **Process decided** (2026-10-24). Starting defaults set; final choices come from a measured comparison ("bake-off") once the AI evaluation set exists (Q18).

## Why this needs its own decision

The system calls an LLM in three places (Q2). Each has different needs, so one model for everything would be either too slow and expensive, or too weak:

| Stage | What it must do well | What matters most |
|---|---|---|
| **Guard** (Q5b) | Classify a request as `ok` / `off_topic` / `malicious` | Catch every attack (high recall), few false alarms, **low latency** (fail-closed, runs on every request) |
| **Planner** (Q3) | Multi-step tool calling, map language to registry enums, respect structured fields, produce a valid plan | **Plan accuracy** first, then latency; the most demanding task |
| **Narrator** (Q2, Q4b) | Write the **chart title** in **one call**, using fact-sheet placeholders (until 2026-10-24 also a one-sentence summary, now removed) | Instruction following (placeholders, no banned claims); low cost |
| **Fallback** (Q8) | Take over any stage when the primary model fails | A **different model family** than the primaries, so one provider-side model incident doesn't take out both |

## Candidates

The models allowed by Cheiron's key, checked live on 2026-10-24 (11 of 12 respond; `gpt-4.1-nano` returns 404, retired by OpenAI).

### Official prices (standard tier, USD per 1M tokens)

Source: [OpenAI API pricing](https://developers.openai.com/api/docs/pricing), read 2026-10-24.

| Model | Input | Cached input | Output | Family / type |
|---|---|---|---|---|
| gpt-5.4 | 2.50 | 0.25 | 15.00 | GPT-5.4, reasoning |
| gpt-5.4-mini | 0.75 | 0.075 | 4.50 | GPT-5.4, reasoning |
| gpt-5.4-nano | 0.20 | 0.02 | 1.25 | GPT-5.4, reasoning |
| gpt-5.2 | 1.75 | 0.175 | 14.00 | GPT-5.2, reasoning |
| gpt-5.1 | 1.25 | 0.125 | 10.00 | GPT-5.1, reasoning |
| gpt-5 | 1.25 | 0.125 | 10.00 | GPT-5, reasoning |
| gpt-5-mini | 0.25 | 0.025 | 2.00 | GPT-5, reasoning |
| gpt-4.1 | 2.00 | 0.50 | 8.00 | GPT-4.1, non-reasoning |
| gpt-4.1-mini | 0.40 | 0.10 | 1.60 | GPT-4.1, non-reasoning |
| gpt-4o-mini | 0.15 | 0.075 | 0.60 | GPT-4o, non-reasoning |
| gpt-4o-2024-08-06 | — | — | — | Not listed under standard inference pricing (only under fine-tuning) on the page read; **excluded** until its price is confirmed |

These numbers go into `pricing.yaml` with `version` and `last_verified: 2026-10-24` (Q16 `llm_usage`). Reasoning models also bill **reasoning tokens** as output, which is why their real cost per call can be well above what the input/output prices suggest. The reasoning-effort setting is therefore part of each candidate's configuration (e.g. `gpt-5.4-mini @ low` vs `@ medium`).

### Rough cost per question (estimates, to be replaced by measured `llm_usage` data)

Assumptions:
- **Guard:** ~600 input / ~20 output tokens (+ a few hundred reasoning tokens on reasoning models)
- **Planner:** ~15k input across ~4 tool turns / ~0.8k visible output, plus ~2k reasoning tokens on reasoning models
- **Narrator:** ~1.5k input / ~150 output with the summary; title only (since 2026-10-24) about half the output

| Planner candidate | Est. cost / question | Notes |
|---|---|---|
| gpt-5.4 | ~$0.08 | Strongest; expensive and likely slowest |
| **gpt-5.4-mini** | **~$0.024** | Starting default |
| gpt-5-mini | ~$0.009 | Older generation, cheaper |
| gpt-4.1-mini | ~$0.007 | Non-reasoning: fast; weaker multi-step reasoning |
| gpt-5.4-nano | ~$0.007 | Cheapest reasoning model; accuracy unknown for tool loops |
| gpt-4o-mini | ~$0.003 | Cheapest; likely weakest at enum mapping and tool use |

| Stage | Starting default | Est. cost / question |
|---|---|---|
| Guard | gpt-5.4-nano | ~$0.0005 |
| Planner | gpt-5.4-mini | ~$0.024 |
| Narrator | gpt-5.4-nano | ~$0.001 |
| **Total** | | **~$0.025** -> the default `LLM_DAILY_BUDGET_USD = 100` covers ~4,000 fresh questions/day (cache hits cost nothing) |

### Latency

**Not yet measured meaningfully.** The 2026-10-24 key check (one "Reply OK" call per model) took ~2-3 s for every model, which mostly reflects connection overhead, not task latency. Real p50/p95 latency per stage is measured in the bake-off below, with the actual prompts and tools.

~~**Title and summary share one model and one call.**~~ **Superseded 2026-10-24:** the narrator writes only the title ([Q4b revision](04b-ai-validation.md#revision-2026-10-24-the-ai-summary-is-removed)): free-text summaries were hallucination-prone, the assignment only requires a title, and dropping it saves output tokens and narrator time. The bake-off scores titles only (check pass rate, readability spot check).

## Starting defaults (until the bake-off runs)

| Stage | Model | Why this as a starting point |
|---|---|---|
| Guard | `gpt-5.4-nano` | Cheapest current-generation model; classification is a narrow task |
| Planner | `gpt-5.4-mini` | Current generation, reasoning, mid price; tool calling + enum mapping is the hardest task |
| Narrator (**title**; summary removed 2026-10-24) | `gpt-5.4-nano` | Placeholders + checks make the task simple; cost matters more than nuance |
| Fallback (all stages) | `gpt-4.1-mini` | Different family (non-reasoning GPT-4.1) from the GPT-5.4 primaries; cheap and fast |

## Model settings (fully configurable)

The defaults above are only defaults. **Every model choice is a setting.** Changing a model never requires a code change.

- Settings are a typed `Settings` class (Pydantic Settings), read from environment variables / `.env`.
- They're validated **at startup**, and a bad value fails fast with a clear message.
- **One settings group per AI stage** (`GUARD_*`, `PLANNER_*`, `NARRATOR_*`):

| Setting (per stage) | Example env var | Default (guard / planner / narrator) | Notes |
|---|---|---|---|
| Model | `PLANNER_MODEL` | `gpt-5.4-nano` / `gpt-5.4-mini` / `gpt-5.4-nano` | Any model enabled on the key |
| Fallback model | `PLANNER_FALLBACK_MODEL` | `gpt-4.1-mini` (all stages) | Used after the primary's retries fail (Q8). Can be empty to disable (except the guard, which fails closed anyway) |
| Reasoning effort | `PLANNER_REASONING_EFFORT` | `low` / `low` / `low` | Applied only to reasoning models; ignored (with a startup warning) for non-reasoning ones |
| Temperature | `NARRATOR_TEMPERATURE` | unset | Applied only to models that accept it |
| Max output tokens | `PLANNER_MAX_OUTPUT_TOKENS` | stage-specific | Caps cost and runaway output |
| Timeout per call | `GUARD_TIMEOUT_SECONDS` | e.g. 5 / 30 / 10 | Feeds the retry policy (Q8) |
| Max retries | `PLANNER_MAX_RETRIES` | e.g. 2 | Before switching to the fallback |
| Planner step limit | `PLANNER_MAX_STEPS` | 6 | Planner only (Q3) |

Startup checks:
- Every configured model must exist in `pricing.yaml`. A missing price is a **warning**: cost is recorded as `null`, never as $0 (Q16).
- The primary and fallback must differ.
- An optional `LLM_STARTUP_PING=true` makes one tiny call per configured model so a mistyped or retired model (e.g. `gpt-4.1-nano`) is caught at boot, not on the first user request.

Changing a model or prompt changes `planner_version`, so the plan cache (L2, Q8) naturally ignores plans made by the old configuration. The model actually used is recorded on every call in `llm_usage` and in `meta`.

**Not exposed per request:** clients can't choose the model. That would let the public endpoint bypass cost controls. The bake-off runs the same code with different settings.

## Selection process (the bake-off)

1. **Evaluation data** (from Q18):
   - **Planner:** the ~40-question AI eval set with expected plan properties (intent, chart type, dimension(s), filters, scope verdict)
   - **Guard:** a labelled set of legitimate questions (incl. tricky but harmless ones) and malicious ones (prompt injection, prompt extraction, abuse, misuse)
   - **Narrator:** fact sheets from real results
2. **Candidates per stage** (2-4 each, incl. reasoning-effort variants):
   - Guard: `gpt-5.4-nano`, `gpt-4o-mini`, `gpt-4.1-mini`
   - Planner: `gpt-5.4-mini` (low / medium effort), `gpt-5.4`, `gpt-5-mini`, `gpt-4.1-mini`
   - Narrator: `gpt-5.4-nano`, `gpt-4o-mini`, `gpt-4.1-mini`
3. **Runs:** each candidate runs the full set **3 times** (models are non-deterministic). Every call is recorded in `llm_usage`, so cost and latency come from real measurements, not estimates.
4. **Metrics:**

| Stage | Quality metrics | Speed / cost |
|---|---|---|
| Guard | Recall on malicious set; false-positive rate on legitimate set | p50/p95 latency; cost per call |
| Planner | % plans fully correct; per-property accuracy; % passing the code gate first time; average tool steps; `could_not_interpret` rate | p50/p95 latency; cost per question |
| Narrator | % passing all narration checks first time (V6-V8); fallback rate; a manual readability spot check of ~20 outputs | p50/p95 latency; cost per call |

5. **Quality bars** (a candidate must pass all of its stage's bars):

| Stage | Bar |
|---|---|
| Guard | **100% recall** on the malicious set; **≤ 5%** false positives; p95 ≤ 3 s (it runs in parallel with planning, so it shouldn't be the slowest branch) |
| Planner | **≥ 90%** of plans fully correct; ≥ 99% valid after the gate; p95 ≤ 15 s |
| Narrator | **≥ 95%** pass all checks on the first attempt; p95 ≤ 3 s |

6. **Decision rule:**
   - Among the candidates that pass every bar, pick the **lowest measured cost per request**.
   - If two are within ~20% on cost, pick the one with the **lower p95 latency**.
   - If **no** candidate passes, improve the prompt/tool design first, then re-run. Picking a bigger model is the last resort, and is recorded with the reason.
7. **Publish:** results table (per candidate: quality, p50/p95, cost) in `docs/eval/model-selection.md`, summarised in the README. Defaults in config are updated to the winners.

## When to re-run

- A prompt, tool, or registry change that affects a stage
- A new model becomes available, or a price changes (`pricing.yaml` version bump)
- The live E2E suite (Q18) shows a quality drop

## Honesty notes (for the README)

- The evaluation sets are **our own and small** (tens of cases), so results are indicative, not statistically strong. That limitation is stated alongside the numbers.
- Cost estimates in this file are **pre-measurement**. The README reports measured costs from `llm_usage`.

## Requirement links

P7-4..P7-6 (AI design: validation, sensible planning, appropriate tools), P7-1 (rational decisions), P8-1, P8-2 (tools used, how correctness was validated), Q16 (`llm_usage`, budget cap), Q18 (AI evaluation).
