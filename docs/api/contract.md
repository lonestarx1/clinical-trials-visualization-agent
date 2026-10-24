# ClinicalTrials.gov API v2: what the documentation says

This is the first half of our research on the ClinicalTrials.gov API: what the **official documentation** says, read on 2026-10-24 (KST). The second half, [`live-probe.md`](live-probe.md), tests these statements against the live API. Where the probe answered a question raised here, this file links to the answer.

- Statements marked **[docs]** are quoted or closely paraphrased from official sources.
- Statements marked **[ours]** are our interpretation, or what it means for the design.
- Every source is saved in [`reference/`](reference/), so each claim can be checked against the copy we read.

## Sources (saved in `docs/api/reference/`)

| File | Source | What it is |
|---|---|---|
| `ctg-oas-v2.yaml` | https://clinicaltrials.gov/api/oas/v2 | Official OpenAPI 3.0.3 spec, API version **2.0.5** |
| `studies-metadata.json` | `GET /api/v2/studies/metadata` | Full field tree: path, piece name, type |
| `studies-metadata-indexed.json` | same, `?includeIndexedOnly=true` | Adds search-only fields (e.g. `NumPhases`, `NumLocations`) |
| `studies-search-areas.json` | `GET /api/v2/studies/search-areas` | What each `query.*` parameter actually searches, with weights |
| `studies-enums.json` | `GET /api/v2/studies/enums` | All enum values plus display labels |
| `essie-search-syntax.txt` | https://clinicaltrials.gov/find-studies/constructing-complex-search-queries | Search syntax reference (page last updated 2026-02-09) |

The prose pages are rendered with JavaScript, so we rendered them with headless Chrome to read them. `/api/v2/version` at read time: `apiVersion 2.0.5`, `dataTimestamp 2026-10-23T09:00:04`.

---

## 1. Endpoints

Base URL: `https://clinicaltrials.gov/api/v2`. No auth. GET only.

| Endpoint | Purpose | Useful to us? |
|---|---|---|
| `GET /studies` | Search studies; paginated | **Core.** All retrieval goes through this. |
| `GET /studies/{nctId}` | One study (json, csv, json.zip, fhir.json, ris). An alias NCT ID returns a 301 redirect. | Citations / detail lookup |
| `GET /studies/metadata` | Data model field tree | Field paths for our registry |
| `GET /studies/search-areas` | Search areas and their weighted fields | Understanding search precision |
| `GET /studies/enums` | Enum values plus display labels | Display labels for phase/status/... |
| `GET /stats/size` | JSON size stats | No |
| `GET /stats/field/values` | Value counts of a field over **all** studies | **No for filtered questions.** [docs] It "does not accept a search expression and always returns the values for all studies, plus the number of returning values is limited to 250" (migration guide). |
| `GET /stats/field/sizes` | Sizes of list fields | No |
| `GET /version` | API version and `dataTimestamp` | Put into `meta.data_version` |

**[ours] Key consequence:** there is **no server-side aggregation for filtered searches**. To count "phases for pembrolizumab trials", we must either:
- (a) download the matching studies (only the fields we need) and count them ourselves, or
- (b) send one `countTotal` query per category bucket.

