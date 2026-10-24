# Design Q11: Name Normalisation

Status: **Decided** (2026-10-24)

## Principle

Normalisation changes **how values are grouped**, never **which trials are counted**. The **raw API value is always kept** next to the normalised key and used as the citation excerpt, so every grouping can be checked by a human.

## Rules per entity

| # | Entity | Group key | Details |
|---|---|---|---|
| D11.1 | **Drugs** | `derivedSection.interventionBrowseModule.meshes[].term`, compared **case-insensitively** (display: the most common casing) | Fallback when a trial has **no** intervention MeSH term (7.7% in the probe): a cleaned `InterventionName`. Cleaning removes dose/strength text ("200 mg", "10 mg/kg"), ® / ™ / ©, dosage-form words ("injection", "tablet", "infusion", "oral solution"), and bracketed text; then trims and case-folds. Only `DRUG` and `BIOLOGICAL` interventions count as drugs. |
| D11.2 | **Placebo** | Excluded from drug dimensions and networks | MeSH never contains placebo. For the fallback path, a name check (`placebo`, `matching placebo`, `vehicle`, `sham`) excludes it. Exclusion counts are reported in `meta`. |
| D11.3 | **Conditions** | `derivedSection.conditionBrowseModule.meshes[].term` by default; `condition_source: raw` option uses `conditionsModule.conditions` (trimmed, case-folded) | MeSH merges 1,353 raw strings into 241 terms (probe), but has **mapping errors** (67 pembrolizumab trials tagged "Parkinson Disease 4, Autosomal Dominant Lewy Body"). Citations show the raw condition string next to the MeSH term. |
| D11.4 | **Sponsors** (lead and collaborators) | Raw name, lightly normalised: trim, collapse whitespace, case-fold | **No fuzzy or semantic merging.** "Merck Sharp & Dohme LLC" and "Immune Design, a subsidiary of Merck & Co., Inc." stay separate. A known limitation (an organisation-alias table is future work). |
| D11.5 | **Countries** | API `locations[].country` as-is | The API names are already canonical. Aliases only matter for filters (Q7, D7.3). |
| D11.6 | **Investigators** | `overallOfficials[].name` (trial level) and `locations[].contacts[].name` with role `PRINCIPAL_INVESTIGATOR` / `SUB_INVESTIGATOR` (site level), with credentials removed ("John Smith, MD, PhD" -> "John Smith"), case-folded | Different people with the same name may merge, and one person may appear with different spellings. Documented. |
| D11.7 | **Sites** | `facility` + `city` + `country`, each trimmed and case-folded | Facility spellings vary across trials. Documented. |

## Revision during implementation (2026-10-24): anchor MeSH terms to drug interventions

Live data showed that a trial's intervention MeSH list also contains **non-drug terms** (e.g. NCT02506153: "Specimen Handling", "Magnetic Resonance Spectroscopy", "Introns", "CTLA-4 Antigen"). Using every MeSH term as a drug would put them in drug charts and networks.

**New rule:** each `DRUG` / `BIOLOGICAL` intervention takes the MeSH term that shares a word with its **name or other names** (e.g. TEW-7197 -> "vactosertib" through `otherNames`); without a match it keeps its cleaned name. Placebo is skipped. The citation cites both the MeSH term and the intervention name. Remaining limitation: MeSH can name one substance two ways ("aldesleukin", "Interleukin-2"), which then stay separate.

## Known limitation: MeSH terms are per trial, not per intervention

`interventionBrowseModule.meshes` lists terms for the **trial as a whole**. It doesn't say which intervention entry each term came from. For counting trials per drug this is fine. For an edge such as "sponsor ↔ drug", the citation shows both the MeSH term and the trial's raw intervention names, so a reader can check the link.

## Requirement links

P7-3 (real-world data), P4-4 (meaningful networks), P5-3 (exact excerpts: raw values kept), P3-11 (assumptions in meta).
