# AI evaluation

How well each AI stage does its job, measured on fixed case sets with the real models ([design Q18](../design/18-testing.md), [Q20](../design/20-model-selection.md)). The code is in [`backend/evals/`](../../backend/evals/).

## The case sets

| Set | Cases | What a case is |
|---|---|---|
| [Planner](../../backend/evals/cases/planner.yaml) | 42 | A question, and the properties a correct plan has: scope, chart type, dimension(s), measure, filters, groups, options. 9 are the assignment's appendix questions; the rest cover every chart type and measure, 5 questions we must refuse, structured request fields, and an injection the planner must ignore. |
| [Guard](../../backend/evals/cases/guard.yaml) | 36 | A request labelled `ok` (18, including alarming medical words and a benign "ignore"), `off_topic` (5) or `malicious` (13: injection, prompt or key extraction, abuse, misuse). |
| [Narrator](../../backend/evals/cases/narrator.yaml) | 10 | A plan run once on live ClinicalTrials.gov data, so the narrator writes a title from a real fact sheet. |

An offline test keeps every case valid against the schemas and the registry, and checks that the narrator plans pass the gate (`tests/unit/test_eval_cases.py`).

## How it's scored

- **Planner:** each expected property passes or fails. Term filters match case-insensitively and either may contain the other ("alzheimer" matches "Alzheimer's Disease"). `filters` also fails when the plan adds a filter nobody asked for. Where more than one reading is right, the case lists each one (`any_of`).
  - **Fully correct:** every property right.
  - **Valid:** the planner submitted a plan the gate accepted.
  - **First time:** its first `submit_plan` passed the gate.
- **Guard:** recall on the malicious set, the false-positive rate on legitimate requests, and accuracy on off-topic ones.
- **Narrator:** the share of titles that pass every check (V6-V8) on the first attempt, and how often it falls back to the template title.
- **Every stage:** p50 and p95 time per question, and the measured cost from the token counts.

Each stage runs on its own, with its fallback model turned off, so every score belongs to one model. The planner gets live ClinicalTrials.gov counts for its `count_trials` tool.

**Quality bars** (Q20). A model must pass all of its stage's bars:

| Stage | Bars |
|---|---|
| Guard | 100% of attacks caught; at most 5% false positives; p95 at most 3 s |
| Planner | at least 90% fully correct; at least 99% valid; p95 at most 15 s |
| Narrator | at least 95% pass on the first attempt; p95 at most 3 s |

The **bake-off** runs Q20's candidate models per stage and picks the cheapest one that passes every bar, or the faster one when two are within about 20% on cost.

## Running it

It calls the real OpenAI API, so it costs money (about $0.50 for the baseline below) and isn't part of `make test`.

```bash
make eval ARGS="--runs 3 --label baseline"                    # the configured models
make eval ARGS="--stages planner --model planner=gpt-5.4:low"  # one stage, another model
make bakeoff                                                   # every Q20 candidate, 3 runs per case
```

Each run writes `docs/eval/<label>.md` and the raw runs to `docs/eval/results/<label>.json`.

## Results

- [Baseline](baseline.md): the deployed models and code (`6955b33`), 3 runs per case. It found:
  - a **gate bug**: "the number of sites" in a scatter question was read as counting distinct sites, so a correct plan was rejected and the planner refused the question (B-04). Fixed, with a regression test;
  - the planner never sets `top_n` ("the 5 most common", B-25), and only about 1 in 5 of its first submissions passes the gate, so most questions take an extra step;
  - the guard lets an "essay" request through as off-topic (G-MAL-07), so it misses the 100% bar.
- [After the prompt fixes](after-prompt-fixes.md): the planner prompt lists the exact chart types and option names and says never to drop a named term; the guard prompt calls writing requests misuse, keeps advice questions off-topic and treats "ignore trials without ..." as a filter. **Every stage passes every bar.**

| | Baseline | After the fixes |
|---|---|---|
| Planner: fully correct | 94% | 98% |
| Planner: first submission passes the gate | 21% | 81% |
| Planner: steps per question | 2.1 | 1.2 |
| Planner: p50 / p95 | 3.4 s / 6.2 s | 1.6 s / 3.5 s |
| Planner: cost per question | $0.0021 | $0.0013 |
| Guard: attacks caught / false positives / off-topic right | 92% / 2% / 100% | 100% / 0% / 100% |
| Narrator: titles passing first time | 97% | 100% |

The fixes took two rounds. The first round raised the gate pass rate, but the guard then blocked advice questions such as "How do I bake sourdough bread?", and the planner once dropped "melanoma". The eval caught both, and the second round fixed them. One miss remains: the planner still drops the condition in about 1 run in 3 on two questions (PA-4, B-14).

- [Model selection](model-selection.md): the bake-off, every Q20 candidate per stage, 3 runs per case ($1.28). Chosen: guard `gpt-5.4-nano`, narrator `gpt-4o-mini`, and the planner stays on `gpt-5.4-mini` as a recorded exception: the rule's choice, `gpt-5-mini`, is cheaper by $0.0005 per question but more than twice as slow. The planner's fallback, `gpt-4.1-mini`, failed the planner bars (83% correct), so it is now `gpt-5-mini`. Details in [design Q20](../design/20-model-selection.md#bake-off-results-2026-10-25).

The sets are our own and small (tens of cases), so the numbers are indicative, not statistically strong.
