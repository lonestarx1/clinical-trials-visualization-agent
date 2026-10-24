# Part 3: Functional Requirements (3.1 Inputs, 3.2 Outputs)

## 1. Source text (verbatim)

### 3.1 Inputs

> Your service must accept a request containing:
>
> **Required**
>
> - `query` (string): a natural language question about clinical trials.
>
> **Optional structured fields (candidate-defined)**
>
> You may define an input schema that includes additional parameters. Examples (not required):
>
> - `drug_name`
> - `condition/disease`
> - `trial_phase`
> - `sponsor`
> - `country/location`
> - `start_year`, `end_year`
> - any other fields you find useful
>
> **You must document your request schema** (field names, types, optional/required, validation).
>
> An example request may look like:
>
> ```json
> {
>   "query": "How has the number of trials for this drug changed over time?",
>   "drug_name": "Pembrolizumab"
> }
> ```

### 3.2 Outputs

> Your service must return a **structured response** describing a visualization.
>
> **Required output components**
>
> 1. **Visualization specification**
>    - `type`: the visualization type (e.g., `bar_chart`, `time_series`, `network_graph`, etc.)
>    - `title`: a human-readable title
>    - `encoding`: a clear mapping from fields to visual channels (e.g., x-axis, y-axis, series, nodes/edges)
>    - `data`: the data points required to render the visualization
> 2. **Response metadata**
>    - any additional fields needed for the frontend to render appropriately (units, sorting, time granularity, grouping choices, etc.)
>    - optional notes about assumptions, filters applied, or query interpretation
>
> **You must document your response schema** so that a frontend engineer can implement a renderer without guessing. If you build a simple frontend demo, that's a bonus, but **backend + structured outputs** are the focus.
>
> Example response (illustrative only):
>
> ```json
> {
>   "visualization": {
>     "type": "bar_chart",
>     "title": "Trials by Phase for Pembrolizumab",
>     "encoding": {
>       "x": {"field": "phase"},
>       "y": {"field": "trial_count"}
>     },
>     "data": [
>       {"phase": "Phase 1", "trial_count": 32},
>       {"phase": "Phase 2", "trial_count": 78}
>     ]
>   },
>   "meta": {
>     "filters": {"drug_name": "Pembrolizumab"},
>     "source": "clinicaltrials.gov"
>   }
> }
> ```

## 2. Atomic requirements

### Inputs

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P3-1 | MUST | Accept `query`, a **string** and **required**. It's a natural-language question about clinical trials. | "`query` (string): a natural language question" |
| P3-2 | MAY | Define optional structured fields. Their names are suggested, not fixed. | "candidate-defined", "Examples (not required)" |
| P3-2a | MAY | Suggested fields: `drug_name`, condition/disease, `trial_phase`, `sponsor`, country/location, `start_year`, `end_year`, and others. | list |
| P3-3 | MUST | **Document the request schema**, with all four of: **field names, types, optional/required, validation rules**. | "You must document your request schema (field names, types, optional/required, validation)" |
| P3-4 | SHOULD | The given example request (query with "this drug" + `drug_name`) must work. Graders will likely try it first. | example |

