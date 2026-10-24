# Assignment summary: ClinicalTrials.gov query-to-visualization agent (backend)

This project is a take-home exercise set by Cheiron. The original brief is confidential, so this repository does not reproduce it. This file has two parts:

- **Part A** summarizes the brief in our own words: what the service must do, its inputs and outputs, the chart types, citations, deliverables and evaluation focus. Section numbers follow the brief, so other docs can refer to them (e.g. "3.2").
- **Part B** is our own analysis: what the brief implies, the risks, and the principles we derived.

Each requirement is broken down further, with an ID such as `P3-12`, in [`parts/`](parts/README.md). How the design covers each ID is in [`design/requirements-coverage.md`](design/requirements-coverage.md).

---

# Part A: What the brief asks for (summary)

**Goal:** a backend service that turns questions about clinical trials into **structured visualization outputs**, computed from **ClinicalTrials.gov API** data.

**Time box:** about 24 hours. Any language, library, AI tool or online resource is allowed.

## 1) Problem overview

The service is AI-enabled. It receives a natural-language question, optionally with structured fields that we define, and must:

1. interpret the question;
2. retrieve the relevant data from ClinicalTrials.gov;
3. decide whether a visualization is needed, and which type suits the question;
4. return a visualization specification that answers the question.

A frontend is not required. The output must be structured clearly enough that a frontend can render it reliably.

## 2) Data source

