# AI evaluation: after-prompt-fixes

Run on 2026-10-25: 3 run(s) per case; cases: 36 guard, 42 planner, 10 narrator. Total AI cost of this run: $0.1791. The sets are small, so the numbers are indicative, not statistically strong (design Q20).

## Guard

| Model | Malicious caught | False positives | Off-topic right | p50 | p95 | Cost per call | Bars |
|---|---|---|---|---|---|---|---|
| gpt-5.4-nano:low | 100% | 0% | 100% | 0.83 s | 1.09 s | $0.000123 | pass |

Choice by the Q20 rule: **gpt-5.4-nano:low**


## Planner

| Model | Fully correct | Valid plan | Gate passed first time | Avg steps | p50 | p95 | Cost per question | Bars |
|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini:low | 98% | 100% | 81% | 1.2 | 1.59 s | 3.48 s | $0.001271 | pass |

Choice by the Q20 rule: **gpt-5.4-mini:low**

- gpt-5.4-mini:low, B-09 wrong: groups (1/3)
- gpt-5.4-mini:low, B-14 wrong: filters.conditions (1/3)
- gpt-5.4-mini:low, PA-4 wrong: filters.conditions (1/3)
- gpt-5.4-mini:low, properties below 100%: filters.conditions 97%, groups 89%

## Narrator

| Model | Checks passed first time | Fallback title | p50 | p95 | Cost per call | Bars |
|---|---|---|---|---|---|---|
| gpt-5.4-nano:low | 100% | 0% | 1.18 s | 1.73 s | $0.000190 | pass |

Choice by the Q20 rule: **gpt-5.4-nano:low**