### Outputs

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P3-5 | MUST | Return a **structured response** that describes a visualization. | "Your service must return a structured response describing a visualization." |
| P3-6 | MUST | Visualization spec has `type`. | "`type`: the visualization type" |
| P3-7 | MUST | Visualization spec has `title`, which is **human-readable**. | "`title`: a human-readable title" |
| P3-8 | MUST | Visualization spec has `encoding`, a **clear mapping from data fields to visual channels**: x, y, series, and **nodes/edges** for graphs. | "`encoding`: a clear mapping from fields to visual channels" |
| P3-9 | MUST | Visualization spec has `data`, containing **all** data points needed to render. The frontend must not need another call. | "`data`: the data points required to render the visualization" |
| P3-10 | MUST | **Response metadata** with anything the frontend needs to render properly: **units, sorting, time granularity, grouping choices**, etc. | "Response metadata - any additional fields needed for the frontend to render appropriately" |
| P3-11 | MAY (graded) | Notes on **assumptions, filters applied, query interpretation**. Labelled "optional", but it directly serves "avoid hallucination" and "sensible handling" in Part 7, so we treat it as required. | "optional notes about assumptions, filters applied, or query interpretation" |
| P3-12 | MUST | **Document the response schema** so a frontend engineer can build a renderer **without guessing**. | "You must document your response schema so that a frontend engineer can implement a renderer without guessing." |
| P3-13 | BONUS | A simple frontend demo. | "If you build a simple frontend demo, that's a bonus" |
| P3-14 | (focus) | The focus is **backend + structured outputs**. Don't let the UI take time from them. | "backend + structured outputs are the focus" |

## 3. What it really means

- Structured fields aren't decoration. They let a frontend send exact filters, without relying on the LLM to read them from text. **Structured fields should take priority over what the LLM extracts.**
- "Without guessing" is a high bar. The frontend dev must be able to tell, **from the schema alone**:
  - which field in each data row is x, y and series
  - what type each field is (category / number / date)
  - what unit the value has
  - the sort order
  - the time granularity
  - how to tell node rows from edge rows
- That points to a **typed schema with a variant per chart type**: `type` determines exactly which `encoding` keys and `data` shape follow. FastAPI can publish this as JSON Schema / OpenAPI automatically.
- The example uses **top-level `visualization` + `meta`**, and the data rows are **flat records** whose keys are named in `encoding`. Following that shape makes our output immediately familiar to the grader. The illustrative example has no `units`, `sort` or granularity, which 3.2 says the metadata should include. We add them.

## 4. Ambiguities and proposed decisions

1. **Field names.**
   - `condition/disease` -> `condition`
   - `country/location` -> `country` (plus maybe `location` free text)
   - `trial_phase` -> `trial_phase`, an enum list or single value
   - We document any aliases.
2. **Multiple values for comparisons.** "Drug A vs Drug B" needs two drugs. Proposed: either a `compare` field (a list of 2+ values plus the dimension to compare on), or let the LLM extract the comparison from the query. Document both routes.
3. **Conflicts between query and fields.** Example: the query says "lung cancer", but `condition` = "breast cancer". Proposed: the structured field wins, and a warning is added to `meta`.
4. **Validation rules to document:**
   - `query` length between 1 and N characters, not blank
   - years are integers in a sensible range, and `start_year <= end_year`
   - phase values come from a fixed enum
   - unknown fields are rejected (strict)
   - maybe an optional `max_records` cap, with limits
5. **Where units/sort/granularity go.** The text puts them under "Response metadata", but they are render instructions. Proposed: keep the example's top-level shape. Put render hints inside `visualization` next to `encoding` (e.g. `encoding.y.unit`, `encoding.x.sort`, `encoding.x.time_unit`), and also summarise them in `meta`. The final placement is decided in the schema design step. Either way, it must be documented.
6. **Errors.** Not mentioned, but a renderer needs to know the error shape. Proposed:
   - validation errors use FastAPI's standard 422
   - unsupported or empty results return 200 with `visualization: null`, a `meta.status`, and a message
   - upstream API failure returns 502 or 503 with a structured error body

## 5. Acceptance checks

- [ ] Request schema doc lists every field with name, type, required/optional, and validation, generated from or checked against the code's model.
- [ ] Response schema doc covers every chart type with a complete example. A JSON Schema file or OpenAPI page is linked.
- [ ] The exact example request from the PDF works and returns a time series.
- [ ] Contract tests: every response validates against the published schema.
- [ ] A test shows the structured field overrides a conflicting query, with the warning present in `meta`.
- [ ] Bad input (empty query, `start_year > end_year`, unknown phase) returns a clear 422.
