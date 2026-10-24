# ClinicalTrials.gov API v2: live probe findings

This is the second half of our research on the ClinicalTrials.gov API. The first half, [`contract.md`](contract.md), covers what the documentation says. This file covers **what the live API actually does**, with the exact queries and counts, so each finding can be re-run and checked.

- **When:** 2026-10-24 ~16:10-16:30 KST, API `2.0.5`, `dataTimestamp 2026-10-23T09:00:04`
- **How:** 65 calls, throttled to at least 1.5 s apart (stdlib `urllib`). Every call is logged in [`probe-data/calls.jsonl`](probe-data/calls.jsonl).
- **Scripts:** [`scripts/api_probe/`](../../scripts/api_probe/) (`ctg.py` helper + `batch1-4.py`). A later `batch5.py` (one more call, also logged) saved the API's country names to [`reference/location-countries.json`](reference/location-countries.json).
- **Data saved:**
  - [`probe-data/batch1_counts.json`](probe-data/batch1_counts.json): all count results
  - [`probe-data/samples/`](probe-data/samples/): 8 full study records chosen to be messy (now used as test fixtures)
  - `probe-data/raw/`: large dumps, not committed, re-creatable with the scripts
- **Rate limits were deliberately not tested**, to avoid getting blocked. See section 8.

Live counts change daily. Treat every number below as a snapshot.

---

## 1. Result sizes (`countTotal=true&pageSize=1`)

| Search | Total studies |
|---|---|
| all studies (no params) | **608,415** |
| `query.intr=pembrolizumab` | 2,993 |
| ... + `filter.advanced=AREA[StartDate]RANGE[2015-01-01,MAX]` | 2,928 |
| `query.intr=nivolumab` | 2,036 |
| `query.cond=breast cancer` | **16,944** |
| ... + `filter.overallStatus=RECRUITING` | 2,457 |
| `query.cond=lung cancer` | 14,657 |
| `query.cond="lung cancer"` (quoted) | 13,423 |
| `query.cond=type 2 diabetes` | 12,017 |
| `query.cond=alzheimer disease` | 4,327 |
| `query.spons=Merck` | 5,240 |
| `query.lead="Merck Sharp & Dohme LLC"` | 2,191 |
| `AREA[NumInterventions]RANGE[2,MAX]` (no other scope) | 288,821 |

**Takeaways**
- Drug-scoped questions are around **2-3k** studies.
- Broad conditions are around **12-17k**.
- An unscoped drug <-> drug network (appendix PA-9) would be about **289k** studies, so it **must** be scoped.

## 2. Speed and payload

| Request | Latency | Size |
|---|---|---|
| Count-only call (`pageSize=1`, `fields=NCTId`) | **~0.35 s** (median, max 0.59) | <1 KB |
| 1,000 studies, 4 small fields (`NCTId\|Phase\|StartDate\|LeadSponsorClass`) | 1.1 s | 0.22 MB |
| 1,000 studies + `LocationCountry` | 1.5 s | 0.52 MB |
| 1,000 studies + MeSH terms + intervention names | 1.6 s | 0.35 MB |
| 1,000 studies, 21 fields incl. locations + interventions | **2.0-2.2 s** | **~2 MB** |
| Single full study (`/studies/{id}`) | 0.3-0.8 s | 5 KB - 212 KB |
| Full fetch of pembrolizumab (2,993 studies, 21 fields, 3 pages) | 11.1 s wall, incl. our 1.5 s throttle | ~6 MB |

**Takeaways**
- **Location data dominates the payload**: one study has 1,660 sites. Only request `LocationCountry` when the question needs it.
- A full fetch of a broad condition (17 pages) would take ~20-45 s depending on fields and throttling. That's too slow for one interactive request without caching or a count-based strategy.
- **Count queries are cheap (~0.35 s)**, so per-bucket counts are a realistic way to get **exact** totals for big categorical questions.

## 3. Search behaviour (answers to the contract's open questions)

