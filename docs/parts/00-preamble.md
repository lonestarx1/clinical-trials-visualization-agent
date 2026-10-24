# Part 0: Preamble (goal and time box)

The brief opens with an unnumbered header that sets the overall goal. It isn't a numbered part, but we break it down too.

## 1. Summary

The brief asks for a **backend service** that turns questions about clinical trials into **structured visualization outputs**, with the data coming from the **ClinicalTrials.gov API**. The expected effort is about 24 hours. Any programming language, library, AI tool and internet resource may be used.

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| P0-1 | MUST | Build a **backend service** that turns clinical-trial questions into **structured visualization outputs**. |
| P0-2 | MUST | The outputs are **backed by ClinicalTrials.gov API data**: the data comes from the API at request time (or from a cache of it), not from the LLM. |
| P0-3 | SHOULD | The scope fits a time box of about 24 hours. |
| P0-4 | MAY | Any language, library, AI tool and internet resource is allowed. |

## 3. What it means

- The title calls the service an **agent** and a **backend**. An AI component that plans and calls tools is expected, but the deliverable is an API, not a UI.
- "Query to visualization" is the whole contract: **text in, chart spec out**. Not prose answers, not a chatbot.
- "Structured" means the output must be machine-readable and stable (a schema), not free-form LLM JSON.

## 4. Ambiguities and decisions

- **What "agent" means.** It could be a free-running tool loop (the LLM decides each step) or a fixed pipeline with an LLM planning step.
  - **Decision:** a fixed pipeline where the LLM's only job is to produce a schema-checked plan. Plain code fetches the data, counts it and builds the chart, so every step is easy to test and follow.
  - A free-running loop is more prone to hallucination, which the evaluation criteria (Part 7) count against.
  - The planner still uses tools (list options, check the plan, count trials), so the design is an agent in a bounded form. See [design Q2](../design/02-pipeline.md) and [Q3](../design/03-ai-vs-code.md).
- **Language and stack.** Free choice. **Decision:** Python and FastAPI ([design Q15](../design/15-code-structure-stack.md)).

## 5. Acceptance checks

- [ ] `POST` a natural-language question to the running service and get back a structured visualization JSON.
- [ ] Every number in the output can be traced to ClinicalTrials.gov API records (see Part 5).
- [ ] The scope fits the time box: core pipeline first, bonuses after (see the [implementation plan](../implementation-plan.md)).
