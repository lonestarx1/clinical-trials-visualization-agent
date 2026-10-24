# Design Q22: The API picks the trials, our database counts them

Status: **Proposed** (2026-10-25). Not built. A **second mode, `fast`**, next to today's live fetching, which stays the default and is unchanged. It builds on the mirror designed in [Q21](21-local-mirror-revisited.md) and removes the reason Q21 gave for not building it.

## The problem

ClinicalTrials.gov returns at most **1,000 trials per request** and answers about **10 requests per 10 s** per IP ([live probe §8](../api/live-probe.md)). So any design that moves trial records over the API while someone waits is bound by the number of trials:

| Question | Trials | Today |
|---|---|---|
| "Breast cancer" by phase | 16,765 | 17 pages, ~27 s |
| Sponsors with over 2 trials per year, 2010-2020 | 273,202 | ~7 min, as a background job |
| Unscoped, needs every record | 608,415 | ~11 min at best |

Asking for less doesn't help. Measured on 2026-10-25: `pageSize` is capped at 1,000 even with `fields=NCTId` (we asked for 5,000 and got 1,000). An IDs-only page is small (~5 KB, 0.8 s), but it is still one request per 1,000 trials. **The only way to be much faster is to stop moving records at question time.**

## Why Q21 stopped, and the idea

Q21 designed a local mirror, then didn't build it. The API's search resolves synonyms and MeSH ancestors: "lung cancer" finds ~20% more trials than a plain match on the condition field, and "Keytruda" finds the pembrolizumab trials. A mirror with plain local matching would give lower counts, silently.

The idea is to **split each question in two**:

- **Which trials match a search term** is the search engine's job. Ask the API, and remember its answer as a set of NCT IDs: a **term set**.
- **What the matching trials contain** (phases, sponsors, dates, enrollment, ...) is data. Read it from the local mirror.

The mirror never interprets a search term, so it can't get synonyms wrong: membership always comes from the API.

## Two modes

| | `live` (default) | `fast` |
|---|---|---|
| What it does | Today's pipeline, unchanged: download the matching trials (S3) or count per year (S2), at question time | Term sets from the API, records from the mirror, checked against a live count (Parts 1-3) |
| Speed | Bound by the number of trials: seconds to minutes; broad questions become background jobs | About a second for most questions |
| Where the records come from | ClinicalTrials.gov, at request time | Our copy of ClinicalTrials.gov at the same data timestamp |
| When it can't answer | n/a | It falls back to `live` and says so |

**Live fetching stays.** It is the default, it is the reference that `fast` is checked against, and it is the fallback whenever a `fast` check fails or the mirror isn't ready. Nothing in this design removes or changes it.

**Choosing a mode:**

- **API:** `POST /v1/query` gains `mode`: `"live"` (default) or `"fast"`, a top-level field like `citations`. The `fast` request needs the server setting `FAST_MODE_ENABLED`; without it, `fast` is answered by `live` with a note.
- **Response:** `meta.data_source` says which mode actually answered (`live` or `fast`), and `meta.notes` gives the reason for a fallback (for example "the mirror is syncing today's update").
- **Web app:** a "Fast results" switch by the question box, kept in the shareable `?q=` link. Each answer shows its source: "Live from ClinicalTrials.gov", or "Fast: from our copy of the 2026-10-23 data, checked against ClinicalTrials.gov".

A stored answer can be reused by either mode: when the checks pass, both modes give the same numbers.

## Part 1: the mirror

As designed in Q21: a `registry` schema in the app's Postgres, one row per trial with the record as the API returns it (JSONB, only the fields the registry uses), plus extracted, indexed columns.

- **First load:** 608,415 trials (2026-10-25), 609 pages, about 11 minutes at the limit. Page tokens make one search's pages strictly sequential, so the load runs as several searches sliced by `StartDate` range (plus trials with no start date), each paging on its own, so together they keep the limiter busy.
- **Daily update:** only the trials that changed, after each new `dataTimestamp` (below).
- **Removals:** compare the API's total count with the mirror's (one call). When they differ, find the removed trials by **bisection with count calls** (per start year, then per month) and list IDs only in the ranges that differ, instead of a 609-page ID pass.
- **Weekly full re-sync**, at night (~11 minutes at the full rate): a safety net for changes that don't bump `LastUpdatePostDate` (open item O5). Its diff against the daily updates measures how often that happens.

