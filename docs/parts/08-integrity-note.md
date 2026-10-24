# Part 8: Integrity Note (Use AI Tools Freely)

## 1. Source text (verbatim)

> You may use AI tools and online resources. We care about your **engineering judgment** and **design reasoning**.
>
> In your README, briefly describe:
>
> - which tools you used (if any)
> - how you validated correctness
> - what parts you designed/implemented deliberately vs generated and adapted
>
> We reward submissions that show evidence of thoughtful construction, testing, and iteration.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P8-0 | MAY | AI tools and online resources are allowed. | "You may use AI tools and online resources." |
| P8-1 | MUST | README states **which tools** were used. | "which tools you used (if any)" |
| P8-2 | MUST | README states **how correctness was validated**. | "how you validated correctness" |
| P8-3 | MUST | README separates **what was designed or implemented deliberately** from **what was generated and adapted**. | "what parts you designed/implemented deliberately vs generated and adapted" |
| P8-4 | SHOULD | Show **evidence** of thoughtful construction, testing, and **iteration**. | "We reward submissions that show evidence of thoughtful construction, testing, and iteration." |
| P8-5 | (guidance) | Keep it brief. | "briefly describe" |

## 3. What it really means

- They expect AI-assisted work and are checking for **judgment and honesty**. An honest, specific account beats a vague or inflated one. Anything claimed in this section can be probed in the technical interviews, so **only claim what is true**.
- "Evidence of iteration" is easiest to show with:
  - a **real commit history**: small, meaningful commits, not one giant "initial commit"
  - a short **decision log** of what we tried, what failed and what we changed
  - tests added when bugs were found
- "How you validated correctness" should name concrete checks:
  - unit tests
  - schema contract tests
  - the citation exactness check
  - comparing our counts against the ClinicalTrials.gov website for a few queries
  - manual review of the example outputs

## 4. Proposed approach

- **Tools to list (fill in at the end, accurately):**
  - Claude Code as the coding assistant
  - OpenAI models (with the exact model names used) inside the product
  - libraries (FastAPI, Pydantic, httpx, ...)
  - the ClinicalTrials.gov API docs
- **Keep a running log** in `docs/decisions.md` as we go: decision, alternatives, reason, and the date/time. It's the raw material for the README and for "evidence of iteration".
- **Designed vs generated:** the user should state which design decisions were theirs. Example: the user decided the architecture and schema, and the AI assistant generated drafts that the user reviewed and adapted. That split must match what actually happened in this session. We'll write it together at the end, from the log.
- **Commits:** commit at each working step, with clear messages.

## 5. Acceptance checks

- [ ] README has a short "AI tools and validation" section that answers all 3 questions.
- [ ] Every claim in that section is true and can be explained in an interview.
- [ ] Git history shows step-by-step progress.
- [ ] `docs/decisions.md` exists and is linked from the README.
