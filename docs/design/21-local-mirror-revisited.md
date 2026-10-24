# Design Q21: A local mirror, revisited

Status: **Revisited and not built** (2026-10-25), at the time of writing. **Later the same day, the mirror was built under [Q22](22-term-sets.md)**, as the opt-in `fast` mode. This file records why we reopened it, what we designed, and the finding that stopped it then.

**Follow-up (2026-10-25), built:** [Q22](22-term-sets.md) gets around the synonym finding below with **term sets**: the API resolves each search term to a set of NCT IDs, so its synonyms and MeSH search stay exact, and the mirror supplies only the records. That removed the reason for not building it. Live fetching stays the default and the fallback; `fast` is on in the deployment as an opt-in.

## Why we reopened it

Q6 rejected a local mirror and named two triggers for revisiting it (see [06-retrieval.md](06-retrieval.md), "When to revisit"). Live testing hit the second one:

- "Rank years 2010-2020 on the number of sponsors sponsoring over 2 trials" covers **273,202 trials**. It needs every trial's record, so the live API took **~7 minutes** (274 pages at our 40 requests/min limit), as a background job.
- The bottleneck is the **number of requests** under the rate limit, not the payload. Asking for fewer fields doesn't help; the page size is already the maximum (1,000).

The idea: offer **two modes**:
1. **Live**, as today: always query the API, with the existing caches.
2. **Mirror**: pre-fetch the whole dataset into our database, apply the daily updates, and answer from SQL in under a second.

## The mirror we designed

**Same Postgres instance, separate schema** (`registry`).
- One server, one backup and one connection pool, and the mirror stays cleanly apart from the app's tables (`results`, `jobs`, caches).
- A separate database (or instance) only pays off if the mirror's load starts to hurt the app; it can move later without code changes, behind the data-source interface (D6.6).

**Tables:**

| Table | Contents |
|---|---|
| `registry.trials` | One row per study: `nct_id` (PK), the record as **JSONB** in the API's own shape (so `extract()` and the citation exactness check work unchanged), extracted, indexed columns (`start_date`, `start_date_type`, `overall_status`, `phases[]`, `study_type`, `lead_sponsor`, `lead_sponsor_class`, `enrollment`, ...), `last_update_post_date`, `synced_at` |
| `registry.trial_conditions`, `trial_drugs`, `trial_countries`, `trial_collaborators`, `trial_sites` | One row per value of a multi-valued dimension (raw value + normalised key, e.g. MeSH term or cleaned drug name), indexed, so most charts become one `GROUP BY` |
| `registry.sync_runs` | Each load or daily sync: started, finished, studies upserted and removed, the API's `dataTimestamp` |

**Loading and staying fresh:**
- **First load:** ~608k studies at 1,000 per request, ~608 requests, about **15-20 minutes** at the 40 requests/min limit of the time. (Built later under [Q22](22-term-sets.md#part-1-the-mirror), at half of today's 54-a-minute limit: the measured first load took **23.4 minutes**, and the mirror holds 1.16 GB.) Only the fields our registry uses, so the database stays a few GB.
- **Daily sync:** `filter.advanced=AREA[LastUpdatePostDate]RANGE[<last sync>,MAX]` fetches only changed studies (a few thousand a day) and upserts them. The API itself refreshes once a day, so a daily sync loses no freshness.
- **Removals:** a periodic ID-only pass (`fields=NCTId`) finds withdrawn records.

**Is it allowed?** ClinicalTrials.gov offers full downloads, and AACT (Duke / CTTI) publishes a daily Postgres mirror of the same data, which is strong precedent. We would still read the terms of use before shipping it, credit the source, and show the data date (which we already do).

## The finding that settled it: search is not just filtering

The live API does more than filter records: its search engine **resolves synonyms**. Our compiler relies on this on purpose. The planner is told never to add synonyms, because "ClinicalTrials.gov resolves synonyms itself" (Q3, Q7). Measured on 2026-10-24 (Q7):

| Term | What the API does | What a plain local match would miss |
|---|---|---|
| Condition "lung cancer" | Quoted `query.cond` searches conditions, titles, keywords and **MeSH terms with their ancestors and synonyms**: **13,423** trials | A match on the condition field alone (`AREA[Condition]`) finds **10,676**, missing **~2,750 trials (~20%)** |
| Drug "Keytruda" / "MK-3475" | `InterventionNameSearch` adds **UMLS synonyms**, so the brand name, code and generic name (pembrolizumab) return the same trials | A local name match would return almost nothing for "Keytruda", since most records list "pembrolizumab" |

To match the live answers, the mirror would need its own synonym and MeSH-hierarchy layer (e.g. NLM's MeSH entry terms and tree numbers, plus a drug synonym source). Then it would have to be **proven** equivalent to the API's search. That is a project of its own, and far beyond the time available.

Without it, the mirror would give **different, silently lower counts** for drug and condition questions. That breaks the product's core promise (D6.2, exact answers; Q14, every number traceable and correct). A faster wrong answer is worse than a slow right one, so: **not built.**

## The middle path we considered: route by question type

The slow questions are usually the **broad** ones, with no drug or condition terms: e.g. "trials per year", "sponsors with more than 2 trials per year", "phase by status". Their filters are structured fields (years, phases, statuses, countries, sponsor class), where a local SQL filter **is** exact.

So a hybrid could send:
- questions with only structured filters to the **mirror** (exact and fast);
- questions with drug, condition or sponsor-name terms to the **live API** (exact via its synonyms, and usually small enough to be quick).

**Why not now:** it still needs the full ingestion pipeline, the daily sync, a second retrieval path, and a **cross-check suite** proving that mirror and API counts agree exactly on structured-only questions. That suite is non-negotiable, and it wouldn't fit before the deadline. Sponsor names add a wrinkle: the API's `query.lead` is a contains-match, so local matching would have to copy that rule exactly.

## What we did instead

- **Per-year counts without downloading** (S2 for time dimensions): a trials-per-year series makes one count call per year. 2010-2020 went from **412 s to 57 s**, with identical numbers.
- **Background jobs** for large questions, with heartbeats, and requeueing when a worker stops (a restart no longer strands a job).
- **Result reuse with revalidation** (Q8): a repeated question is answered from the stored result after two cheap count calls.
- **Charts built off the event loop**, so one large question doesn't stall other requests.

## If we build it later

1. Read and record the terms of use.
2. Build the ingestion (first load + daily sync + removals) behind the data-source interface (D6.6).
3. Add a `data_source` setting: `live` | `mirror` | `auto`. `auto` routes structured-only questions to the mirror.
4. Gate it with a cross-check suite: for a fixed set of structured-only questions, mirror and live counts must match **exactly**, run after each sync.
5. Only after a validated synonym/MeSH layer, consider sending drug and condition questions to the mirror. Until then they stay live.

## Requirement links

- Accuracy over speed: exact answers (D6.2), traceable citations (Q14).
- Performance: background jobs and per-year counts cover the slow cases for now (Q6, Q8).
- Future work, listed in the README.