### The daily update

ClinicalTrials.gov publishes one update per weekday, and `/version` gives its `dataTimestamp` (`2026-10-23T09:00:04` for the data measured here). Measured: 5,022 trials changed between 2026-10-18 and that update, about 1,000 per update, so one or two pages.

| Step | What happens |
|---|---|
| **Detect** | A sync loop in the API process asks `/version` every 10 minutes (the client caches it that long anyway). A `dataTimestamp` newer than the mirror's starts a sync |
| **Lock** | The sync takes a Postgres advisory lock, so only one runs at a time, even while a rolling update briefly runs two pods |
| **Fetch** | `AREA[LastUpdatePostDate]RANGE[<date of the last successful sync - 1 day>,MAX]`, with the registry's fields: ~1,000 trials, one or two pages |
| **Save** | Upsert the trials into `registry.trials`, in one transaction |
| **Removals** | In the same transaction: if the mirror now has more trials than the API's total, find the removed ones by bisection (above) and delete them |
| **Check** | The mirror's count must equal the API's total. Only then write the `sync_runs` row with the new `dataTimestamp`, and commit. That row is what marks the mirror as current |
| **Fail** | Roll back, keep the previous `dataTimestamp`, record the failed run, and retry after 1, 5, 15, 30 and then every 60 minutes. Log an error when an update is still not synced 3 hours after it appeared |

**Why in the API process, not a cron pod:** the sync must share the one rate limiter. A separate pod would have its own limiter on the same IP, and together they could go over ~10 requests per 10 s, so questions would get `429`s. Inside the process, the sync's client gets its own **lower cap (half the budget, 27 requests a minute) under the shared limiter**, so a long load can't starve questions.

**While a sync runs:** `fast` answers only when the mirror's synced `dataTimestamp` equals the API's current one. From the moment new data appears until the sync commits (a few minutes per weekday), `fast` requests fall back to `live` with a note. No answer mixes the old data with the new.

**Missed updates:** the fetch always starts from the last *successful* sync, with a day of overlap, so a missed day (a restart, an outage) is covered by the next run, and a rerun saves the same trials again harmlessly. If the last successful sync is more than 7 days old, a full load runs instead.

**First load:** the same steps without the `LastUpdatePostDate` filter, in `StartDate` slices, committing page by page. The mirror is not marked current until every slice is done and the total matches. If a new update appears during the load, a daily update runs right after it, from the load's start date.

**Nightly and weekly work**, at a quiet hour (03:00 UTC) through the same loop and limiter: pre-warming term sets every night (Part 2), and the full re-sync on Sundays, when there is no update. The re-sync writes every difference it finds to `registry.drift`: those are trials that changed without a new `LastUpdatePostDate` (O5).

## Part 2: term sets

A term set is the NCT IDs that one search term matches, at one data timestamp.

**What counts as a term:** every piece of a search that the search engine interprets. In our compiler ([Q7](07-query-compilation.md)) that is:

| Piece | Example | Why it's a term |
|---|---|---|
| `query.cond` | `"lung cancer"` | Synonyms, MeSH ancestors, several fields |
| `query.intr`, `AREA[InterventionNameSearch]` | `"Keytruda"` | UMLS drug synonyms |
| `query.lead`, `query.spons` | `"Pfizer"` | Contains-match on sponsor names |
| `AREA[LocationCountry]`, `AREA[LocationState]` | `"Japan"` | Phrase match. It may well equal a plain match on the country (a check of "Guinea" found only trials in Guinea), but it stays a term until the cross-check suite proves that |

Everything else is **structured**: enum codes (`AREA[Phase]PHASE2`, `filter.overallStatus`, study type, sponsor class, ...), booleans and the `StartDate` range. The mirror evaluates these itself.

**Key:** the parameter plus the term's Essie text, such as `query.cond|"lung cancer"`. There is one set per filter value (one phrase), so sets are reused across questions: values of one filter are a union (OR), and filters are an intersection (AND), as in D7.2.

**Lifecycle:**