| Question | Finding | Evidence |
|---|---|---|
| Do UMLS synonyms work? | **Yes, for interventions.** `query.intr` = pembrolizumab, `keytruda`, `MK-3475` all return **exactly 2,993**. `AREA[InterventionName]keytruda` = `...pembrolizumab` = 2,582. | batch1 |
| `query.intr` vs strict field search | `query.intr`: **2,993**. `AREA[InterventionNameSearch]`: **2,652**. `AREA[InterventionName]`: **2,582**. In the fetched data, **335 of 2,993** `query.intr` hits have no pembrolizumab in any intervention name/otherName. Some are real combos where pembrolizumab is only in the title (NCT03724851, "Vactosertib in Combination with Pembrolizumab"); others are observational studies about checkpoint-inhibitor side effects (NCT04975932). | batch1, data analysis |
| `EXPANSION[None]` | **Too strict**: 305 (case-sensitive, exact). Don't use. | batch1 |
| Quoted vs unquoted condition | `lung cancer` 14,657 -> `"lung cancer"` 13,423 -> `AREA[Condition]"lung cancer"` 10,676 | batch1 |
| Enum code or label in `AREA[...]`? | **Both work** with identical counts: `AREA[Phase]PHASE3` = `AREA[Phase]"Phase 3"` = 50,082; `AREA[LocationStatus]RECRUITING` = `...Recruiting` = 120,010 | batch1 |
| Date RANGE formats | `RANGE[2015-01-01,MAX]` and `RANGE[01/01/2015,MAX]` both work (410,312). `AREA[StartDate]2022` works (37,730). | batch1 |
| Missing values | `AREA[StartDate]MISSING` = 5,375. `AREA[Phase]MISSING` = 144,290. | batch1 |
| Multi-phase search | `AREA[Phase:size] 2` = 24,793 studies with 2 phases | batch1 |
| Sponsor class filter | `AREA[LeadSponsorClass]INDUSTRY` = 133,187, works | batch1 |
| Search-only numeric fields as filters | `AREA[NumInterventions]RANGE[2,MAX]` works | batch1 |
| `SEARCH[Location](...)` | Works: US **and** recruiting at the same site = 26,520 | batch1 |
| Observational studies and phase | **No `phases` key at all** (not `["NA"]`). `OBSERVATIONAL AND Phase MISSING` = all 142,101 observational studies. `NA` is used by interventional non-drug studies. | batch1, sample `observational_*` |

**Design implications [ours]**
1. **Drug filter:** default to `AREA[InterventionNameSearch]<drug>`, which is name + other names, with synonyms on. That keeps synonym support but drops the "only mentioned in a title/description" noise. Offer the broad `query.intr` as a documented alternative (`match_mode: broad`). Report the mode in `meta`.
2. **Condition filter:** `query.cond` with a **quoted** phrase gives good recall, and still uses MeSH and synonyms. Strict `AREA[Condition]` misses MeSH matches. Proposed default: quoted `query.cond`.
3. **No LLM synonym invention needed** for drugs. The API resolves brand and code names.

## 4. Response shape

| Question | Finding |
|---|---|
| `pageSize=0` + `countTotal` = count-only? | **No.** It falls back to 10 studies. Use `pageSize=1`. |
| `fields` dotted paths | **Work** (`protocolSection.designModule.phases`). Piece names work too. |
| `fields` branch piece | Works (`ArmsInterventionsModule` returns the whole module). |
| Search-only fields in `fields` | Accepted, but come back **empty** (`"designModule": {}`). Confirms they're filter-only. |
| Unknown field in `fields` | `400` `Parameter 'fields' contains invalid field name: 'NoSuchField'` |
| Projected study shape | Same nesting as a full study, with only the requested leaves present. Missing values are **omitted** (key absent), not null. |
| Ordering without `sort` | The same query twice gave the **same order** (not guaranteed by the docs). |
| `sort=StartDate:asc` | Works. Partial dates (`1988-02`) sort alongside full dates. |
| `sort` on a text field | `400 Unsupported sort field type: nct` |
| Unknown NCT ID | `404` `NCT number NCT99999999 not found` (text/plain) |
| Bad `filter.advanced` | `400` `Error parsing query in advanced filter: Unknown area name: 'NoSuchField'` / `missing ')' at '<EOF>'` |
| Bad enum in `filter.overallStatus` | `400` `Invalid value in parameter 'overallStatus': 'RUNNING'` |
| Rate-limit headers | **None** observed on any response (no `X-RateLimit-*`, no `Retry-After`) |

## 5. Real data quirks (2,993 pembrolizumab studies, `query.intr`)

| Topic | Finding |
|---|---|
| **Phases** | `PHASE2` 1,269 · `PHASE1` 575 · **`PHASE1+PHASE2` 476** · `PHASE3` 326 · **missing 176** · `NA` 55 · `EARLY_PHASE1` 52 · **`PHASE2+PHASE3` 44** · `PHASE4` 20. **17% are multi-phase.** |
| Study type | Interventional 2,817 · Observational 171 · Expanded access 5 |
| **Start date format** | `yyyy-MM-dd` 2,769 · **`yyyy-MM` 219** · missing 5. (No `yyyy`-only values in this set.) |
| **Start date type** | ACTUAL 2,630 · ESTIMATED 303 · **no type 60** |
| **Future start dates** | 46, all `ESTIMATED`, up to 2027 |
| Lead sponsor class | OTHER 1,662 · INDUSTRY 1,189 · NIH 81 · NETWORK 26 · OTHER_GOV 24 · FED 8 · UNKNOWN 2 · INDIV 1 |
| **Sponsor names** | Top: "Merck Sharp & Dohme LLC" (274), "M.D. Anderson Cancer Center" (77), "National Cancer Institute (NCI)" (74). Merck also appears as "Immune Design, a subsidiary of Merck & Co., Inc. (Rahway, New Jersey USA)". |
| **Intervention names** | **507 distinct spellings** contain pembrolizumab/Keytruda/MK-3475: "Pembrolizumab" 1,897, "pembrolizumab" 138, "MK-3475" 29, "Keytruda" 18, "Pembrolizumab Injection [Keytruda]", "Pembrolizumab 200 mg", "KEYTRUDA®", "Pembrolizumab/Quavonlimab"... |
| Intervention types | DRUG 6,783 · BIOLOGICAL 1,454 · PROCEDURE 596 · RADIATION 315 · OTHER 290 · ... |
| **Placebo** | 140 interventions named like placebo ("Placebo", "placebo", "Placebo for lenvatinib", "Placebo for pembrolizumab", ...) |
| **Drugs per study** | DRUG+BIOLOGICAL interventions per study: 0 (130), 1 (728), **2+ (2,135)**, max 54 |
| **Locations** | 82,079 sites. **213 studies have none.** Median 2 per study, **max 1,660**. |
| **Country names** | 81 countries, clean English names: "United States", "South Korea", "United Kingdom", "**Turkey (Türkiye)**", "Taiwan", "Russia", "Iran", "Vietnam" |
| **Site status** | **Missing on 53,470 of 82,079 sites (65%)**. RECRUITING 23,156, ... |
| Enrollment | Missing 5. ACTUAL 1,689 / ESTIMATED 1,299. Max **500,000** (outlier) |
| **Conditions** | Up to 101 per study. Raw names are inconsistent ("Non-small Cell Lung Cancer" 113 vs "Non Small Cell Lung Cancer" 90). |

### MeSH terms (`derivedSection`): a ready-made normaliser (1,000-study page)