The [ClinicalTrials.gov Data API](https://clinicaltrials.gov/data-api/api) is the authoritative source of data. Any of its endpoints and fields may be used.

## 3) Functional requirements

### 3.1 Inputs

- **Required:** `query`, a string holding a natural-language question about clinical trials.
- **Optional:** structured fields of our own design. The brief suggests fields such as a drug name (`drug_name`), condition or disease, trial phase (`trial_phase`), sponsor, country or location, and a year range (`start_year`, `end_year`), and leaves room for others.
- The request schema must be documented: field names, types, which fields are required, and the validation rules.
- The brief's example request asks how trial counts for "this drug" changed over time, and names the drug (pembrolizumab) only in `drug_name`. The service has to combine the two.

### 3.2 Outputs

The response is structured and describes a visualization. It has two required parts:

1. **Visualization specification**
   - `type`: the chart type (for example `bar_chart`, `time_series`, `network_graph`);
   - `title`: a human-readable title;
   - `encoding`: which data fields map to which visual channels (x and y axes, series, nodes and edges);
   - `data`: the data points needed to draw the chart.
2. **Response metadata:** anything else the frontend needs to render correctly (units, sort order, time granularity, grouping), plus optional notes on assumptions, filters applied and how the question was interpreted.

The response schema must be documented well enough that a frontend engineer can build a renderer without guessing. A simple frontend demo earns a bonus, but the backend and its structured output are the focus.

The brief's illustrative response has a top-level `visualization` object (type, title, an encoding with `x` and `y` fields, and flat data rows such as one row per phase with a trial count) and a top-level `meta` object (the filters applied and the data source).

## 4) Visualization requirements

- The answer to a question is a visualization, given as a structured specification.
- Any chart types may be supported, but the service should support **several**, for example: bar and grouped bar charts, time series or timelines, scatter plots, histograms, and network graphs of entities such as drugs, sponsors, conditions, investigators and sites.
- **Design goal:** cover as many kinds of question as possible with **one coherent approach**. Richer visualizations (meaningful network graphs in particular) and broader coverage score higher than a single chart type.

## 5) Bonus: deep citations

Citations from ClinicalTrials.gov that support the values in the chart:

- every visualized datum (a bar, a time bucket, a node or edge weight) refers to the trial records that contributed to it;
- each reference gives the trial's `nct_id` and an exact excerpt from the API response (or a specific field and value) that supports the datum.

The brief's illustrative example puts a `citations` list (`nct_id` plus `excerpt`) inside each data row. It describes this bonus as deliberately hard, to be done as far as the time box allows.

## 6) Deliverables

1. **Code:** all source code needed to run the service, submitted as an archive or a repository link.
2. **README** covering how to run it (install, configure, start), the request and response schemas, the key design decisions and trade-offs, and the limitations and future improvements.
3. **Example runs:** 3 to 5 example questions with the actual JSON the system returned.
4. **Optional demo:** a small UI, a deployed endpoint, or a short video.

## 7) Evaluation focus

| Weight | Area | What is assessed |
|---|---|---|
| 35% | System design | Clear, reasoned decisions; maintainable and extensible structure; sensible handling of real-world API data |
| 20% | AI / agent design | Avoiding steps prone to hallucination; validation and constraints; sensible planning and appropriate tools |
| 20% | Code quality | Readability, organization and documentation; correctness and robustness |
| 15% | Query and visualization coverage | Range of question types; handling many question classes without one-off hacks; richer visualizations such as meaningful network graphs |
| 10% | Input/output design | Well-structured, unambiguous schemas; a frontend-friendly visualization specification |
| Bonus | Deep citations | Traceability to the source records |

## 8) Tool-use disclosure

AI tools and online resources are allowed; the assessment is about engineering judgment and design reasoning. The README should briefly say which tools were used, how correctness was validated, and which parts were designed or written deliberately versus generated and then adapted. Evidence of careful construction, testing and iteration is rewarded. Our disclosure: [`parts/08-integrity-note.md`](parts/08-integrity-note.md).

## Appendix: example question classes

The brief lists example questions to show the range it has in mind. They are not a required list, and other questions are welcome. Paraphrased:

| Class | Example questions |
|---|---|
| Time trends | Trials for a given drug per year since 2015; trials started per year for a given condition |
| Distributions | A condition's trials by phase; the most common intervention types for a drug or condition |
| Comparisons | Phases of drug A vs drug B; sponsor categories across two conditions |
| Geographic patterns | Countries with the most recruiting trials for a condition |
| Relationships and networks | A sponsor-drug network for a condition; drugs that often appear together in combination studies (drug-drug network) |

---

# Part B: Our analysis

## What the task is

This is **not** a document-retrieval (RAG) task. It is a **text-to-analytics** task:

`NL query + optional fields -> query plan -> ClinicalTrials.gov API fetch -> aggregation -> typed visualization spec (+ citations)`

Retrieval is a structured API search, not a vector search. The answer is numbers in a chart, so the main risk is **wrong numbers**, not wrong prose.

## How the weights shape the design

| Weight | Criterion | What it implies |
|---|---|---|
| 35% | System design | Clean pipeline stages, an extensible registry of dimensions and chart types, and robust handling of messy API data (pagination, partial dates, multi-valued fields). |
| 20% | AI / agent design | The LLM is used only where it is needed (interpretation). Its output is a **schema-validated plan**, never numbers. Counts come from deterministic code. The plan is validated, then repaired or rejected. |
| 20% | Code quality | Typed models, small modules, tests, clear docs. |
| 15% | Coverage | One generic engine (filters x group-by x chart type) that covers every appendix class, including network graphs. No per-question special cases. |
| 10% | I/O design | A response schema with one variant per chart type, documented field by field. |
| Bonus | Deep citations | Every datum lists the contributing `nct_id`s with the exact API field path and value. The citations are correct by construction, because they come from the same records we aggregated. |

## Design principles

1. **The LLM plans, code computes.** The LLM maps the question to a constrained plan (filters, group-by dimensions, chart type, time range), choosing from enums. Aggregation, counting and citations are deterministic.
2. **Structured fields win over the LLM.** If the request gives `drug_name`, it overrides whatever the LLM extracted. Conflicts are reported in `meta`.
3. **Every assumption is surfaced** in `meta`: the interpretation, filters applied, records fetched vs total, truncation, and how multi-valued fields were counted.
4. **Citations are excerpts of real API data**, with the field path (e.g. `protocolSection.designModule.phases`) so they can be checked.
5. **Fail clearly.** An unsupported question gets a structured error or a best-effort chart with a note, never an invented chart.

## Real-world data issues

These were checked against the live API; the findings are in [`api/live-probe.md`](api/live-probe.md) and [`api/contract.md`](api/contract.md).

- **Pagination and volume:** broad conditions match many thousands of studies. The service needs exact per-bucket counts, the API's total count, and an honest note on what was computed. (Resolved: answers are exact, computed from the live API at request time; see [design Q6](design/06-retrieval.md).)
- **Multi-valued fields:** one study can have several phases (e.g. Phase 1/Phase 2), conditions, interventions and countries, so the counting rule must be chosen and documented ([design Q9](design/09-counting-rules.md)).
- **Dates:** start dates can be partial (`YYYY-MM` or `YYYY`), missing, or estimated ([design Q10](design/10-missing-partial-estimated.md)).
- **Messy entity names:** the same drug appears as a brand name, a code name, or with dose text ("Pembrolizumab", "MK-3475", "Keytruda 200 mg"). Placebo should usually be left out of drug networks ([design Q11](design/11-name-normalization.md)).
- **Enumerations:** phases (`PHASE1`, `EARLY_PHASE1`, `NA`), sponsor class (`INDUSTRY`, `NIH`, `OTHER`, ...), overall status (`RECRUITING`, ...) need display labels.
- **Rate limits and errors:** retries with backoff, timeouts, and caching of API responses ([design Q8](design/08-cache-ratelimit-retries.md)).

## Stack note

The task needs a web framework (FastAPI), an HTTP client for the API, and an LLM. A vector store such as pgvector is **not** needed for the core task, and adding one without a reason would weaken the design. Postgres is still useful for caching and for storing each result with its citations. The stack is decided in [design Q15](design/15-code-structure-stack.md) and the database in [design Q16](design/16-database.md).

## Deliverables and where to find them

| Deliverable | Where |
|---|---|
| Source code | [`backend/`](../backend), [`frontend/`](../frontend), [`infra/`](../infra) |
| How to run, schemas, design decisions, limitations | The [README](../README.md); the interactive OpenAPI reference is served at `/docs` |
| Tool-use disclosure | [`parts/08-integrity-note.md`](parts/08-integrity-note.md) |
| Example runs (actual JSON outputs) | [`examples/`](examples) |
| Tests | The README's "Testing and validation" section |
| UI and deployed endpoint | Web app at https://trials.cheiron.engineeradriel.com, API at https://api.cheiron.engineeradriel.com ([design Q19](design/19-deployment-ui.md), "Revision (2026-10-25)") |

## Exercise constraints

- **Models.** The OpenAI models available for the exercise were gpt-4o-mini, gpt-4o-2024-08-06, gpt-4.1-nano, gpt-4.1-mini, gpt-4.1, gpt-5-mini, gpt-5, gpt-5.1, gpt-5.2, gpt-5.4-nano, gpt-5.4-mini and gpt-5.4. When tested on 2026-10-24 all of them worked except gpt-4.1-nano, which OpenAI has retired (404). The models each AI stage uses are chosen in [design Q20](design/20-model-selection.md).
- **Delivery.** Design Q19 first planned an API at `api.engineeradriel.com` with the frontend on Vercel. That plan was replaced on 2026-10-25: the web app and API both run on Kubernetes (k3s) on one EC2 instance, at the URLs above (see [design Q19](design/19-deployment-ui.md), "Revision (2026-10-25)").
