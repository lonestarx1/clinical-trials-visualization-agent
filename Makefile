.PHONY: up down logs test test-db test-live test-e2e lint fmt

BACKEND := cd backend &&
LOCAL_DB := postgresql+asyncpg://ctviz:ctviz@127.0.0.1:5433/ctviz

up: ## Build and start the stack, wait until healthy
	@test -f .env || (echo "Missing .env: cp .env.example .env and set OPENAI_API_KEY" && exit 1)
	docker compose up -d --build --wait
	@echo "API ready: http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f

test: ## Offline tests (no network, no AI)
	$(BACKEND) uv run pytest

test-db: ## Database tests against the Compose Postgres
	docker compose up -d --wait postgres
	$(BACKEND) DATABASE_URL=$(LOCAL_DB) uv run pytest -m db

test-live: ## Live ClinicalTrials.gov checks (about 25 throttled calls)
	$(BACKEND) uv run pytest -m live

test-e2e: ## Acceptance tests against the running stack (real API and AI)
	$(BACKEND) uv run pytest -m e2e

lint:
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy app

fmt:
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .
