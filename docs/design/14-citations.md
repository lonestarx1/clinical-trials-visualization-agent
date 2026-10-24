# Design Q14: Deep Citations

Status: **Decided** (2026-10-24)

## What a citation proves

Every number in a chart is backed by the trials that produced it. For each trial we show **the exact value we read** and **where in the record it came from**, so anyone can check it.

## Citation object

```json
{
  "nct_id": "NCT01234567",
  "url": "https://clinicaltrials.gov/study/NCT01234567",
  "title": "Brief title of the trial (context only)",
  "evidence": [
    { "field": "protocolSection.designModule.phases", "excerpt": "PHASE3" }
  ]
}
```

- `excerpt` keeps the PDF's key name and is the **raw API value, copied exactly**. It's never summarised or produced by the AI.
- `field` is the JSON path of that value in the API record.
- **Network edges** have **two** evidence items (one per end), e.g. `leadSponsor.name` + an intervention MeSH term.
- **Enrollment measures** add `designModule.enrollmentInfo.count` (+ `type`).
- **Normalised values** (Q11) cite the raw value. When grouping used MeSH, both the MeSH term and the raw name are given, so a mapping error is visible.

## Per data point (bar, time bucket, bin, point, node, edge, metric)

| Field | Meaning |
|---|---|
| `citation_count` | Number of contributing trials (equals the value for count charts) |
| `citations` | Up to **5** citations by default (`citations_per_datum`, configurable up to 50), in a **fixed order**: most recent start date, then NCT ID |
| `citations_truncated` | `true` if `citation_count > len(citations)` |

## Full citation lists: dedicated endpoint

- Every successful response has a **`result_id`**. The result, including each data point's **full** list of contributing NCT IDs, is stored in Postgres.
- `GET /v1/results/{result_id}/citations?datum=<datum key>&page=<n>&page_size=<<=100>` returns the full, paginated citation list for one data point.
- **Lifetime:** configurable retention (e.g. 24 h). After an API data update, a stored result stays valid as long as its underlying searches pass the revalidation check (Q8). Otherwise it's recomputed, or treated as expired. Expired or unknown IDs return **410 Gone** ("re-run the query").
- **Why:** a broad chart can cover 17,000 trials; inline full lists would make responses megabytes long. The frontend can show "326 trials, view all" and load the list on demand.

## Count-only strategies (S1 stats / S2 per-bucket counts, Q6)

- Each data point cites the **exact API query** that reproduces its count: `{ "type": "api_query", "url": "...", "total_count": 326 }`.
- Trial-level citations for these data points are fetched **on demand** by the citations endpoint (it runs the bucket's query with paging), which costs no API calls unless someone asks.

## `citations: "full"` request option (with a backend size guard)

- A request may ask for all citations inline: `citations: "sample"` (default) or `"full"`.
- **The backend always checks the size before returning.** If the full inline set exceeds a limit (configurable, e.g. **2,000 citations in total** across the response, or an estimated payload above a few MB), it falls back to the sample mode.
- The response then reports `meta.citations = { "requested": "full", "applied": "sample", "reason": "2,000 citation limit exceeded (17,450 contributing trial references)" }`, and the full lists stay available through the endpoint.
- `full` never bypasses the exactness check below.

## Exactness check (always on)

Before a response is returned, code verifies that **every** citation's `excerpt` equals the value at its `field` path in the stored raw API record. A failure is a bug: the response fails loudly (500 with a trace ID) instead of returning an unverifiable citation. The same check runs over all example runs in the test suite. This is evidence for "how we validated correctness" (Part 8).

## Requirement links

P5-1..P5-4 (deep citations for every datum, `nct_id`, exact excerpt), P2-2 (authoritative data), P8-2 (validation evidence), P7-B (bonus).
