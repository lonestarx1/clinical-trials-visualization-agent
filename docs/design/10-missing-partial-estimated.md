# Design Q10: Missing, partial and estimated values

Status: **Decided** (2026-10-24)

Principle: **nothing is silently dropped.** Every excluded trial is counted and explained in `meta.excluded`, as a list of `{reason, count}`.

## Missing values

| # | Case | Behaviour |
|---|---|---|
| D10.1 | Categorical dimension missing (e.g. no lead sponsor class, no phase on an interventional trial, no country because no sites) | A **"Not reported"** bucket, sorted **last**. Option `include_unknown: false` hides it, but the count still appears in `meta.excluded`. (Observational trials without phases go into the explicit "No phase (observational / expanded access)" bucket from Q9, not "Not reported".) |
| D10.2 | Time dimension missing (no start date: 5 of 2,993 pembrolizumab trials) | Can't be placed on the axis. Excluded and counted: `{reason: "no start date", count: 5}`. |
| D10.3 | API RANGE filters (`AREA[StartDate]RANGE[...]`) | The API excludes trials with no value. `meta` notes it (e.g. "Year filter excludes trials without a start date"). |

## Partial dates

| # | Case | Behaviour |
|---|---|---|
| D10.4 | `yyyy-MM` or `yyyy` with **yearly** buckets | Bucketed by year. No loss. |
| D10.5 | Month granularity requested | `yyyy`-only dates can't be placed. Excluded and counted. |

## Estimated / future dates

| # | Case | Behaviour |
|---|---|---|
| D10.6 | Default time range | Ends at the **current year**. Future (planned) starts are excluded and counted (`{reason: "planned start after 2026", count: 46}`). |
| D10.7 | Questions about planned / upcoming trials ("planned", "upcoming", "not yet recruiting") | The range extends into the future. Recorded in `assumptions`. |
| D10.8 | Estimated dates inside the range | Included, and **flagged**. Each time bucket carries `estimated_count`, and `meta` warns when a bucket is mostly estimated (e.g. the current year). Start-date type missing (60 of 2,993 trials) is treated as "unknown type" and not counted as estimated. |

## Empty buckets

| # | Behaviour |
|---|---|
| D10.9 | Time series are **zero-filled** across the full range, so gaps show as 0 instead of the line jumping over them. Categorical charts don't zero-fill open-ended dimensions, but enum dimensions (phase, status) show all values with 0 when `show_empty: true`. |

## Numeric values

| # | Case | Behaviour |
|---|---|---|
| D10.10 | Enrollment missing | Excluded from histograms, scatter plots and enrollment measures; counted. ESTIMATED vs ACTUAL enrollment is reported per bucket (and per point in scatter plots). |
| D10.11 | Outliers (e.g. enrollment 500,000) | **Kept** (they're real data). Histograms use an **overflow bin** ("≥ X", with X at a high percentile, e.g. P99) so one trial can't flatten the chart. The bin edges and the overflow rule are in `meta`. Optional log scale is a render hint. |
| D10.12 | Duration (completion date − start date) | Needs both dates. Partial dates use the first day of the month/year, with the approximation noted. **Impossible values** (end before start) are excluded and counted as data errors. Estimated completion dates are flagged like estimated starts. |

## As built (2026-10-25)

Checked against [`extract.py`](../../backend/app/pipeline/extract.py), [`aggregate.py`](../../backend/app/pipeline/aggregate.py) and [`charts.py`](../../backend/app/pipeline/charts.py). D10.1-D10.4 and D10.7 are as designed; partial dates take their first 4 characters as the year. Differences:
- **D10.5:** there is no month granularity (time dimensions are yearly), so the case never arises.
- **D10.6:** the exclusion reason reads "start after 2026".
- **D10.8:** as designed: `estimated_count` per time bucket, and a warning when most of a bucket's trials have estimated dates.
- **D10.9:** time series are zero-filled. `show_empty` is **not built**: the plan accepts it, but no code reads it, so enum charts show only the values that occur.
- **D10.10:** enrollment ESTIMATED vs ACTUAL is **not** reported per bucket. Scatter points carry `estimated: true` when either value is an estimate.
- **D10.11:** the overflow bin starts at the nearest-rank P99, and `meta.notes` gives the bin width and the cut. There is no log-scale hint.
- **D10.12:** histograms exclude negative durations and count them as "completion before start (data error)". Scatter plots drop them under the general "no ... reported" reason. Estimated completion dates are flagged only on scatter points.

## Requirement links

P3-10, P3-11 (render metadata, assumptions), P7-3 (sensible handling of real-world API data), P7-8 (robustness), P7-13 (frontend-friendly).
