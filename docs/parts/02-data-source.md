# Part 2: Data Source

## 1. Source text (verbatim)

> Use the **ClinicalTrials.gov Data API** as the authoritative data source.
>
> - API documentation: https://clinicaltrials.gov/data-api/api
> - You may use any endpoints/fields needed.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P2-1 | MUST | Use the **ClinicalTrials.gov Data API** (not a scraped website, Kaggle dump, or LLM knowledge). | "Use the ClinicalTrials.gov Data API" |
| P2-2 | MUST | It is the **authoritative** source: every fact shown (counts, phases, dates, sponsors, countries) comes from API data. | "as the authoritative data source" |
| P2-3 | MAY | Any endpoint and any field may be used. | "You may use any endpoints/fields needed." |

## 3. What it really means

- "Authoritative" rules out an LLM filling in or "correcting" data. If the API says a trial has no start date, we report it as missing. We don't guess.
- The API's quirks are part of the test. Part 7 grades "sensible handling of real-world API data", so we must deal with:
  - pagination
  - multi-valued fields
  - partial dates
  - inconsistent names
  - large result sets
  - rate limits
- We should read the API docs and **verify behaviour against the live API** (not from memory) before designing around it.

## 4. Things to verify against the live API (do before designing)

Each item below is an **open question until checked**. Record the findings in a separate `docs/api-notes.md`.

- [ ] Main search endpoint, its query parameters (condition, intervention, sponsor, location, status, advanced filters), and the page-size limit.
- [ ] Pagination mechanism (page token?) and whether a **total count** can be requested.
- [ ] Whether a total-count-only request is cheap. If so, exact per-bucket counts could come from count queries instead of downloading every record.
- [ ] Whether a `fields` parameter can limit the response to the fields we need (smaller and faster responses).
- [ ] Any stats/aggregation endpoints, and whether they accept filters.
- [ ] Field paths for: NCT ID, title, phases, start date, overall status, lead sponsor name and class, interventions (type, name), conditions, locations (country, facility), collaborators.
- [ ] Date formats (full vs partial) and how missing values appear.
- [ ] Enumeration values (phase, status, intervention type, sponsor class).
- [ ] Rate limits and error behaviour (429s, 5xx).

## 5. Ambiguities and proposed decisions

### Tension: LLM-produced synonyms vs "authoritative"

Example: the user writes "Keytruda", but most records say "Pembrolizumab" or "MK-3475".

**Proposed:**
- The LLM may only **rewrite the search terms**, never data. Any expansion is shown in `meta` (e.g. `"interpreted 'Keytruda' as intervention search 'pembrolizumab OR Keytruda OR MK-3475'"`). All matched records still come from the API.
- The API's own search may already handle synonyms. If it does, we rely on that and say so.

### Other decisions

- **Live calls vs local copy.** Proposed: query the live API per request, with a response cache (for speed, rate limits, and repeatable example runs).
  - We won't download the full dataset (500k+ studies). That's too large and slow to set up in 24h.
  - It would be a good "with more time" item, because it allows exact aggregate queries in SQL.
- **Cache freshness.** The cache stores data from a point in time, so record a `retrieved_at` timestamp in `meta`.

## 6. Acceptance checks

- [ ] No value in any output comes from LLM text. A test confirms that chart data is built only from the parsed API records.
- [ ] `meta` states the source, the retrieval time, and the API query that was used.
- [ ] `docs/api-notes.md` exists with the verified API behaviour.
