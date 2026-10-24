# Part 6: Submission Requirements

## 1. Source text (verbatim)

> Submit a zip file containing:
>
> 1. **Code:** All source code required to run the service.
> 2. **README:** must include
>    - how to run (install, configure, start)
>    - request/response schema documentation (inputs/outputs)
>    - key design decisions and tradeoffs
>    - limitations and what you would improve with more time
> 3. **Example Runs:** Provide **3-5 example queries** with the **actual JSON outputs** produced by your system.
> 4. **(Optional) Demo**
>    - a small UI
>    - a deployed endpoint
>    - a short demo video

Related, from Cheiron's email (2026-10-24 12:50 KST):

> Submit Your Work: https://you.ashbyhq.com/Cheiron/assignment/593473ca-1a6c-4167-8c9c-905a36f54cbe
> A file or GitHub link both work.
> Please submit before your 24-hour window closes.
> Late submissions won't be considered, so plan accordingly.

## 2. Atomic requirements

| ID | Level | Requirement | Source phrase |
|---|---|---|---|
| P6-1 | MUST | Include **all** source code needed to run the service: nothing missing, no private dependencies, no hard-coded local paths. | "All source code required to run the service." |
| P6-2 | MUST | README: **how to run**, covering all three of **install, configure, start**. | "how to run (install, configure, start)" |
| P6-3 | MUST | README: **request and response schema** documentation. | "request/response schema documentation (inputs/outputs)" |
| P6-4 | MUST | README: **key design decisions and tradeoffs**. | "key design decisions and tradeoffs" |
| P6-5 | MUST | README: **limitations** and **what we'd improve with more time**. | "limitations and what you would improve with more time" |
| P6-6 | MUST | **3 to 5** example queries, each with the **actual** JSON output from **our system**, not hand-written. | "3-5 example queries with the actual JSON outputs produced by your system" |
| P6-7 | BONUS | Small UI. | "a small UI" |
| P6-8 | BONUS | Deployed endpoint. | "a deployed endpoint" |
| P6-9 | BONUS | Short demo video. | "a short demo video" |
| P6-10 | MUST | Submit through the Ashby link **before Sun 2026-10-25 15:00 KST**. Late is rejected. | email |
| P6-11 | MUST | Format: a zip file **or** a GitHub link. | PDF + email |

## 3. What it really means

- "Configure" means: which environment variables, which API key, and the defaults. `.env.example` plus a table in the README.
- "Actual JSON outputs" will likely be compared with what the code does. They must be produced by a script against the real system and saved as files (e.g. `examples/01-time-trend.request.json` + `.response.json`), and they must match the current schema at submission.
- Exactly **3-5**: not 2, not 12. Pick 5 that show the widest range: the 5 appendix classes, including a network graph and a comparison. Extra examples can go in a separate folder if they add value, but the 5 main ones come first.
- Optional demo items are bonus points, but only **after** the MUST items are solid.

## 4. Ambiguities and proposed decisions

- **Zip vs GitHub link.** The email allows either. **Decided (Q19):** submit a **zip of the repository** plus the **deployed endpoint** (`https://api.engineeradriel.com` + the Vercel frontend). The git history (with `.git` included or a public repo link) shows iteration, which Part 8 rewards.
  - As a safety net, also attach a zip, if the Ashby form accepts both.
  - Make sure the repo has no secrets (`.env` is ignored; scan before pushing).
- **Should example runs be frozen after LLM or API changes?** Live data changes daily. Proposed: save the outputs with a `retrieved_at` timestamp, and note that live counts will drift.
- **Deployed endpoint and the LLM key.** A public endpoint spends Cheiron's OpenAI key.
  - Proposed: rate limit plus a short daily cap, or a shared demo token.
  - The key must be stored as a secret on the host, never in the repo.
  - Decide in the deploy step.
- **Demo video.** Low cost if done at the end with a screen recording (2-3 minutes). Optional.

## 5. Acceptance checks

- [ ] Fresh clone + README steps on a clean machine (or clean Docker) -> service runs. Actually test this before submitting.
- [ ] README has all 4 required sections plus the Part 8 integrity section.
- [ ] `examples/` holds 3-5 request/response pairs created by a script, and they validate against the schema.
- [ ] No secrets in git history (`git log -p | grep -i "sk-"` or a secret scanner).
- [ ] Submitted on Ashby with margin (target ~14:00 KST Sunday). Screenshot of the confirmation saved.
