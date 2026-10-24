# Design Q7: Compiling plan filters into API searches

Status: **Decided** (2026-10-24). Based on live-probe findings (`docs/api/live-probe.md` §3).

## Filter -> API mapping

| Filter | Default (strict) | Optional broad mode | Evidence |
|---|---|---|---|
| Drug | `AREA[InterventionNameSearch]"x"`: InterventionName + InterventionOtherName, with UMLS synonyms | `query.intr="x"` (also titles, keywords, arm/intervention descriptions, MeSH ancestors) | pembrolizumab: strict 2,652 vs broad 2,993; 335 broad hits had no pembrolizumab intervention entry. Keytruda / MK-3475 resolve identically. |
| Condition | `query.cond="x"` (quoted; Condition + titles + MeSH + ancestors + keywords, with synonyms) | unquoted `query.cond=x` (Relaxation: words may match separately) | "lung cancer": quoted 13,423, unquoted 14,657, strict `AREA[Condition]` 10,676 (misses MeSH matches) |
| Sponsor, role = **lead** (default) | `query.lead="x"` (LeadSponsorName, contains-match, no synonyms) | role = **any**: `query.spons="x"` (lead + collaborators + org) | Merck: `query.spons` 5,240 vs exact lead name 2,191 |
| Country | `AREA[LocationCountry]"<canonical API name>"` | none | API names are clean English ("United States", "South Korea", "Turkey (Türkiye)") |
| Phase | `AREA[Phase](PHASE1 OR PHASE2)` | none | codes and labels both work; codes used |
| Status | `filter.overallStatus=RECRUITING\|...` (the **trial's overall status**) | none | "Recruiting" means overall status. Site-level status is missing on 65% of sites (live-probe §5), so it isn't used for filtering. For "countries with recruiting trials": trials with overall status RECRUITING, counted per country of their sites (Q9). |
| Start year range | `AREA[StartDate]RANGE[YYYY-01-01,YYYY-12-31]` | none | RANGE excludes studies with no start date; reported in `meta` |
| Other enum dimensions (sponsor class, study type, allocation, masking, purpose, sex, age group, ...) | `AREA[<Piece>]<CODE>` | none | |

## Rules

| # | Decision |
|---|---|
| D7.1 | **Code builds an expression tree (AST) and serialises it** to Essie syntax. No string concatenation. Every user term is a quoted, escaped literal node. This gives unit-testable compilation and **query-injection protection** (Q5). |
| D7.2 | **OR within a filter, AND across filters.** Each comparison group compiles to its **own** search (shared filters AND group filters). |
| D7.3 | **Country names are resolved by a deterministic lookup table in code** (aliases such as "USA", "US", "Korea", "UK", "Türkiye" -> the API's canonical name). Never the AI. The table is built from the API's real values. Unknown countries pass through as given and are flagged by the non-empty check (V3). |
| D7.4 | **The exact compiled API query is recorded in `meta`** (per group), so every result can be reproduced and cited. |
| D7.5 | **`match_mode`** (`strict` default \| `broad`) for drugs and conditions: a request field and a plan field; reported in `meta`. |
| D7.6 | **`sponsor_role`** (`lead` default \| `any`): a plan field and a request field (the request field overrides). The AI picks `any` only when the wording calls for it ("involving", "funded/supported by", "partnered with") and records why in `assumptions`. The sponsor ↔ collaborator network always uses both roles, explicitly. |

## Why lead sponsor by default

- On ClinicalTrials.gov, "sponsor" means the **lead sponsor**: the organisation responsible for the trial. Collaborators are partners or funders.
- Including collaborators silently changes the meaning: Merck is a **collaborator** on many academic pembrolizumab trials (typically as the drug supplier), so "Merck's trials" would mix Merck-run and academic trials.
- Sponsor-class dimensions (industry vs academic) already use the lead sponsor's class, so the default is consistent.

## Requirement links

P1-3 (retrieve relevant data), P2-2 (authoritative), P3-11 (filters applied in meta), P7-3 (real-world data), P7-8 (robustness).
