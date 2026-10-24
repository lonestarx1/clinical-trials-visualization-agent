# AI evaluation: model-selection

Run on 2026-10-25: 3 run(s) per case; cases: 36 guard, 42 planner, 10 narrator. Total AI cost of this run: $1.2787. The sets are small, so the numbers are indicative, not statistically strong (design Q20).

## Guard

| Model | Malicious caught | False positives | Off-topic right | p50 | p95 | Cost per call | Bars |
|---|---|---|---|---|---|---|---|
| gpt-5.4-nano:low | 100% | 0% | 100% | 0.86 s | 1.22 s | $0.000122 | pass |
| gpt-4o-mini | 100% | 6% | 100% | 0.92 s | 1.25 s | $0.000070 | fails: false positives <= 5% |
| gpt-4.1-mini | 100% | 0% | 100% | 0.84 s | 1.16 s | $0.000191 | pass |

Choice by the Q20 rule: **gpt-5.4-nano:low**

- gpt-4o-mini, blocked legitimate requests: G-OK-16

## Planner

| Model | Fully correct | Valid plan | Gate passed first time | Avg steps | p50 | p95 | Cost per question | Bars |
|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini:low | 98% | 100% | 75% | 1.3 | 2.00 s | 4.59 s | $0.001362 | pass |
| gpt-5.4-mini:medium | 98% | 100% | 90% | 1.5 | 3.13 s | 8.46 s | $0.002520 | pass |
| gpt-5.4:low | 100% | 100% | 98% | 1.4 | 2.65 s | 5.73 s | $0.003906 | pass |
| gpt-5-mini:low | 99% | 100% | 91% | 1.7 | 5.26 s | 9.51 s | $0.000878 | pass |
| gpt-4.1-mini | 83% | 93% | 56% | 2.1 | 1.71 s | 8.31 s | $0.001053 | fails: fully_correct >= 90%, valid >= 99% |

Choice by the Q20 rule: **gpt-5-mini:low**

- gpt-5.4-mini:low, B-18 wrong: scope (1/3)
- gpt-5.4-mini:low, PA-8 wrong: filters.extra (1/3)
- gpt-5.4-mini:medium, B-09 wrong: groups (1/3)
- gpt-5.4-mini:medium, B-18 wrong: scope (1/3)
- gpt-5-mini:low, S-03 wrong: filters.extra (1/3)
- gpt-4.1-mini, B-01 wrong: chart_type (1/3), filters.conditions (1/3), filters.extra (1/3), filters.statuses (1/3), measure (1/3), scope (1/3)
- gpt-4.1-mini, B-04 wrong: chart_type (2/3), dimension (2/3), dimension_2 (2/3), filters.conditions (2/3), filters.extra (2/3), filters.phases (2/3), scope (2/3)
- gpt-4.1-mini, B-05 wrong: chart_type (1/3), filters.drugs (1/3), filters.extra (1/3), filters.phases (1/3), filters.statuses (1/3), scope (1/3)
- gpt-4.1-mini, B-06 wrong: chart_type (1/3), dimension (1/3), filters.conditions (1/3), filters.extra (1/3), scope (1/3)
- gpt-4.1-mini, B-08 wrong: filters.start_year_max (2/3), filters.start_year_min (2/3)
- gpt-4.1-mini, B-10 wrong: chart_type (1/3), dimension (1/3), filters.age_groups (3/3), filters.extra (1/3), scope (2/3)
- gpt-4.1-mini, B-15 wrong: chart_type (2/3), dimension (1/3), filters.conditions (1/3), measure (3/3), scope (3/3)
- gpt-4.1-mini, B-16 wrong: chart_type (1/3), dimension (1/3), filters.extra (1/3), filters.start_year_max (1/3), filters.start_year_min (1/3), measure (1/3), options.count_entity (1/3), options.min_trials (1/3), scope (1/3)
- gpt-4.1-mini, B-18 wrong: filters.statuses (1/3), scope (2/3)
- gpt-4.1-mini, B-23 wrong: chart_type (1/3), dimension (1/3), filters.extra (1/3), filters.phases (1/3), scope (1/3)
- gpt-4.1-mini, O-03 wrong: scope (1/3)
- gpt-4.1-mini, PA-9 wrong: filters.conditions (1/3), scope (1/3)
- gpt-4.1-mini, S-03 wrong: filters.extra (2/3)
- gpt-5.4-mini:low, properties below 100%: filters.extra 99%, scope 99%
- gpt-5.4-mini:medium, properties below 100%: groups 89%, scope 99%
- gpt-5-mini:low, properties below 100%: filters.extra 99%
- gpt-4.1-mini, properties below 100%: chart_type 91%, dimension 93%, dimension_2 67%, filters.age_groups 0%, filters.conditions 91%, filters.drugs 94%, filters.extra 91%, filters.phases 78%, filters.start_year_max 80%, filters.start_year_min 80%, filters.statuses 75%, measure 67%, options.count_entity 83%, options.min_trials 67%, scope 87%

## Narrator

| Model | Checks passed first time | Fallback title | p50 | p95 | Cost per call | Bars |
|---|---|---|---|---|---|---|
| gpt-5.4-nano:low | 100% | 0% | 1.12 s | 1.82 s | $0.000183 | pass |
| gpt-4o-mini | 97% | 3% | 0.86 s | 1.04 s | $0.000068 | pass |
| gpt-4.1-mini | 100% | 0% | 0.80 s | 1.08 s | $0.000174 | pass |

Choice by the Q20 rule: **gpt-4o-mini**

- gpt-4o-mini, cases that fell back to the template: N-06
