# ClinicalTrials.gov Query-to-Visualization Agent

A backend service that turns a natural-language question about clinical trials into a structured visualization spec, backed by live data from the [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api), with citations for every data point.

> **Status: in progress.** The skeleton (M0) is in place: settings, health endpoint, Docker Compose stack, CI and the acceptance tests. See [the implementation plan](docs/implementation-plan.md).

## Quick start

Requirements: Docker with Compose v2.

```bash
cp .env.example .env    # then set OPENAI_API_KEY
make up                 # builds and starts postgres + api, waits until healthy
curl localhost:8000/health
```

API docs: http://localhost:8000/docs

## Development

Requirements: [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed by uv if missing).

| Command | What it runs |
|---|---|
| `make test` | Offline tests: unit, contract, integration (no network, no AI) |
| `make test-db` | Database tests against the Compose Postgres |
| `make test-e2e` | Acceptance tests against the running stack (real API and AI) |
| `make lint` | ruff, formatting check, mypy (strict) |

## Configuration

All settings come from environment variables (or `.env`). Only `OPENAI_API_KEY` is required. The full list, with defaults, is in [`backend/app/core/config.py`](backend/app/core/config.py); per-stage model settings use the `GUARD_*`, `PLANNER_*` and `NARRATOR_*` prefixes (e.g. `PLANNER_MODEL=gpt-5.4`).

## Documentation

- [Assignment and requirements](docs/parts/README.md)
- [ClinicalTrials.gov API research](docs/api/contract.md)
- [System design (Q1-Q20)](docs/design/README.md)