The choice depends on result sizes and speed, which the live probe measured ([live-probe §1-2 and §6](live-probe.md#6-retrieval-strategy-options-input-to-the-design-step)).

## 2. `GET /studies` parameters

### Query parameters (Essie syntax; they affect relevance ranking)

| Param | Search area | Fields actually searched (weight) [docs: search-areas] |
|---|---|---|
| `query.cond` | ConditionSearch | Condition (0.95), BriefTitle (0.6), OfficialTitle (0.55), ConditionMeshTerm (0.5), ConditionAncestorTerm (0.4), Keyword (0.3), NCTId (0.2) |
| `query.intr` | InterventionSearch | InterventionName (0.95), InterventionType (0.85), ArmGroupType (0.85), InterventionOtherName (0.75), BriefTitle (0.65), OfficialTitle (0.6), ArmGroupLabel, InterventionMeshTerm, Keyword (0.5), InterventionAncestorTerm, InterventionDescription, ArmGroupDescription (0.4) |
| `query.spons` | SponsorSearch | LeadSponsorName (1.0), CollaboratorName (0.9), OrgFullName (0.6) |
| `query.lead` | (field) | LeadSponsorName only |
| `query.locn` | LocationSearch | LocationCity, LocationState, LocationCountry, LocationFacility (0.95), LocationZip (0.35) |
| `query.titles` | TitleSearch | Acronym, BriefTitle, OfficialTitle |
| `query.outc` | OutcomeSearch | Outcome measures/descriptions |
| `query.id` | IdSearch | NCTId, NCTIdAlias, Acronym, OrgStudyId, SecondaryId |
| `query.patient` | PatientSearch | Broad patient-facing mix |
| `query.term` | BasicSearch | Very broad: 39 weighted field groups, including titles, conditions, interventions, summaries, outcomes, LeadSponsorName (0.4), locations (0.35), MeSH terms, design enums. Also accepts any `AREA[...]` expression. |

Two more search areas have **no** `query.*` parameter, but can be used via `AREA[...]` in `query.term` / `filter.advanced`:
- `InterventionNameSearch`: InterventionName (1.0), InterventionOtherName (0.9)
- `FunderTypeSearch`: LeadSponsorClass (1.0), CollaboratorClass (0.9)

**Synonym expansion is per field, not global.** [docs: `isSynonyms` flag in `/studies/search-areas`]

| Synonyms? | Fields |
|---|---|
| `isSynonyms: true` | Condition, InterventionName, InterventionOtherName, titles, Keyword, MeSH terms, descriptions |
| `isSynonyms: false` | **All sponsor fields** (LeadSponsorName, CollaboratorName, OrgFullName), **all location fields**, NCT/ID fields, enum fields (Phase, InterventionType, ArmGroupType, StudyType, ...) |

[ours] So sponsor names like "Merck" vs "Merck Sharp & Dohme LLC" and country spellings are **not** matched by the API's synonym logic.

**[ours] Precision warning.** `query.intr=pembrolizumab` also matches trials that only mention pembrolizumab in a **title, keyword, arm description or MeSH ancestor**. That includes comparator mentions. `query.cond=lung cancer` also matches titles and MeSH **ancestor** terms. Both are good for recall but loose for "trials **of** drug X". For strict matching, `AREA[InterventionName]pembrolizumab` (or the `InterventionNameSearch` area, which covers InterventionName 1.0 and InterventionOtherName 0.9) is available through `filter.advanced` / `query.term`. The live probe compares the counts ([live-probe §3](live-probe.md#3-search-behaviour-answers-to-the-contracts-open-questions)).

### Filter parameters (no ranking effect)

| Param | Format | Notes |
|---|---|---|
| `filter.overallStatus` | pipe/comma list of `Status` | e.g. `RECRUITING` |
| `filter.advanced` | Essie expression | [docs] examples: `AREA[StartDate]2022` (a year-only term matches partial dates), `AREA[MinimumAge]RANGE[MIN, 16 years]`. [ours, unverified] `AREA[StartDate]RANGE[2015-01-01,MAX]`, `AREA[Phase]PHASE3`, `AREA[LeadSponsorClass]INDUSTRY` |
| `filter.geo` | `distance(lat,lon,dist)` | Radius search only |
| `filter.ids` | NCT ID list | Matches NCTId and aliases |
| `filter.synonyms` | `area:synonym_id` pairs | Internal synonym IDs, undocumented source |
| `postFilter.*` | same as `filter.*` | [docs] "same effect as there is no aggregation calculation" |
| `aggFilters` | e.g. `results:with,status:com` | Website facet filters |

[docs] If **any** query parameter contains only NCT IDs, filters are ignored. If neither queries nor filters are set, **all** studies are returned. `geoDecay` is ignored when a result has more than 10,000 studies.

### Response shaping and paging

| Param | Contract [docs] |
|---|---|
| `fields` | Pipe/comma list; [docs] each item is "either area name, piece name, field name, or special name" (`@query` = the fields that were searched). Branch nodes include all their descendants. If left out, **all** fields come back (large). [ours] The item pattern allows dots, and `/stats` docs show dotted paths, but **dotted paths in `/studies?fields=` are unverified**. |
| `sort` | Up to **2** items, `field[:asc\|desc]`. **Only date and numeric fields**, or `@relevance`. Studies missing the sort field always come last. Default direction: date `desc`, numeric `asc`, `@relevance` `desc`. **With no `sort`, results are unsorted** "for a performance reason". |
| `countTotal` | `true` puts `totalCount` on the **first page only**. |
| `pageSize` | Default **10**; 0 means the default; values above **1,000** are reduced to 1,000. |
| `pageToken` | Value from the previous page's `nextPageToken`. The last page has no token. **A page may have an empty `studies` array.** Later pages **must** use the same params, except `countTotal`/`pageSize`/`pageToken`. |
| `format` | `json` (default) or `csv` (CSV: `x-total-count`, `x-next-page-token` headers). |
| `markupFormat` | `markdown` (default) or `legacy`. |

Response body: `{ "studies": [...], "nextPageToken"?: str, "totalCount"?: int }`. Errors: `400` with a `text/plain` message. `/studies/{id}` also returns `404` and `301`.

**[ours]**
- With no default sort order, results come back in no fixed order. To make example runs repeatable, we need an explicit sort (e.g. `sort=StartDate` or `LastUpdatePostDate`) or to sort NCT IDs ourselves after fetching.
- Our citation order must not depend on API order.
- An empty page that still has a `nextPageToken` must not be treated as "done".

## 3. Essie search syntax (for `query.*`, `filter.advanced`)

[docs] Operator precedence, highest to lowest: terms and source operators > NOT and context operators > AND > OR.

| Operator | Meaning [docs] |
|---|---|
| `OR`, `AND`, `NOT`, `"phrase"`, `( )` | Boolean and grouping |
| `AREA[Field]term` | Search one area **or any field** from the data structure |
| `SEARCH[Location](...)` | Requires several conditions to match **within the same location** (e.g. country = X **and** status = Recruiting at that same site) |
| `COVERAGE[FullMatch\|StartsWith\|EndsWith\|Contains]` | How much of the field must match. **Default: Contains.** |
| `EXPANSION[None\|Term\|Concept\|Relaxation\|Lossy]` | How far a term is expanded. **Default: Relaxation.** |
| `RANGE[min,max]` | Numeric/date range; `MIN`/`MAX` allowed. **Excludes studies with no value.** |
| `MISSING` | Field has no value |
| `ALL` | All studies |
| `AREA[Field:size] n` | (from `/stats/field/sizes` docs) list length, e.g. `AREA[Phase:size] 2` = studies with 2 phases |
| `DISTANCE[...]`, `TILT[...]` | Geo radius; ranking bias |

[docs] Combination rules:
- `SEARCH[...]` takes only `Study` or `Location`.
- `COVERAGE[FullMatch|StartsWith|EndsWith]` work only with `EXPANSION[Concept|Term|None]`.
- `EXPANSION[Lossy]` can't be combined with any COVERAGE.
- A quoted phrase under Relaxation/Lossy behaves like `EXPANSION[Concept]`.
- RANGE date examples appear in both `01/01/2015` and `2025-03-20` forms.
- The location example writes the status as a label: `AREA[LocationStatus]Recruiting`, not `RECRUITING`.

[docs] Expansion levels:
- **Term:** plurals, spelling variants, ignores case and hyphens.
- **Concept:** adds **UMLS synonyms**.
- **Relaxation** (the default): Concept plus partial-term matches. "heart disease" matches "heart ... lung disease".
- **Lossy:** may drop words.

**[ours]**
1. **Synonyms are partly handled by the API.** The default expansion includes UMLS synonyms (Concept ⊂ Relaxation), **but only on fields flagged `isSynonyms`**: conditions, interventions, titles, MeSH. So "Keytruda" -> pembrolizumab *may* be covered without the LLM inventing synonyms. The documentation doesn't say whether UMLS links that brand name to the generic (the live probe found that it does). **Sponsor and location fields get no synonym expansion**, so sponsor/country normalisation is on us.
2. **The default Relaxation is loose.** Multi-word conditions can match unrelated studies. Quoting phrases (`"lung cancer"`, effectively Concept level) should help; the live probe measures the difference.
3. **"Recruiting trials in country X"** needs `SEARCH[Location](AREA[LocationCountry]X AND AREA[LocationStatus]Recruiting)` if it means recruiting **at a site in X**. `filter.overallStatus=RECRUITING` means the trial overall is recruiting. The two readings differ, so the design has to pick one and document it.
4. **Year ranges** work through `filter.advanced=AREA[StartDate]RANGE[2015-01-01,MAX]`. The range excludes studies with no start date, so report that.

## 4. Data model: the fields relevant to this project

From `/studies/metadata`. "Piece" is the short name used in `fields=`, `AREA[...]` and `sort=`.

| Piece | JSON path | Type | Multi-valued? |
|---|---|---|---|
| NCTId | `protocolSection.identificationModule.nctId` | nct (11 chars) | no |
| BriefTitle / OfficialTitle | `protocolSection.identificationModule.briefTitle` / `.officialTitle` | text | no |
| OverallStatus | `protocolSection.statusModule.overallStatus` | Status | no |
| StartDate (+ type) | `protocolSection.statusModule.startDateStruct.date` / `.type` | **PartialDate** + ACTUAL/ESTIMATED | no |
| PrimaryCompletionDate / CompletionDate | `...statusModule.primaryCompletionDateStruct.date` / `completionDateStruct.date` | PartialDate | no |
| StudyFirstPostDate | `...statusModule.studyFirstPostDateStruct.date` | full date | no |
| Phase | `protocolSection.designModule.phases` | **Phase[]** | **yes** |
| StudyType | `protocolSection.designModule.studyType` | StudyType | no |
| EnrollmentCount (+ type) | `protocolSection.designModule.enrollmentInfo.count` / `.type` | integer + ACTUAL/ESTIMATED | no |
| LeadSponsorName / LeadSponsorClass | `protocolSection.sponsorCollaboratorsModule.leadSponsor.name` / `.class` | text / AgencyClass | no |
| CollaboratorName / CollaboratorClass | `...sponsorCollaboratorsModule.collaborators[].name` / `.class` | text / AgencyClass | **yes** |
| InterventionType / InterventionName | `protocolSection.armsInterventionsModule.interventions[].type` / `.name` | InterventionType / text | **yes** |
| InterventionOtherName | `...interventions[].otherNames` | text[] | **yes (nested)** |
| ArmGroupType | `...armsInterventionsModule.armGroups[].type` | ArmGroupType (incl. PLACEBO_COMPARATOR) | **yes** |
| Condition / Keyword | `protocolSection.conditionsModule.conditions` / `.keywords` | text[] | **yes** |
| ConditionMeshTerm | `derivedSection.conditionBrowseModule.meshes[].term` | text | **yes** |
| InterventionMeshTerm | `derivedSection.interventionBrowseModule.meshes[].term` | text | **yes** |
| LocationCountry / Facility / City / Status | `protocolSection.contactsLocationsModule.locations[].country` / `.facility` / `.city` / `.status` | text / RecruitmentStatus | **yes** |
| OverallOfficialName / Affiliation | `...contactsLocationsModule.overallOfficials[].name` / `.affiliation` | text | **yes** |
| HasResults | `hasResults` | boolean | no |

**Search-only fields** (only returned by `/studies/metadata` when `includeIndexedOnly=true`; usable in `AREA[...]`; [ours] probably absent from study JSON, which the live probe confirmed): `NumPhases`, `NumInterventions`, `NumLocations`, `NumUniqueLocationCountries`, `NumArmGroups`, `NumCollaborators`, `NumConditions`, `LocationCountryCode`, `StudyFirstPostYear`, and others. There is **no** `StartYear`.

**[ours] Numeric fields** for histograms and scatter plots:
- `EnrollmentCount`
- duration (`CompletionDate - StartDate`, derived; partial dates make it approximate)
- number of locations / countries / arms. These are search-only, so we compute them from returned arrays instead (`len(locations)`, unique countries).

### Formats [docs]

- `PartialDate` = `yyyy`, `yyyy-MM`, or `yyyy-MM-dd`. Year bucketing is always possible; month bucketing is not.
- `DateType` = `ACTUAL` | `ESTIMATED`. [ours, verify] Estimated start dates are probably often in the **future** (not-yet-recruiting trials).
- `markup` fields (e.g. descriptions) default to Markdown.

## 5. Enums and display labels (from `/studies/enums`)

| Enum | Values -> display label (`legacyValue`) |
|---|---|
| Phase | NA -> Not Applicable, EARLY_PHASE1 -> Early Phase 1, PHASE1 -> Phase 1, PHASE2 -> Phase 2, PHASE3 -> Phase 3, PHASE4 -> Phase 4 |
| Status (OverallStatus) | ACTIVE_NOT_RECRUITING, COMPLETED, ENROLLING_BY_INVITATION, NOT_YET_RECRUITING, RECRUITING, SUSPENDED, TERMINATED, WITHDRAWN, AVAILABLE, NO_LONGER_AVAILABLE, TEMPORARILY_NOT_AVAILABLE, APPROVED_FOR_MARKETING, WITHHELD, UNKNOWN -> "Unknown status" |
| RecruitmentStatus (`LocationStatus`, per site) | 9 values: ACTIVE_NOT_RECRUITING, COMPLETED, ENROLLING_BY_INVITATION, NOT_YET_RECRUITING, RECRUITING, SUSPENDED, TERMINATED, WITHDRAWN, AVAILABLE. **No** UNKNOWN / WITHHELD / NO_LONGER_AVAILABLE / TEMPORARILY_NOT_AVAILABLE / APPROVED_FOR_MARKETING. |
| AgencyClass (sponsor class) | NIH, FED, OTHER_GOV, INDIV, INDUSTRY, NETWORK, AMBIG, OTHER, UNKNOWN (legacy labels are the same codes; we write our own readable labels) |
| InterventionType | BEHAVIORAL, BIOLOGICAL, COMBINATION_PRODUCT, DEVICE, DIAGNOSTIC_TEST, DIETARY_SUPPLEMENT, DRUG, GENETIC, PROCEDURE, RADIATION, OTHER |
| StudyType | EXPANDED_ACCESS, INTERVENTIONAL, OBSERVATIONAL |
| ArmGroupType | EXPERIMENTAL, ACTIVE_COMPARATOR, PLACEBO_COMPARATOR, SHAM_COMPARATOR, NO_INTERVENTION, OTHER |
| DateType / EnrollmentType | ACTUAL, ESTIMATED |

**[ours]**
- Phase is an **array**, so a study with `[PHASE1, PHASE2]` is a "Phase 1/Phase 2" study. There is no separate PHASE1_PHASE2 enum value.
- `ArmGroupType = PLACEBO_COMPARATOR` helps detect placebo arms. Placebo **interventions** still need name-based detection (e.g. "Placebo").

## 6. Operational rules

| Topic | Official? | Content |
|---|---|---|
| Data refresh | [docs] | "refreshed daily Monday through Friday, generally by 9 a.m. ET (14:00 UTC)". Check `dataTimestamp` at `/version`. |
| Auth / API key | [docs] | None needed (the spec has no security scheme). |
| Rate limit | **Not stated in any official page we read** | Third-party sources disagree: ~50 req/min per IP ([reference doc](https://cdn.jsdelivr.net/npm/@saibolla/ada@0.1.3/skills/clinicaltrials-database/references/api_reference.md)) vs ~3 req/s ([Jentic](https://jentic.com/apis/clinicaltrials.gov/clinicaltrials)). One analysis ([IntuitionLabs](https://intuitionlabs.ai/pdfs/clinicaltrials-gov-api-v2-pipeline.pdf)) notes no formal value is published. **[ours]** Design for limits we can't see in advance: bounded concurrency, exponential backoff with jitter on 429/5xx, caching. The live probe deliberately did not test the limit ([live-probe §8](live-probe.md#8-rate-limits-educated-guess-not-tested-on-purpose)). |
| Data ingest change | [docs] | Since 2025-08-26 modernised ingest: some markup formats differ; "Locations and geopoint data are now pulling from a different database for geographic data." [ours, speculation] Country/city spellings may differ from older third-party write-ups; check live values. |

## 7. Implications for our design (summary, [ours])

1. **Retrieval = `/studies` with field projection plus pagination.** No filtered aggregation endpoint exists, so the aggregation engine is ours. That is exactly where the deep citations come from.
2. **Two count strategies** are available; the live probe measures what each costs:
   - fetch the minimal fields for all matches (needed anyway for citations, networks and histograms)
   - `countTotal` per bucket (exact totals for big categorical questions, but no citations)
3. **Search precision is a real design choice:** `query.intr` (broad) vs `AREA[InterventionName]` (strict), and phrase quoting. Report which was used in `meta`.
4. **The API handles synonyms (UMLS)**, so the LLM doesn't need to invent drug synonyms.
5. **Multi-valued fields everywhere** (phases, interventions, conditions, countries, sponsors). The counting rule must be explicit per dimension.
6. **Partial and estimated dates.** Bucket by year, flag estimated or future dates, and exclude missing dates with a count in `meta`.
7. **Results are unordered by default.** Sort explicitly so outputs and citations are the same on every run.
8. **Display labels** come from `/studies/enums` `legacyValue`, plus our own labels for AgencyClass.

## 8. Questions the documentation leaves open

**All are answered in [`live-probe.md`](live-probe.md)** (2026-10-24), except the rate limit, which was deliberately not tested. Summary:
- [x] Result sizes: drug ~2-3k, broad condition ~12-17k, unscoped multi-intervention ~289k
- [x] Latency: count ~0.35 s; 1,000 studies 1.1-2.2 s depending on fields
- [x] Keytruda / MK-3475 = pembrolizumab: **yes**, identical counts
- [x] `query.intr` 2,993 vs `AREA[InterventionNameSearch]` 2,652 vs `AREA[InterventionName]` 2,582
- [x] Quoted `"lung cancer"` 13,423 vs unquoted 14,657
- [x] `fields`: piece names **and** dotted paths both work
- [x] `pageSize=0` falls back to 10 (use `pageSize=1` for counts)
- [x] Country names: clean English ("South Korea", "Turkey (Türkiye)")
- [x] Error format: 400/404 `text/plain` with a clear message
- [ ] Rate limit: **not tested** (risk of being blocked). Educated guess and design in live-probe §8
- [x] `AREA[Phase]PHASE3` = `AREA[Phase]"Phase 3"`; `AREA[StartDate]RANGE[...]` (both date formats); `AREA[LeadSponsorClass]INDUSTRY`: all work
- [x] Search-only fields: accepted in `fields` but returned empty
- [x] Observational studies: `phases` key absent (not `NA`)
- [x] Estimated future start dates exist (46 of 2,993, all ESTIMATED)

## 9. Corrections from a second review (2026-10-24)

A second pass re-checked each claim against the saved source files. It made these corrections:

| # | Was | Now | Evidence |
|---|---|---|---|
| 1 | "The API handles synonyms" (general) | Synonyms apply **only** to `isSynonyms: true` fields. Sponsors, locations, IDs and enums have none. | `studies-search-areas.json` per-part `isSynonyms` |
| 2 | `query.term` listed briefly | Lists its real breadth (39 field groups, incl. sponsor and location) | `studies-search-areas.json` BasicSearch |
| 3 | Missed `FunderTypeSearch` area | Added: sponsor class searchable via `AREA[LeadSponsorClass]` | same |
| 4 | `AREA[Phase]PHASE3` shown as if documented | Marked as our unverified syntax; added the documented examples | spec `filter.advanced` examples |
| 5 | Sort default direction missing | Added date desc / numeric asc / relevance desc | spec `sort` description |
| 6 | `fields` accepts "field paths" | Docs say "field name"; dotted paths unverified | spec `fields` description |
| 7 | RecruitmentStatus "Status minus expanded-access values" | Exact 9-value list (it **includes** AVAILABLE, **excludes** UNKNOWN) | spec `RecruitmentStatus` enum |
| 8 | Search-only fields "not returned in JSON" stated as fact | Marked as probable, to verify | metadata only says "indexed-only" |
| 9 | "Estimated start dates can be in the future" stated as fact | Marked as our expectation, to verify | not in docs |
| 10 | "Country names may differ" presented next to a docs quote | Exact docs quote kept; our guess labelled as speculation | API page notice |
| 11 | Missing combination rules for COVERAGE/EXPANSION/SEARCH | Added | `essie-search-syntax.txt` |
| 12 | Missing "no params = all studies" and `geoDecay` limit | Added | spec `/studies` description |

Confirmed correct, no change needed:
- endpoint list (9 GET paths, no other methods)
- no auth scheme in the spec
- paging rules (default 10, max 1,000, empty pages possible, `totalCount` on the first page only)
- the `/stats/field/values` 250-value cap and no filtering (migration guide)
- Essie defaults (Contains, Relaxation)
- RANGE excludes missing values
- data refresh schedule quote
- all field paths in section 4 (from metadata)
- enum labels in section 5
- **no `StartYear` field exists**, so start-year bucketing is ours
