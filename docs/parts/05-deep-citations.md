# Part 5: Bonus - Deep Citations (Source Traceability)

## 1. Source text (verbatim)

> As a bonus, include **deep citations** from ClinicalTrials.gov to support the values shown in the visualization.
>
> What "deep citations" mean here:
>
> - Each visualized datum (e.g., a bar, time bucket, node/edge weight) includes references to the underlying trial records that contributed to it.
> - Each reference includes:
>   - `nct_id`
>   - an **exact text excerpt** from the API response (or a specific field/value) that supports the datum
>
> Example (illustrative only):
>
> ```json
> {
>   "phase": "Phase 3",
>   "trial_count": 41,
>   "citations": [
>     {
>       "nct_id": "NCT01234567",
>       "excerpt": "Phase 3 randomized study evaluating pembrolizumab..."
>     }
>   ]
> }
> ```
>
> This is intentionally challenging, implement as much as is reasonable in the time box.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P5-1 | BONUS | **Each** visualized datum carries references to the trial records that **contributed** to it. | "Each visualized datum ... includes references to the underlying trial records that contributed to it." |
| P5-1a | BONUS | This covers bars, time buckets, **node weights and edge weights**: every chart type, not just bars. | "(e.g., a bar, time bucket, node/edge weight)" |
| P5-2 | BONUS | Each reference has an `nct_id`. | "`nct_id`" |
| P5-3 | BONUS | Each reference has an **exact text excerpt** from the API response, **or a specific field/value**, that **supports** the datum. | "an exact text excerpt from the API response (or a specific field/value) that supports the datum" |
| P5-4 | BONUS | The citations live **inside the data row** (the example puts `citations` next to `phase` and `trial_count`). | example |
| P5-5 | (guidance) | It's meant to be hard. Do as much as is reasonable. | "intentionally challenging" |

## 3. What it really means

- "Exact" is the key word. The excerpt must be **copied verbatim** from the API response, never summarised or written by the LLM.
- "Supports the datum" means the excerpt must show **why** that trial counts toward that bar.
  - For the "Phase 3" bar, the best excerpt is the phase field value itself (`"PHASE3"`), ideally with the field path.
  - The title is also fine when it mentions the phase.
  - For a 2018 time bucket, the excerpt is the start date (`"2018-03-15"`).
  - For a sponsor <-> drug edge, the excerpts are the lead sponsor name **and** the intervention name.
- Getting this right is **by construction**: the code that puts a trial into a bucket also records which field value put it there. No second LLM pass and no matching after the fact.
- The bonus is a natural fit with "avoid hallucination" (Part 7): every number can be checked against records.

## 4. Ambiguities and proposed decisions

1. **Size.** A bar could cover 2,000 trials, and listing 2,000 citations in every bar would bloat the response.
   Proposed, per datum:
   - `citation_count`: the number of contributing trials, which always equals the value for count charts
   - `citations`: a capped list (e.g. the first N, sorted in a fixed order, so repeat runs match)
   - `citations_truncated: true/false`
   - the **full NCT ID list** available by one of these routes (decide in design):
     - (a) the full `nct_ids` array per datum, which is cheap (IDs are short)
     - (b) a follow-up endpoint `GET /runs/{run_id}/citations?datum=...`
   - Document the cap.
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
   - `field` plus `value` make it checkable by machine.
   - `excerpt` stays to match the PDF's key name.
   - `url` lets a human click through.
   - Optional: the brief title as context.
3. **Multi-field support.** Edges need **two** field excerpts (one per endpoint). Proposed: allow a list of `evidence` items per citation.
4. **Derived values** (like duration = completion - start). Cite both source fields.
5. **Non-count measures** (mean enrollment). Cite each trial's enrollment value.
6. **Is the excerpt really exact?** Proposed: a test that, for every citation in the example runs, reads the stored API record at `field` and asserts the value matches `value` / `excerpt`. This becomes evidence for the README's "how we validated correctness".

## 5. Acceptance checks

- [ ] Every datum in every chart type has `citations` (or a documented equivalent), including network nodes and edges.
- [ ] For count charts, `citation_count == value`.
- [ ] Automated check: each citation's excerpt is found verbatim at the stated field path in the raw API record.
- [ ] Citation lists are in a fixed order, so repeat runs match.
- [ ] README explains the citation model, the cap, and how to get full lists.
