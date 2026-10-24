# Part 2: Data source

## 1. Summary

The [ClinicalTrials.gov Data API](https://clinicaltrials.gov/data-api/api) is the authoritative source of data. Any of its endpoints and fields may be used.

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| P2-1 | MUST | Use the **ClinicalTrials.gov Data API** (not a scraped website, a third-party dump, or LLM knowledge). |
| P2-2 | MUST | It is the **authoritative** source: every fact shown (counts, phases, dates, sponsors, countries) comes from API data. |
| P2-3 | MAY | Any endpoint and any field may be used. |

## 3. What it means

- "Authoritative" rules out an LLM filling in or "correcting" data. If the API says a trial has no start date, we report it as missing. We don't guess.
- The API's quirks are part of the test. Part 7 assesses sensible handling of real-world API data, so we must deal with:
  - pagination
  - multi-valued fields
  - partial dates
  - inconsistent names
  - large result sets
  - rate limits
- API behaviour has to be **verified against the live API**, not assumed, before designing around it.

## 4. Things to verify against the live API

Each item below was an open question before the design. All but the rate limit were checked against the official docs and the live API; the findings are in [`../api/contract.md`](../api/contract.md) (endpoints, fields, enums) and [`../api/live-probe.md`](../api/live-probe.md) (measured behaviour). The `docs/api-notes.md` file first proposed here became those two files.

- [x] Main search endpoint, its query parameters (condition, intervention, sponsor, location, status, advanced filters), and the page-size limit.
- [x] Pagination mechanism (page token) and whether a **total count** can be requested.
- [x] Whether a count-only request is cheap. If so, exact per-bucket counts can come from count queries instead of downloading every record.
- [x] Whether a `fields` parameter can limit the response to the fields we need (smaller and faster responses).
- [x] Any stats or aggregation endpoints, and whether they accept filters.
- [x] Field paths for: NCT ID, title, phases, start date, overall status, lead sponsor name and class, interventions (type, name), conditions, locations (country, facility), collaborators.
- [x] Date formats (full vs partial) and how missing values appear.
- [x] Enumeration values (phase, status, intervention type, sponsor class).
- [x] Error behaviour (400 with a plain-text message, 404 for an unknown study).
- [x] Rate limits (429s). Measured with a careful ramp test on 2026-10-25: about 10 requests per 10 seconds per IP, no limit on concurrency, and no `Retry-After` on the 429. The client allows 9 per 10 seconds and retries 429s and 5xx with backoff; see [`../api/live-probe.md`](../api/live-probe.md), section 8.

## 5. Ambiguities and decisions

### Tension: LLM-produced synonyms vs "authoritative"

Example: someone asks about "Keytruda", but most records say "Pembrolizumab" or "MK-3475".

First proposal:
- The LLM may only **rewrite the search terms**, never data. Any expansion is shown in `meta`, and all matched records still come from the API.
- If the API's own search already handles synonyms, we rely on that and say so.

**Resolved:** the live probe showed that the API resolves brand and code names itself ("Keytruda", "MK-3475" and "pembrolizumab" return the same trials), so the LLM never invents synonyms. See [`../api/live-probe.md`](../api/live-probe.md) and [design Q7](../design/07-query-compilation.md).

### Other decisions

- **Live calls vs a local copy.** By default we query the live API per request, with caching for speed, rate limits and repeatable answers ([design Q6](../design/06-retrieval.md), [Q8](../design/08-cache-ratelimit-retries.md)).
  - A local copy alone can't reproduce the API's synonym and MeSH search ([design Q21](../design/21-local-mirror-revisited.md)). So the opt-in fast mode keeps a daily-synced copy of all ~608k trials but lets the API pick which trials match each search term, and checks every answer against a live count ([design Q22](../design/22-term-sets.md)).
- **Data freshness.** Cached data is from a point in time, so each answer records a `retrieved_at` timestamp in `meta`.

## 6. Acceptance checks

- [ ] No value in any output comes from LLM text. A test confirms that chart data is built only from the parsed API records.
- [ ] `meta` states the source, the retrieval time, and the API queries that were used.
- [x] The verified API behaviour is written down ([`../api/contract.md`](../api/contract.md), [`../api/live-probe.md`](../api/live-probe.md)).
