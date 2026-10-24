# Assignment Reference: ClinicalTrials.gov Query-to-Visualization Agent (Backend)

This file has two parts:

- **Part A** is a faithful transcription of Cheiron's instructions (from 6 screenshots received 2026-10-24 15:06 KST). Wording is kept as close to the original as possible. Treat it as the source of truth.
- **Part B** is our own analysis: what the spec implies, risks, and open questions. It is not from Cheiron.

Window: DocSend opened **Sat 2026-10-24 15:00 KST**. **Deadline: Sun 2026-10-25 15:00 KST** (submit with margin; late = not considered).

---

# Part A: The Instructions (transcribed)

**Time expectation:** ~24 hours
**Tools allowed:** Any programming language, libraries, AI tools, and internet access
**Primary goal:** Build a backend service that converts clinical-trial questions into **structured visualization outputs** backed by **ClinicalTrials.gov API** data.

## 1) Problem Overview

You will build an AI-enabled backend that answers questions about clinical trials using the **ClinicalTrials.gov API**. The user will provide a natural-language query, along with optional structured fields (which you may define). Your system must:

1. Interpret the user's question.
2. Retrieve relevant data from ClinicalTrials.gov.
3. Identify if a visualization is needed and what type of visualization is suitable for the given question.
4. Produce a **visualization specification** that answers the question.

A frontend is **not required**, but your output must be clear and structured so that a frontend can render the visualization reliably.

## 2) Data Source

Use the **ClinicalTrials.gov Data API** as the authoritative data source.

- API documentation: https://clinicaltrials.gov/data-api/api
- You may use any endpoints/fields needed.

## 3) Functional Requirements

### 3.1 Inputs

Your service must accept a request containing:

**Required**

- `query` (string): a natural language question about clinical trials.

**Optional structured fields (candidate-defined)**

You may define an input schema that includes additional parameters. Examples (not required):

- `drug_name`
- `condition/disease`
- `trial_phase`
- `sponsor`
- `country/location`
- `start_year`, `end_year`
- any other fields you find useful

**You must document your request schema** (field names, types, optional/required, validation).

An example request may look like:

```json
{
  "query": "How has the number of trials for this drug changed over time?",
  "drug_name": "Pembrolizumab"
}
```

### 3.2 Outputs

Your service must return a **structured response** describing a visualization.

**Required output components**

1. **Visualization specification**
   - `type`: the visualization type (e.g., `bar_chart`, `time_series`, `network_graph`, etc.)
   - `title`: a human-readable title
   - `encoding`: a clear mapping from fields to visual channels (e.g., x-axis, y-axis, series, nodes/edges)
   - `data`: the data points required to render the visualization
2. **Response metadata**
   - any additional fields needed for the frontend to render appropriately (units, sorting, time granularity, grouping choices, etc.)
   - optional notes about assumptions, filters applied, or query interpretation

**You must document your response schema** so that a frontend engineer can implement a renderer without guessing. If you build a simple frontend demo, that's a bonus, but **backend + structured outputs** are the focus.

Example response (illustrative only):

```json
{
  "visualization": {
    "type": "bar_chart",
    "title": "Trials by Phase for Pembrolizumab",
    "encoding": {
      "x": {"field": "phase"},
      "y": {"field": "trial_count"}
    },
    "data": [
      {"phase": "Phase 1", "trial_count": 32},
      {"phase": "Phase 2", "trial_count": 78}
    ]
  },
  "meta": {
    "filters": {"drug_name": "Pembrolizumab"},
    "source": "clinicaltrials.gov"
  }
}
```

## 4) Visualization Requirements

- The answer to the query must be a **visualization** (via structured specification).
- You may support any visualization types, but your system should aim to support **multiple** types, such as:
  - bar chart / grouped bar chart
  - timeline/time series
  - scatter plot
  - histogram
  - network graph (entities like drugs, sponsors, conditions, investigators, sites)

**Design goal:** Cover as many query types as possible with a **single coherent approach** and support **multiple visualization types**. Submissions that implement richer visualizations (e.g., meaningful network graphs) and broader query coverage will be scored higher than those that only support one chart type.

