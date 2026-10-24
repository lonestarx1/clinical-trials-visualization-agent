# Part 7: Evaluation criteria

## 1. Summary

The brief weights the evaluation as follows:

| Weight | Area | What is assessed |
|---|---|---|
| 35% | System design | Clear, reasoned decisions; maintainable and extensible structure; sensible handling of real-world API data |
| 20% | AI / agent design | Avoiding steps prone to hallucination; validation and constraints; sensible planning and reasoning steps with appropriate tools |
| 20% | Code quality | Readability, organization and documentation; correctness and robustness |
| 15% | Query and visualization coverage | Range of question types; handling many question classes without one-off hacks; richer visualizations (such as meaningful network graphs) over single-chart systems |
| 10% | Input/output design | Well-structured, unambiguous schemas; a frontend-friendly visualization specification |
| Bonus | Deep citations | Traceability to the source records |

## 2. Atomic criteria and how we address each

| ID | Weight | Criterion | How we address it | Evidence in the repository |
|---|---|---|---|---|
| P7-1 | 35% | Clear, rational design decisions | Each major choice is written down with its alternatives and the reason it was picked. | README "Key design decisions"; [`../design/`](../design/README.md) |
| P7-2 | 35% | Maintainable structure and extensibility | Separate modules: API client, planner, query compiler, aggregator, chart builder, schemas. Dimension and chart registries. | Folder layout; [design Q15](../design/15-code-structure-stack.md) |
| P7-3 | 35% | Sensible handling of real-world API data | Pagination, the total count, multi-valued fields, partial dates, missing values, name normalisation, retries and backoff, caching. Each one is surfaced in `meta`. | [`../api/live-probe.md`](../api/live-probe.md); tests with recorded API data; `meta` notes |
| P7-4 | 20% | Avoid hallucination-prone steps | The LLM never produces numbers, data or citations. It only produces a plan. Data and citations come from code over API records. | [design Q3](../design/03-ai-vs-code.md); tests |
| P7-5 | 20% | Validation or constraints | The plan is a strict JSON schema with enums, checked with Pydantic, then semantic checks (e.g. the chart type fits the dimensions), with a repair and retry loop. Structured fields override the LLM. | Planner code; tests for invalid plans; [design Q4b](../design/04b-ai-validation.md) |
| P7-6 | 20% | Sensible planning and reasoning steps, appropriate tools | Clear stages: interpret -> plan -> retrieve -> aggregate -> build chart -> check. The interpretation is recorded in `meta`. The LLM is used only where language understanding is needed. | Trace in `meta` and logs; [design Q2](../design/02-pipeline.md) |
| P7-7 | 20% | Readability, organization, documentation | Typed Python, small functions, docstrings where they help, consistent naming. | Code; strict mypy and ruff in CI |
| P7-8 | 20% | Correctness and robustness | Unit tests (aggregation, date parsing, normalisation), contract tests (schema), integration tests (recorded API data), error handling, timeouts. | `backend/tests/`; CI; README "Testing and validation" |
| P7-9 | 15% | Breadth of query types | All 5 appendix classes (time trend, distribution, comparison, geographic, network) plus numeric questions (histogram, scatter). | [`../examples/`](../examples); end-to-end tests |
| P7-10 | 15% | Many question classes without one-off hacks | One generic engine; no `if "network" in query` branches. | Code review |
| P7-11 | 15% | Richer visualizations, meaningful networks | Typed, weighted, pruned network graphs with citations. | Network example; [design Q13](../design/13-networks.md) |
| P7-12 | 10% | Well-structured, unambiguous schemas | One typed variant per chart type; JSON Schema published. | OpenAPI at `/docs`; [design Q12](../design/12-io-schema.md) |
| P7-13 | 10% | Frontend-friendly visualization spec | Flat data rows, explicit encoding with field types, units and sort order, stable keys; a reference renderer proves it. | The web app in [`frontend/`](../../frontend) |
| P7-B | Bonus | Deep citations | See Part 5. | Citations on every datum |

## 3. What it means

- **System design is worth more than coverage** (35% vs 15%). A well-built engine that handles 6 question classes beats a hacky one that handles 20.
- **The AI part is assessed on restraint** (avoiding hallucination, validation, constraints), not on how clever the agent is. A tightly constrained planner fits the criteria better than an open-ended agent loop.
- Code quality and correctness together (20%) mean **tests are part of the assessment**, not optional.
- Every criterion needs **visible evidence** in the repository or README.

## 4. Priority order (derived)

1. A correct end-to-end pipeline with a strict plan schema (system design plus AI design: 55%).
2. A clean, typed I/O schema and its docs (I/O 10%, plus part of code quality).
3. Tests (code quality 20%).
4. Coverage breadth, with the network graph first (15%).
5. Citations (a bonus, but cheap if designed in from the start, so they are built into the aggregator from day one).
6. UI and deployment (bonus only).

## 5. Acceptance checks

- [ ] Go through the table above row by row and confirm each evidence item exists.
