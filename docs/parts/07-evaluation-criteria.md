# Part 7: Evaluation Criteria

## 1. Source text (verbatim)

> We will evaluate submissions on:
>
> 1. **System Design (35%)**
>    - clear, rational design decisions
>    - maintainable structure and extensibility
>    - sensible handling of real-world API data
> 2. **AI / Agent Design (20%)**
>    - avoid hallucination-prone steps
>    - include validation or constraints
>    - Sensible planning and reasoning steps, along with appropriate tools
> 3. **Code Quality (20%)**
>    - readability, organization, documentation
>    - correctness and robustness
> 4. **Query and Visualization Coverage (15%)**
>    - breadth of supported query types
>    - ability to handle multiple question classes without one-off hacks
>    - richer visualizations (e.g., meaningful network graphs) score higher than simple single-chart systems
> 5. **Input/Output Design (10%)**
>    - well-structured, unambiguous schemas
>    - frontend-friendly visualization specification
>
> **Bonus consideration:** Deep citations/traceability to source records.

## 2. Atomic criteria and how we earn each

| ID | Weight | Criterion | How we earn it (proposal) | Evidence a grader will see |
|---|---|---|---|---|
| P7-1 | 35% | Clear, rational design decisions | Each major choice is written down with alternatives and why we picked it. | README "Design decisions" section; `docs/` notes |
| P7-2 | 35% | Maintainable structure and extensibility | Separate modules: API client, planner, query builder, aggregator, chart builder, schemas. Dimension and chart registries. | Folder layout; "how to add a dimension" in README |
| P7-3 | 35% | Sensible handling of real-world API data | Pagination, caps, the total count, multi-valued fields, partial dates, missing values, name normalisation, retries/backoff, caching. Each one is surfaced in `meta`. | `docs/api-notes.md`; tests with real API fixtures; `meta` notes |
| P7-4 | 20% | Avoid hallucination-prone steps | The LLM never produces numbers, data or citations. It only produces a plan. Data and citations come from code over API records. | Architecture diagram; tests |
| P7-5 | 20% | Validation or constraints | The plan is a strict JSON schema with enums, checked with Pydantic, then a semantic check (e.g. chart type fits the dimensions) plus a repair/retry loop. Structured fields override the LLM. | Planner code; tests for invalid plans |
| P7-6 | 20% | Sensible planning/reasoning steps + appropriate tools | Clear stages: interpret -> plan -> retrieve -> aggregate -> build chart -> check. The interpretation is recorded in `meta`. The LLM is used only where language understanding is needed. | Trace in `meta` / logs |
| P7-7 | 20% | Readability, organization, documentation | Typed Python, small functions, docstrings where they help, consistent naming. | Code |
| P7-8 | 20% | Correctness and robustness | Unit tests (aggregation, date parsing, normalisation), contract tests (schema), integration tests (API fixtures), error handling, timeouts. | `tests/`; CI badge if time |
| P7-9 | 15% | Breadth of query types | All 5 appendix classes (time trend, distribution, comparison, geographic, network) plus numeric (histogram/scatter). | `examples/`; test matrix |
| P7-10 | 15% | Multiple question classes without one-off hacks | One generic engine; no `if "network" in query` branches. | Code review |
| P7-11 | 15% | Richer visualizations, meaningful networks | Typed, weighted, pruned network graphs with citations. | Network example |
| P7-12 | 10% | Well-structured, unambiguous schemas | Typed variants per chart type; JSON Schema published. | `/docs` OpenAPI; schema docs |
| P7-13 | 10% | Frontend-friendly visualization spec | Flat data rows, explicit encoding with field types/units/sort, stable keys; a small reference renderer proves it. | UI demo |
| P7-B | Bonus | Deep citations | See Part 5. | Citations in every datum |

## 3. What it really means

- **System design is worth more than coverage** (35 vs 15). A well-built engine handling 6 question classes beats a hacky one handling 20.
- **The AI part is graded on restraint** ("avoid", "validation", "constraints"), not on how clever the agent is. A tightly constrained planner scores better than an open-ended agent loop.
- Code quality and correctness together (20%) mean **tests are graded, not optional**.
- Every criterion should have **visible evidence** in the repo or README, because graders can't see our intentions.

## 4. Priority order for our time (derived)

1. A correct end-to-end pipeline with a strict plan schema (System + AI = 55%).
2. A clean typed I/O schema and docs (I/O 10% + part of Code Quality).
3. Tests (Code Quality 20%).
4. Coverage breadth, with the network graph as the top priority (15%).
5. Citations (bonus, but cheap if designed in from the start, so build them into the aggregator from day one).
6. UI and deployment (bonus only).

## 5. Acceptance checks

- [ ] Before submitting, go through this table row by row and confirm each "evidence" item exists.
