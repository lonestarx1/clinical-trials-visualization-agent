# Part 5: Bonus: deep citations (source traceability)

## 1. Summary

As a bonus, the chart's values are backed by **deep citations** from ClinicalTrials.gov:

- every visualized datum (a bar, a time bucket, a node or edge weight) refers to the trial records that contributed to it;
- each reference gives the trial's `nct_id` and an **exact excerpt** from the API response (or a specific field and value) that supports the datum.

The brief's illustrative example puts a `citations` list, with `nct_id` and `excerpt` in each entry, inside the data row next to the category and its count. The brief calls this bonus deliberately hard, to be done as far as the time box allows.

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| P5-1 | BONUS | **Each** visualized datum carries references to the trial records that **contributed** to it. |
| P5-1a | BONUS | This covers bars, time buckets, **node weights and edge weights**: every chart type, not just bars. |
| P5-2 | BONUS | Each reference has an `nct_id`. |
| P5-3 | BONUS | Each reference has an **exact text excerpt** from the API response, **or a specific field and value**, that **supports** the datum. |
| P5-4 | BONUS | The citations live **inside the data row**, as in the brief's example. |
| P5-5 | (guidance) | It is meant to be hard. Do as much as is reasonable. |

## 3. What it means

- "Exact" is the key word. The excerpt must be **copied verbatim** from the API response, never summarised or written by the LLM.
- "Supports the datum" means the excerpt shows **why** that trial counts toward that value.
  - For the "Phase 3" bar, the best excerpt is the phase field value itself (`"PHASE3"`), with the field path.
  - The title also works when it mentions the phase.
  - For a 2018 time bucket, the excerpt is the start date (`"2018-03-15"`).
  - For a sponsor-drug edge, the excerpts are the lead sponsor name **and** the intervention name.
- Getting this right is **by construction**: the code that puts a trial into a bucket also records which field value put it there. There is no second LLM pass and no matching after the fact.
- The bonus fits naturally with "avoid hallucination" (Part 7): every number can be checked against records.

## 4. Ambiguities and decisions

The final citation model is in [design Q14](../design/14-citations.md): each citation is `{nct_id, url, title, evidence: [{field, excerpt}]}`, 5 citations are inlined per data point, the full list is paged through `GET /v1/results/{id}/citations`, a size-guarded `full` mode inlines everything, and the exactness check is always on. The first proposals:

1. **Size.** A bar can cover 2,000 trials, and listing 2,000 citations in every bar would bloat the response. Per datum:
   - `citation_count`: the number of contributing trials, which equals the value for count charts
   - `citations`: a capped list in a fixed order, so repeat runs match
   - `citations_truncated: true/false`
   - the **full NCT ID list**, either as (a) a full `nct_ids` array per datum, or (b) a follow-up endpoint. (Decided: (b), the paginated citations endpoint.)
   - The cap is documented.
2. **Excerpt format.** Proposed citation object:
   ```json
   {
     "nct_id": "NCT01234567",
     "field": "protocolSection.designModule.phases",
     "value": "PHASE3",
     "excerpt": "PHASE3",
     "url": "https://clinicaltrials.gov/study/NCT01234567"
   }
   ```
   - `field` makes it checkable by machine.
   - `excerpt` keeps the key name from the brief's example.
   - `url` lets a person click through.
   - The brief title adds context.
3. **Several fields per citation.** Edges need **two** field excerpts (one per endpoint), so each citation holds a list of `evidence` items. (Kept in the final model.)
4. **Derived values** (such as duration = completion date - start date): cite both source fields.
5. **Non-count measures** (such as mean enrollment): cite each trial's enrollment value.
6. **Is the excerpt really exact?** A check reads the stored API record at `field` and asserts that the excerpt matches. It is also evidence for how correctness was validated (Part 8).

## 5. Acceptance checks

- [ ] Every datum in every chart type has `citations` (or a documented equivalent), including network nodes and edges.
- [ ] For count charts, `citation_count` equals the value.
- [ ] Automated check: each citation's excerpt is found verbatim at the stated field path in the raw API record.
- [ ] Citation lists are in a fixed order, so repeat runs match.
- [ ] The README explains the citation model, the cap, and how to get the full lists.
