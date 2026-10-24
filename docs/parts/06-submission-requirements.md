# Part 6: Deliverables

## 1. Summary

The submission contains:

1. **Code:** all source code needed to run the service.
2. **README** covering how to run it (install, configure, start), the request and response schemas, the key design decisions and trade-offs, and the limitations and what we would improve with more time.
3. **Example runs:** 3 to 5 example questions, each with the actual JSON the system returned.
4. **Optional demo:** a small UI, a deployed endpoint, or a short video.

The brief asks for an archive of the work; a repository link was also accepted. The work is submitted within the exercise's time box.

## 2. Atomic requirements

| ID | Level | Requirement |
|---|---|---|
| P6-1 | MUST | Include **all** source code needed to run the service: nothing missing, no private dependencies, no hard-coded local paths. |
| P6-2 | MUST | README: **how to run**, covering all three of **install, configure, start**. |
| P6-3 | MUST | README: **request and response schema** documentation. |
| P6-4 | MUST | README: **key design decisions and trade-offs**. |
| P6-5 | MUST | README: **limitations** and **what we would improve with more time**. |
| P6-6 | MUST | **3 to 5** example queries, each with the **actual** JSON output from **our system**, not written by hand. |
| P6-7 | BONUS | A small UI. |
| P6-8 | BONUS | A deployed endpoint. |
| P6-9 | BONUS | A short demo video. |
| P6-10 | MUST | Submit within the exercise's time box. |
| P6-11 | MUST | Format: an archive **or** a repository link. |

## 3. What it means

- "Configure" means: which environment variables, which API key, and the defaults. A `.env.example` plus a section in the README.
- "Actual JSON outputs" are likely to be compared with what the code does. They must be produced by a script against the real system and saved as files, and they must match the current schema at submission. (Built: [`../examples/`](../examples).)
- Exactly **3 to 5**: not 2, not 12. Pick the 5 that show the widest range: the 5 appendix classes, including a network graph and a comparison.
- The optional demo items earn bonus points, but only **after** the MUST items are solid.

## 4. Ambiguities and decisions

- **Archive vs repository link.** Either works. **Decided ([design Q19](../design/19-deployment-ui.md)):** an archive of the repository plus a **deployed endpoint**. The git history shows iteration, which Part 8 rewards.
  - The repository must contain no secrets (`.env` is git-ignored, and the history is scanned before pushing).
  - The deployment target first planned in Q19 (`api.engineeradriel.com` plus a Vercel frontend) was replaced on 2026-10-25. **Resolved:** the web app and API run on Kubernetes (k3s) on one EC2 instance, at https://trials.cheiron.engineeradriel.com and https://api.cheiron.engineeradriel.com; see [design Q19](../design/19-deployment-ui.md), "Revision (2026-10-25)".
- **Should example runs be frozen after model or API changes?** Live data changes daily. The outputs are saved with a `retrieved_at` timestamp, and live counts are expected to drift.
- **Deployed endpoint and model cost.** A public endpoint spends money on every model call.
  - Proposed: a rate limit plus a daily spending cap.
  - The API key is stored as a secret on the host, never in the repository.
  - **Resolved:** configurable per-client limits ([design Q19](../design/19-deployment-ui.md), "Configurable limits"), a daily AI spending cap that returns `budget_exceeded` ([design Q16](../design/16-database.md), [Q17](../design/17-error-handling.md)), and the key kept in AWS Secrets Manager (Q19 revision).
- **Demo video.** Low cost if recorded at the end (2 to 3 minutes). Optional.

## 5. Acceptance checks

- [ ] A fresh clone plus the README steps on a clean machine (or clean Docker) gives a running service.
- [ ] The README has all 4 required sections plus the Part 8 tool-use section.
- [ ] `examples/` holds 3 to 5 request and response pairs created by a script, and they validate against the schema.
- [ ] No secrets in the git history (a secret scanner, or `git log -p | grep -i "sk-"`).
- [ ] Submitted within the time box.