| Topic | Finding |
|---|---|
| Intervention MeSH coverage | 923 / 1,000 studies have `InterventionMeshTerm`. **7.7% have none.** |
| Intervention MeSH values | Clean: "pembrolizumab" 840, "Carboplatin" 110, "Cisplatin" 82, "Paclitaxel" 78, ... **Placebo never appears** (it isn't a MeSH drug). Casing is inconsistent ("pembrolizumab", "lenvatinib" lowercase). |
| Condition MeSH | **1,353 raw condition strings -> 241 MeSH terms.** |
| **MeSH mapping errors** | "**Parkinson Disease 4, Autosomal Dominant Lewy Body**" appears on **67** pembrolizumab studies. It's almost certainly a mis-mapping (probably from "PD-1"/"PD-L1" text). Automatic MeSH tagging is **not always right**. |

**Design implications [ours]**
1. **Phase counting rule needed.** Options: (a) one bar per phase value, so a multi-phase study counts in both bars; (b) combined labels ("Phase 1/Phase 2") as their own bars, so each study counts once. Also a "No phase (observational)" bucket. Recommend (b) by default, because bars then add up to the total and citations stay one-to-one. Document it.
2. **Year bucketing works for every study with a date.** No `yyyy`-only values were seen, but the code must handle them. Flag ESTIMATED and future years in `meta`, plus a "missing start date" count.
3. **Drug networks should use `InterventionMeshTerm` as the node identity**, with a fallback to a cleaned `InterventionName` when MeSH is missing. This gets normalisation for free, drops placebo, and is fully traceable (the excerpt is the MeSH field value). Case-fold the names.
4. **Condition grouping/networks:** MeSH terms are cleaner, but have mapping errors. Cite the raw `conditions` value next to the MeSH term so a human can spot errors. Mention it as a known limitation.
5. **"Recruiting" = `overallStatus`**, not site status: site status is missing for 65% of sites. For "countries with recruiting trials", count trials with `overallStatus=RECRUITING` per country of their sites.
6. **Sponsor names are not normalised by the API.** Keep the raw `leadSponsor.name` (it's exact, and so cites cleanly) plus light normalisation (trim, case) for node merging. List it as a limitation.
7. **Fetch only the fields each question needs.** Locations make responses 2-5x bigger.

## 6. Retrieval strategy options (input to the design step)

| Strategy | How | Pros | Cons |
|---|---|---|---|
| **A. Fetch and aggregate** | Download the matching studies with minimal `fields`, aggregate in Python | One generic engine for every chart type (incl. networks, histograms). Citations come out naturally. Works for any field. | Broad conditions (12-17k) take ~20-45 s cold. |
| **B. Count per bucket** | One `countTotal` call per category (`AREA[Phase]PHASE3`, `AREA[StartDate]2019`, ...) | Exact, ~0.35 s per bucket, independent of result size | Only for known small category sets. No citations. Can't do networks or top-N over open-ended values (countries, sponsors). Many calls, which matters under rate limits. |
| **C. Hybrid** | A for data and citations, capped at N studies (e.g. 3-5k). If over the cap, fall back to B for exact totals, or sample and say so in `meta`. | Best of both | More code paths |

The probe didn't decide between them. At the time, the lean was **A as the main path, plus a cache, with a per-request study cap** reported in `meta`, optionally adding B for exact totals on enum dimensions. The design decision is [Q6](../design/06-retrieval.md).

## 7. Saved sample records (`probe-data/samples/`)

| File | Why it's interesting |
|---|---|
| `multi_phase_NCT03724851.json` | PHASE1+PHASE2; pembrolizumab only in title/arm description, not an intervention entry |
| `combo_NCT02648477.json` | ≥3 drug/biologic interventions (drug <-> drug network) |
| `observational_NCT04975932.json` | Observational: no `phases` key |
| `placebo_NCT05834413.json` | Has a placebo intervention |
| `partial_date_NCT05894447.json` | Start date `yyyy-MM` |
| `many_locations_NCT02506153.json` | 576 sites, Phase 3 |
| `future_start_NCT07886905.json` | ESTIMATED start date in the future |
| `missing_start_NCT04135092.json` | No start date |

## 8. Rate limits: educated guess (not tested on purpose)

No official limit is published (see contract §6), and we saw **no rate-limit headers** in 65 calls. Third-party references:
- ~50 requests/min per IP ([API reference doc](https://cdn.jsdelivr.net/npm/@saibolla/ada@0.1.3/skills/clinicaltrials-database/references/api_reference.md)), the most conservative figure
- ~3 requests/s ([Jentic](https://jentic.com/apis/clinicaltrials.gov/clinicaltrials))
- 429 returned when exceeded (same reference doc)
- no formal published value; use bounded concurrency + backoff with jitter ([IntuitionLabs](https://intuitionlabs.ai/pdfs/clinicaltrials-gov-api-v2-pipeline.pdf))

**What the client is built for (assuming the strictest figure):**
- **One shared client-side rate limiter**, default **~40 requests/min**, ~1.5 s spacing, configurable. 20% headroom under 50/min.
- **Low concurrency** (default 2 in flight).
- **Retry on 429 / 5xx / timeouts** with exponential backoff and jitter. Honour `Retry-After` if it ever appears. Give up after N tries with a clear upstream error.
- **Response cache** keyed by normalised request params. Repeat questions and example runs cost zero API calls.
- **Budget per request:** a cap on pages per question, reported in `meta`.
- Under 40/min, strategy B (one call per bucket) gets expensive quickly. Another reason to prefer A plus a cache.

**Measured (2026-10-25), with ~120 cheap count calls from one IP:**

| Test | Result |
|---|---|
| 2, 4 or 8 calls at once | all answered, ~0.36 s each |
| 16 at once, after a 70 s rest | 10 answered, then `429` |
| one at a time, back to back | 11 answered, then `429` within 2.9 s |
| a steady 60/min for 45 s | all 45 answered |
| a steady 66/min or 90/min | `429` after 11-13 calls |
| after a `429` | answers again after ~7 s |

So the limit is about **10 requests per ~10 s window** (~60/min) per IP. **Concurrency is not limited**: a burst is fine as long as it stays inside the window. The `429` carries **no `Retry-After`** and no rate-limit headers. A count call takes ~0.35 s and a 1,000-trial page ~0.8-1.2 s.

**What changed in the client:** 9 requests per 10 s (54 a minute), up to 9 at once (a sliding window, 10% under the measured limit), and a `429` without `Retry-After` waits 10 s instead of the 1 s first backoff. Measured on the live API, 16 count calls went from 22.8 s to 10.4 s, and 17 per-year counts from 24.3 s to 10.4 s.

## 9. `/stats/field/values`: counting and the 250-value cap (open item O4)

Measured 2026-10-25 (data timestamp `2026-10-23T09:00:04`, 608,415 studies), about 25 calls.

| Field | Type | Unique values | `topValues` returned | Sum of counts | Missing |
|---|---|---|---|---|---|
| `Phase` | ENUM | 6 | 6 | 488,918 | 144,290 |
| `OverallStatus` | ENUM | 14 | 14 | 608,415 | 0 |
| `LeadSponsorClass` | ENUM | 9 | 9 | 607,427 | 988 |
| `LocationCountry` | STRING | 226 | 226 | 787,289 | 61,012 |
| `LeadSponsorName` | STRING | 52,529 | **250** | 241,288 | 0 |
| `Condition` | STRING | 134,756 | **250** | 316,724 | 1,026 |

**Counting:**
- `studiesCount` is a number of **studies**, the same as a search. For `Phase` NA, PHASE2 and PHASE1, `OverallStatus` COMPLETED, UNKNOWN and RECRUITING, and `LeadSponsorClass` OTHER, INDUSTRY and OTHER_GOV, it equals `countTotal` for `AREA[field]value` exactly.
- A study with several values counts once under each value. The phase counts plus the missing ones add up to 633,208, more than the 608,415 studies (multi-phase trials). The country counts add up to 787,289.
- `missingStudiesCount` equals `AREA[field]MISSING` exactly.

**The cap:** ENUM fields return every value. STRING fields return at most the **top 250** by count, so 52,529 lead sponsors come back as 250.

**STRING values are raw strings, not search terms.** `Condition` "Breast Cancer" has 8,945 studies in the stats (that exact string), but the search `AREA[Condition]"Breast Cancer"` finds 15,214, because it also matches longer condition strings that contain the phrase. `LeadSponsorName` "GlaxoSmithKline" happens to agree (3,647 both ways).

**Unscoped only:** adding a query parameter (`query.cond=melanoma`) returns `400`. The endpoint describes the whole registry, never a filtered subset.

**What this means for strategy S1 (Q6):** S1 is exact, in one call, only for **unscoped questions over an ENUM field** (phase, status, sponsor class, study type and similar). It doesn't fit STRING fields (raw strings, top 250 only) or any question with a filter. S2 (one count per bucket) already answers those questions exactly at some calls' cost, so S1 stays unbuilt: it would only speed up a narrow set of questions.

## 10. Does every change bump `LastUpdatePostDate`? (open item O5)

**No, not for derived data.** Measured 2026-10-25:

- **Derived data is rebuilt with every release.** Records last updated in December 2005 (e.g. NCT00145262, NCT00271141) carry `derivedSection.miscInfoModule.versionHolder` = `2026-10-23`, the current data version, while their `LastUpdatePostDate` stays 2005.
- **Their MeSH terms are current.** NCT00145262, last updated in 2005, is tagged with the MeSH heading "Chronic Limb-Threatening Ischemia". Four trials last updated in January to May 2021 carry "Post-Acute COVID-19 Syndrome", a heading MeSH added in its 2022 edition (e.g. NCT04694768, last updated 2021-01-05, condition "Post COVID-19 Syndrome").

So the registry re-maps conditions and interventions to MeSH, and recomputes other derived fields, **without bumping `LastUpdatePostDate`**. A condition or drug search (which uses the MeSH terms and their synonyms) can therefore gain or lose a trial that wasn't edited. The sponsor-submitted fields, such as status, phase and dates, are only changed by an update, which does bump the date.

**What this means for revalidation (Q8):**
- Check 1 (no trial changed since) can miss a re-mapped trial.
- Check 2 (the total count is unchanged) still catches any re-mapping that changes the count, but not a swap where one trial leaves and another joins.
- MeSH re-mapping is rare (mostly the yearly MeSH update), so the risk is small but real. The **7-day safety ceiling stays**: no stored answer is reused for more than 7 days without being recomputed.

## 11. The code `ALL` must be quoted (found by the mirror cross-check)

Measured 2026-10-25. `AREA[Sex]ALL` matches **every** trial (608,415): Essie reads the bare word `ALL` as "everything". Quoted, `AREA[Sex]"ALL"` matches the 523,690 trials open to all sexes, exactly the `/stats/field/values` count. `AREA[Sex]FEMALE` (58,711), `AREA[Sex]MALE` (24,611) and `AREA[Sex]MISSING` (1,403) match their stats counts, and so do the other code values that look like keywords: `AREA[DesignMasking]NONE` (254,813, quoted or not), `AREA[Phase]NA` (239,565) and the booleans. The compiler quotes `ALL` (`QUOTED_CODES` in `app/ctgov/essie.py`).
