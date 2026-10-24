# Part 3: Functional requirements (3.1 inputs, 3.2 outputs)

## 1. Summary

### 3.1 Inputs

- **Required:** `query`, a string holding a natural-language question about clinical trials.
- **Optional:** structured fields that we define. The brief suggests a drug name (`drug_name`), condition or disease, trial phase (`trial_phase`), sponsor, country or location, and a year range (`start_year`, `end_year`). These are examples, not required names, and other fields are welcome.
- The request schema must be documented: field names, types, which fields are required, and the validation rules.
- The brief's example request asks how trial counts for "this drug" changed over time, with the drug (pembrolizumab) given only in `drug_name`.

### 3.2 Outputs

The service returns a structured response that describes a visualization, with two required parts:

1. **Visualization specification:** `type` (the chart type, e.g. `bar_chart`, `time_series`, `network_graph`), a human-readable `title`, an `encoding` that maps data fields to visual channels (x and y axes, series, nodes and edges), and the `data` points needed to draw it.
2. **Response metadata:** anything else the frontend needs to render correctly (units, sort order, time granularity, grouping), plus optional notes on assumptions, filters applied and how the question was interpreted.

The response schema must be documented well enough that a frontend engineer can build a renderer without guessing. A simple frontend demo is a bonus; the backend and its structured output are the focus.

The brief's illustrative response, marked as an example only, has a top-level `visualization` object (type, title, an encoding with `x` and `y` fields, and flat data rows such as one row per phase with a trial count) and a top-level `meta` object (the filters applied and the data source).

## 2. Atomic requirements

### Inputs

| ID | Level | Requirement |
|---|---|---|
| P3-1 | MUST | Accept `query`, a **string** and **required**: a natural-language question about clinical trials. |
| P3-2 | MAY | Define optional structured fields. The suggested names are examples, not fixed. |
| P3-2a | MAY | Suggested fields: `drug_name`, condition or disease, `trial_phase`, `sponsor`, country or location, `start_year`, `end_year`, and others. |
| P3-3 | MUST | **Document the request schema** with all four of: **field names, types, optional or required, validation rules**. |
| P3-4 | SHOULD | The brief's example request (a "this drug" question plus `drug_name`) works as given. It is the most likely first test. |

### Outputs

| ID | Level | Requirement |
|---|---|---|
| P3-5 | MUST | Return a **structured response** that describes a visualization. |
| P3-6 | MUST | The visualization spec has `type`. |
| P3-7 | MUST | The visualization spec has a **human-readable** `title`. |
| P3-8 | MUST | The visualization spec has `encoding`, a **clear mapping from data fields to visual channels**: x, y, series, and **nodes and edges** for graphs. |
| P3-9 | MUST | The visualization spec has `data`, with **all** the data points needed to render. The frontend must not need another call. |
| P3-10 | MUST | **Response metadata** with anything the frontend needs to render properly: **units, sorting, time granularity, grouping choices**, and so on. |
| P3-11 | MAY (treated as required) | Notes on **assumptions, filters applied and query interpretation**. The brief marks them optional, but they directly serve "avoid hallucination" and "sensible handling" in Part 7, so we treat them as required. |
| P3-12 | MUST | **Document the response schema** so a frontend engineer can build a renderer **without guessing**. |
| P3-13 | BONUS | A simple frontend demo. |
| P3-14 | (focus) | The focus is the **backend and structured outputs**. The UI must not take time away from them. |

## 3. What it means

- Structured fields aren't decoration. They let a frontend send exact filters, without relying on the LLM to read them from text. **Structured fields take priority over what the LLM extracts.**
- "Without guessing" is a high bar. A frontend developer must be able to tell, **from the schema alone**:
  - which field in each data row is x, y and series
  - what type each field is (category, number or date)
  - what unit the value has
  - the sort order
  - the time granularity
  - how to tell node rows from edge rows
- That points to a **typed schema with one variant per chart type**: `type` determines exactly which `encoding` keys and `data` shape follow. FastAPI publishes it as JSON Schema and OpenAPI.
- The brief's example uses a **top-level `visualization` and `meta`**, with **flat data rows** whose keys are named in `encoding`. Following that shape makes the output familiar to anyone who has read the brief. The example has no units, sort order or granularity, which 3.2 asks the metadata to include, so we add them.

## 4. Ambiguities and decisions

The final request schema is in [design Q5](../design/05-request-fields.md), the response schema in [Q12](../design/12-io-schema.md), and errors in [Q17](../design/17-error-handling.md). The first proposals:

1. **Field names.**
   - condition or disease -> `condition`
   - country or location -> `country`
   - `trial_phase` -> a list of phase enum values
   - Any aliases are documented.
2. **Several values for comparisons.** "Drug A vs drug B" needs two drugs. Either a `compare` field (a list of 2 or more groups), or the LLM extracts the comparison from the query. Both routes are documented. (Built: `compare` holds 2 to 4 groups.)
3. **Conflicts between the query and the fields.** Example: the query says "lung cancer" but `condition` is "breast cancer". The structured field wins, and a warning is added to `meta`.
4. **Validation rules to document:**
   - `query` length between 1 and N characters, not blank
   - years are integers in a sensible range, and `start_year <= end_year`
   - phase values come from a fixed enum
   - unknown fields are rejected (strict)
5. **Where units, sort order and granularity go.** The brief lists them under response metadata, but they are rendering instructions. **Decided (Q12):** keep the example's top-level shape, and put the render hints on each channel in `encoding` (`unit`, `sort`, `time_unit`), with the sort order also summarised in `meta`.
6. **Errors.** The brief doesn't mention them, but a renderer needs to know the error shape. **Decided (Q17):**
   - invalid input returns 422
   - out-of-scope questions and empty results return 200 with `visualization: null`, a `status` and a message
   - an upstream API failure returns 503, with one structured error body for every error

## 5. Acceptance checks

- [ ] The request schema doc lists every field with its name, type, whether it is required, and its validation, generated from or checked against the code's model.
- [ ] The response schema doc covers every chart type with a complete example, and links a JSON Schema file or OpenAPI page.
- [ ] The brief's example request works and returns a time series.
- [ ] Contract tests: every response validates against the published schema.
- [ ] A test shows that a structured field overrides a conflicting query, with the warning present in `meta`.
- [ ] Bad input (empty query, `start_year > end_year`, unknown phase) returns a clear 422.