- **Resolve**, on first use: page through the term with `fields=NCTId`. One request per 1,000 trials, but small and quick ones.
- **Refresh**, when the set is older than the last sync: one call, `<term> AND AREA[LastUpdatePostDate]RANGE[<set's last refresh - 1 day>,MAX]`, with `fields=NCTId`. It returns which of the changed trials match now. The new set is the old set, minus every changed trial, plus that answer. Measured: "breast cancer" (16,765 trials) had 186 changes in a week, which is one page.
- **Re-resolve** in full on a schedule (weekly, for sets in use) and whenever a check fails (see Part 3). The API's synonym and MeSH tables can change without any trial changing; NLM publishes MeSH once a year.
- **Pre-warm** the terms people ask about most at night: the example questions, and the most frequent MeSH conditions and drugs in the mirror. Most questions then find their sets ready.

Refreshing only when a term is used means unused terms cost nothing.

## Part 3: answering a question in `fast` mode

1. Plan the question, as today.
2. For each search, refresh its term sets if they are stale. This runs in parallel with the count call that `prepare()` already makes (cached, Q8 D8.3a).
3. Run SQL: trials in the mirror that are in the term sets (union within a filter, intersection across filters) and pass the structured filters. Then run the same extraction and aggregation code as today, on the mirror's records.
4. **Check:** the SQL's number of trials must equal the live count for the same search. If they are equal, answer from the mirror. If not, re-resolve the term sets involved and check again when they are small. Otherwise fall back to `live` mode and record the drift.

The compiler already builds an expression tree ([Q7](07-query-compilation.md), D7.1) and turns it into Essie with `to_essie`. The mirror needs a second serialiser over the same tree, `to_sql`, that maps term nodes to term-set joins and structured nodes to column predicates. With one tree and two outputs, the API search and the SQL can't drift apart on what a filter means.

## Why the answers stay exact

A live answer aggregates the records the API returns for a search. A mirror answer aggregates the mirror's records whose IDs pass the same search. The two are equal when (a) the mirror's records equal the API's at the current data timestamp, and (b) the IDs are the same.

| Risk | Guard |
|---|---|
| A record changed without its `LastUpdatePostDate` changing (O5) | The weekly full re-sync. Its diff against the daily syncs measures how often this happens |
| The mirror is behind (the sync hasn't finished after a new `dataTimestamp`) | The mirror answers only when its synced timestamp equals the API's current one; otherwise the live path |
| A term set is out of date (a record change, a synonym update) | Refresh before use, the weekly re-resolve, and the per-answer count check |
| A structured filter means something different in SQL (for example partial dates such as `2015-03` inside a `StartDate` range) | The cross-check suite before launch, and the per-answer count check |
| Equal totals hide different trials (one in, one out) | **Shadow runs:** a sample of mirror answers (for example 5%) is also computed live in the background and compared value by value and citation by citation. Any difference is logged and alerts |

When a check fails, the question falls back to `live` mode: **as slow as today, never different.** The mirror is an accelerator, not a second source of truth.

**Citations:** mirror records are the API's JSON at the same data timestamp, so citations and their exactness check (Q14) work unchanged. `meta` keeps the live search URLs in both modes, so anyone can still check a number against ClinicalTrials.gov.

## Expected latency

| Question | `live` (today) | `fast` |
|---|---|---|
| Structured filters only: sponsors with over 2 trials per year, 2010-2020 (273,202 trials) | ~7 min, background job | Under 1 s: one count call and SQL |
| Trials per year, 2010-2020 | Count calls per year (S2), tens of seconds | Under 1 s |
| A term with a ready set: "breast cancer" by phase (16,765 trials) | ~27 s (17 pages) | About 1 s: one refresh call and one count call in parallel, then SQL |
| A new term | One request per 1,000 trials | The same number of requests, but small ones. Pre-warming should make this rare |

The SQL times are estimates, to be measured. With indexes on the extracted columns and on term-set members, aggregating a few hundred thousand rows in Postgres should take well under a second.

**A new term, sooner:** resolve only the term AND this question's structured filters first (often a few pages), answer, and complete the full term set in the background.

## Cost

- **Storage:** the registry fields of ~608k trials take a few GB (Q21). Term sets store NCT IDs as integers, 4 bytes each: 1,000 sets of ~5,000 trials is ~20 MB.
- **API budget:** per day, one or two sync pages, one total-count call, and one refresh call per term in use. Per week, ~609 pages for the re-sync, at night. That is far below the limit and leaves the daytime budget to questions.
- **Code:** the ingestion (first load, daily sync, removals), term sets, `to_sql`, the `mode` request field and its switch in the web app, the cross-check suite and shadow runs. The `live` pipeline is untouched.

## Tables (added to Q21's `registry` schema)

| Table | Contents |
|---|---|
| `registry.trials` | As in Q21 |
| `registry.term_sets` | `term_key` (PK), `param`, `expression`, `size`, `resolved_at`, `refreshed_through` (the last `LastUpdatePostDate` covered), `data_ts` |
| `registry.term_members` | `term_key`, `nct_num` (the NCT ID as an integer); primary key on both, index on `nct_num` |
| `registry.sync_runs` | As in Q21 |
| `registry.drift` | Each failed check or shadow-run difference: the search, the live and mirror values, and what was refreshed |

## Terms of use (checked 2026-10-25)

ClinicalTrials.gov's [Terms and Conditions](https://clinicaltrials.gov/about-site/terms-conditions) apply to "all data obtained from ClinicalTrials.gov, independent of format and method of acquisition", and the data "are available to all requesters, both within and outside the United States, at no charge". Nothing in them forbids keeping a copy. They stay in effect "as long as the user retains any of the data". (The page renders in the browser; the text was read from the site's own script bundle on 2026-10-25.)

