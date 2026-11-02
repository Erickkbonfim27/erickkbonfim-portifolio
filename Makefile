# Every command runs from the repository root. `.env` (copied from .env.example)
# is loaded when it exists; the services themselves run on the VPS.

BACKEND := backend
FRONTEND := frontend
ENV_FILE := $(if $(wildcard .env),--env-file ../.env,)
RUN := cd $(BACKEND) && uv run $(ENV_FILE)

.DEFAULT_GOAL := help
.PHONY: help install dev-api dev-worker dev-web build-web check-web migrate migration create-admin setup-storage reindex seed test test-unit cov lint format typecheck imports runtime check

help: ## List the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci

dev-api: ## Run the API with hot reload on :8000
	$(RUN) uvicorn portfolio.main:create_app --factory --reload --port 8000

dev-worker: ## Run the worker (outbox relay, consumers, daily jobs). Off by default: dev points at prod
	$(RUN) portfolio worker

dev-web: ## Run the site with hot reload on :5173 (VITE_API_URL in frontend/.env)
	cd $(FRONTEND) && npm run dev

build-web: ## Build the site into frontend/dist
	cd $(FRONTEND) && npm run build

check-web: ## Site: typecheck, lint and tests
	cd $(FRONTEND) && npm run check

migrate: ## Apply pending migrations to DATABASE_URL
	$(RUN) alembic upgrade head

migration: ## Create a migration from model changes: make migration name="add posts"
	@test -n "$(name)" || (echo 'usage: make migration name="what changed"' && exit 1)
	$(RUN) alembic revision --autogenerate -m "$(name)"

create-admin: ## Create the admin account (prompts for email and password)
	$(RUN) portfolio create-admin

setup-storage: ## Create the bucket with public-read, no-listing policy
	$(RUN) portfolio setup-storage

seed: ## Create, update and publish content from TOML files (SEED=documentos/seed)
	$(RUN) portfolio seed $(abspath $(or $(SEED),documentos/seed))

reindex: ## Rebuild the search index (Qdrant) from published content
	$(RUN) portfolio reindex

test: ## All tests (integration ones need TEST_DATABASE_ADMIN_URL)
	$(RUN) pytest

test-unit: ## Unit tests only, no network
	$(RUN) pytest tests/unit

cov: ## All tests with the 100% coverage gate
	$(RUN) pytest --cov

lint: ## Ruff lint and format check
	cd $(BACKEND) && uv run ruff check src tests migrations && uv run ruff format --check src tests migrations

format: ## Apply ruff formatting and safe fixes
	cd $(BACKEND) && uv run ruff format src tests migrations && uv run ruff check --fix src tests migrations

typecheck: ## mypy --strict
	cd $(BACKEND) && uv run mypy

imports: ## Architecture boundaries (import-linter)
	cd $(BACKEND) && uv run lint-imports

runtime: ## Build the app with production dependencies only, as the deploy does
	cd $(BACKEND) && uv run --isolated --no-dev python tests/deploy_smoke.py

check: lint typecheck imports runtime cov check-web ## Everything that must pass before a push