## 5) Bonus: Deep Citations (Source Traceability)

As a bonus, include **deep citations** from ClinicalTrials.gov to support the values shown in the visualization.

What "deep citations" mean here:

- Each visualized datum (e.g., a bar, time bucket, node/edge weight) includes references to the underlying trial records that contributed to it.
- Each reference includes:
  - `nct_id`
  - an **exact text excerpt** from the API response (or a specific field/value) that supports the datum

Example (illustrative only):

```json
{
  "phase": "Phase 3",
  "trial_count": 41,
  "citations": [
    {
      "nct_id": "NCT01234567",
      "excerpt": "Phase 3 randomized study evaluating pembrolizumab..."
    }
  ]
}
```

This is intentionally challenging, implement as much as is reasonable in the time box.

## 6) Submission Requirements

Submit a zip file containing:

1. **Code:** All source code required to run the service.
2. **README:** must include
   - how to run (install, configure, start)
   - request/response schema documentation (inputs/outputs)
   - key design decisions and tradeoffs
   - limitations and what you would improve with more time
3. **Example Runs:** Provide **3-5 example queries** with the **actual JSON outputs** produced by your system.
4. **(Optional) Demo**
   - a small UI
   - a deployed endpoint
   - a short demo video

## 7) Evaluation Criteria

We will evaluate submissions on:

1. **System Design (35%)**
   - clear, rational design decisions
   - maintainable structure and extensibility
   - sensible handling of real-world API data
2. **AI / Agent Design (20%)**
   - avoid hallucination-prone steps
   - include validation or constraints
   - Sensible planning and reasoning steps, along with appropriate tools
3. **Code Quality (20%)**
   - readability, organization, documentation
   - correctness and robustness
4. **Query and Visualization Coverage (15%)**
   - breadth of supported query types
   - ability to handle multiple question classes without one-off hacks
   - richer visualizations (e.g., meaningful network graphs) score higher than simple single-chart systems
5. **Input/Output Design (10%)**
   - well-structured, unambiguous schemas
   - frontend-friendly visualization specification

**Bonus consideration:** Deep citations/traceability to source records.

## 8) Integrity Note (Use AI Tools Freely)

You may use AI tools and online resources. We care about your **engineering judgment** and **design reasoning**.

In your README, briefly describe:

- which tools you used (if any)
- how you validated correctness
- what parts you designed/implemented deliberately vs generated and adapted

We reward submissions that show evidence of thoughtful construction, testing, and iteration.

## Appendix: Example Query Types (Non-Exhaustive)

You do not need to support all of these, but they illustrate the breadth we care about:

**Time trends**

- "How has the number of trials for *[drug]* changed per year since 2015?"
- "How many trials started each year for *[condition]*?"

**Distributions**

- "How are *[condition]* trials distributed across phases?"
- "What are the most common intervention types for *[drug/condition]* trials?"

**Comparisons**

- "Compare phases for trials involving *Drug A* vs *Drug B*."
- "Compare sponsor categories across two conditions."

**Geographic patterns**

- "Which countries have the most recruiting trials for *[condition]*?"

**Relationships/networks**

- "Show a network of sponsors <-> drugs for *[condition]* trials."
- "Which drugs frequently co-occur in combination studies (drug <-> drug network)?"

To repeat, these are just some example queries and visualization possible. You are not restricted to these in your assignment.

---

# Part B: Our Analysis (not from Cheiron)

## What the task really is

This is **not** a document-RAG task. It is a **text-to-analytics** task:

`NL query + optional fields -> query plan -> ClinicalTrials.gov API fetch -> aggregation -> typed visualization spec (+ citations)`

The "retrieval" is structured API search, not vector search. The answer is numbers in a chart, so the core risk is **wrong numbers**, not wrong prose.

## What scores points (by weight)

