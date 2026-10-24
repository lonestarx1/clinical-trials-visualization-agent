# Part 0: Preamble (document header)

This header comes before Part 1. It isn't numbered, but it sets the overall goal, so we break it down too.

## 1. Source text (verbatim)

> **Take-Home Assignment: ClinicalTrials.gov Query-to-Visualization Agent (Backend)**
>
> **Time expectation:** ~24 hours
> **Tools allowed:** Any programming language, libraries, AI tools, and internet access
> **Primary goal:** Build a backend service that converts clinical-trial questions into **structured visualization outputs** backed by **ClinicalTrials.gov API** data.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P0-1 | MUST | Build a **backend service** that turns clinical-trial questions into **structured visualization outputs**. | "Build a backend service that converts clinical-trial questions into structured visualization outputs" |
| P0-2 | MUST | The outputs are **backed by ClinicalTrials.gov API data**: the data comes from the API at request time (or from a cache of it), not from the LLM. | "backed by ClinicalTrials.gov API data" |
| P0-3 | SHOULD | Scope must be finishable in about 24 hours. | "Time expectation: ~24 hours" |
| P0-4 | MAY | Any language, library, AI tool, and the internet are allowed. | "Tools allowed: Any..." |

## 3. What it really means

- The title says **"Agent"** and **"(Backend)"**. They expect an AI component that plans and calls tools, but the deliverable is an API, not a UI.
- "Query-to-Visualization" is the whole contract: **text in, chart spec out**. Not prose answers, not a chatbot.
- "Structured" signals that the output must be machine-readable and stable (a schema), not free-form LLM JSON.

## 4. Ambiguities and proposed decisions

- **What "agent" means.** It could be a free-running tool loop (the LLM decides each step) or a fixed pipeline with an LLM planning step.
  - **Proposed:** a fixed pipeline where the LLM's only job is to produce a schema-checked plan. Plain code fetches the data, counts it and builds the chart, so the steps are easy to test and follow.
  - A free-running loop is more hallucination-prone, and Part 7 explicitly penalizes "hallucination-prone steps".
  - We can still call the planner's choices "tools" (search, aggregate, build chart), so the design stays explainable as an agent.
- **Language/stack.** Free choice. **Proposed:** Python + FastAPI, which matches Cheiron's job posting.

## 5. Acceptance checks

- [ ] `POST` an NL question to the running service and get back a structured visualization JSON.
- [ ] Every number in the output can be traced to ClinicalTrials.gov API records (see Part 5).
- [ ] The work fits the window: deadline Sun 2026-10-25 15:00 KST.