| The terms say | How `fast` mode meets it |
|---|---|
| "Attribute the source of the data as ClinicalTrials.gov" | Every answer already names ClinicalTrials.gov and links the live search; `fast` answers say "from our copy of ClinicalTrials.gov" |
| "Update the data such that they are current at all times" | The daily update (Part 1), and `fast` answers only when the mirror matches the API's current `dataTimestamp`; otherwise `live` |
| "Clearly display the date the data were processed by ClinicalTrials.gov" | `meta.data_timestamp`, already shown in the web app |
| "State any modifications made to the content of the data" | Records are stored as the API returns them, limited to the fields the registry uses (34, listed in code); no values are changed. Grouping rules are stated per answer, as today (Q9, Q11) |
| Don't "assert any proprietary rights" or present it as other than a U.S. Government database | The API guide and README say the data belong to ClinicalTrials.gov (NLM) |
| Don't use email addresses from the database for marketing | The mirror stores no email fields |
| Some data "may be subject to the copyright of third parties" | We store only the fields charts and citations need (titles, names, codes, dates), no long free text such as descriptions or eligibility criteria |

## Rollout

1. **Terms of use:** done, see above.
2. **Mirror ingestion:** the sync loop, first load, daily update, removals by bisection, then the weekly re-sync. Off by default (`MIRROR_SYNC_ENABLED`). Measure O5.
3. **`to_sql` and the cross-check suite:** for every registry enum value and every year, the mirror count equals the live count; for a sample of terms, the term set equals the live ID list.
4. **Term sets:** resolve, refresh, re-resolve, pre-warm.
5. **Shadow first:** with `FAST_MODE_SHADOW` on, every question is answered `live`, and the `fast` answer is computed too and compared. Keep it on until the drift log stays empty for a week of daily updates.
6. **Offer `fast`:** turn on `FAST_MODE_ENABLED`, so requests can ask for `mode: "fast"` and the web app shows the switch. Keep shadow-running a sample of `fast` answers. `live` stays the default.

## What it doesn't fix

- A new term with a very large set (such as "cancer") still costs one request per 1,000 trials the first time. Pre-warming covers the common ones.
- The daily sync and the questions share one IP's budget, so one API replica stays the plan (D8.5).
- If the API changes how its search behaves, the checks catch it; they can't prevent it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **AACT** (Duke / CTTI's daily Postgres copy) | No rate limit, but a different schema from the API's JSON (citations would need a new mapping) and the same synonym problem. Possible later as a source for the first load |
| **Our own synonym layer** (MeSH entry terms, drug synonyms; Q21's option) | It would have to be proven equal to the API's search, a project of its own. Term sets get the API's exact behaviour for free |
| **Count calls only** (S2 for every chart) | Fast for a few buckets, but there are no records, so no median enrollment, distinct entities, networks or full citations |
| **Several outgoing IPs** to raise the limit | Rejected: it works around the API's limit instead of respecting it |

## Requirement links

- Exact answers (D6.2) and traceable citations (Q14): kept, through the per-answer count check, the live fallback and shadow runs.
- Performance (Q6): broad questions no longer need background jobs.
- Live data (D6.1): `live` stays the default and the reference; `fast` is an opt-in second mode.
- Revisits Q21 (the mirror) and Q6 (live data only).
