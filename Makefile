# Investment Platform — Makefile
# Requires: docker compose v2, python 3.12+, node 20+

COMPOSE_FILE := infra/compose/docker-compose.yml
COMPOSE := docker compose -f $(COMPOSE_FILE)

.PHONY: up down logs seed lint test web-dev

## Start backend services (db, api, worker) in detached mode
up:
	$(COMPOSE) up -d db api worker

## Stop and remove containers (data volumes are preserved)
down:
	$(COMPOSE) down

## Tail logs for all services (Ctrl-C to stop)
logs:
	$(COMPOSE) logs -f

## Apply migrations + seed stub symbols
seed:
	$(COMPOSE) exec api alembic upgrade head
	$(COMPOSE) exec api python -m scripts.seed_symbols

## Run Python linters (ruff + mypy)
lint:
	ruff check .
	mypy apps/api apps/worker

## Run backend test suite
test:
	pytest --tb=short -q

## Start Vite dev server (frontend only — backend must already be up)
web-dev:
	cd apps/web && npm run dev