| Weight | Criterion | What it implies for us |
|---|---|---|
| 35% | System design | Clean pipeline stages, extensible registry of dimensions/chart types, robust handling of messy API data (pagination, partial dates, multi-valued fields). |
| 20% | AI / agent design | LLM only where needed (interpretation). Its output is a **schema-validated plan**, never numbers. Counts come from deterministic code. Validate the plan; repair or reject. |
| 20% | Code quality | Typed models, small modules, tests, clear docs. |
| 15% | Coverage | One generic engine (filters x group-by x chart type) covering all appendix classes, including network graphs. No per-question special cases. |
| 10% | I/O design | Discriminated-union response schema per chart type, documented field by field. |
| Bonus | Deep citations | Every datum lists contributing `nct_id`s plus the exact API field path and value. Citations are correct by construction because they come from the same records we aggregated. |

## Design principles we derive

1. **LLM plans, code computes.** The LLM maps the question to a constrained plan (filters, group-by dimension(s), chart type, time range). Enums limit its choices. Aggregation, counting and citations are deterministic.
2. **Structured fields win over the LLM.** If the request gives `drug_name`, it overrides whatever the LLM extracted. Conflicts are reported in `meta`.
3. **Every assumption is surfaced** in `meta` (interpretation, filters applied, records fetched vs total, truncation, how multi-valued fields were counted).
4. **Citations are an excerpt of real API data**, with the field path (e.g. `protocolSection.designModule.phases`) so they can be verified.
5. **Fail clearly**: unsupported question -> structured error or a best-effort chart with a note, never an invented chart.

## Real-world data issues to handle (verify against the API early)

- **Pagination and volume:** broad conditions return many thousands of studies. Need a cap, the API total count, and an honest "computed over N of M" note. Check whether the API's total count can be used for exact per-bucket counts.
- **Multi-valued fields:** a study can have several phases (e.g. Phase 1/Phase 2), conditions, interventions and countries. Decide and document the counting rule (one count per value vs per study).
- **Dates:** start dates can be partial (`YYYY-MM` or `YYYY`), missing, or "anticipated".
- **Entity names are messy:** the same drug appears as brand name, code name, or with dose text ("Pembrolizumab", "MK-3475", "Keytruda 200 mg"). Placebo should usually be excluded from drug networks. Normalization is a known limitation.
- **Enumerations:** phases (`PHASE1`, `EARLY_PHASE1`, `NA`), sponsor class (`INDUSTRY`, `NIH`, `OTHER`...), overall status (`RECRUITING`...). Map to display labels.
- **Rate limits and errors:** retries with backoff, timeouts, caching of API responses.

## Stack note

The task needs FastAPI, an HTTP client for the API, and an LLM. **pgvector is not needed** for the core task; adding it without a reason would hurt the "rational design" score. Postgres is still useful for caching API responses and logging each run (plan, API calls, timings) for traceability. Decide in the design step.

## Deliverables checklist

- [ ] Source code (zip)
- [ ] README: how to run, request schema, response schema, design decisions and tradeoffs, limitations and future work
- [ ] README: AI tool usage, how correctness was validated, designed vs generated parts (be honest)
- [ ] 3-5 example queries with **actual** JSON outputs (generated by the real system, saved to files)
- [ ] Tests
- [ ] Optional: small UI that renders the spec, deployed endpoint, short demo video

## Logistics (from Cheiron's email, 2026-10-24 12:50 KST)

- **The 24-hour window starts when the DocSend document is opened** (after entering the email), not at the booked slot time. Opened at 15:00 KST on 10/24, so the deadline is **Sun 10/25 15:00 KST**.
- **Submit at:** https://you.ashbyhq.com/Cheiron/assignment/593473ca-1a6c-4167-8c9c-905a36f54cbe. A file or a GitHub link both work. Late submissions are not considered.
- **Plan (decided in design Q19):** zip of the repository + deployed endpoint `https://api.engineeradriel.com` + Vercel frontend. Developed in a git repo (personal account).
- **LLM:** OpenAI key provided by Cheiron. Allowed models: gpt-4o-mini, gpt-4o-2024-08-06, gpt-4.1-nano, gpt-4.1-mini, gpt-4.1, gpt-5-mini, gpt-5, gpt-5.1, gpt-5.2, gpt-5.4-nano, gpt-5.4-mini, gpt-5.4. (Tested 2026-10-24: all work except **gpt-4.1-nano, which OpenAI has retired** (404).)
