# Investment Platform — Makefile
# Requires: docker compose v2, python 3.12+, node 20+

COMPOSE_FILE := infra/compose/docker-compose.yml
COMPOSE := docker compose -f $(COMPOSE_FILE)

.PHONY: up down logs seed lint test web-dev build

## P0-4 — provenance-stamped image build (api + both workers).
## Bakes GIT_SHA/GIT_BRANCH/GIT_DIRTY/BUILD_TS into the images so every
## container ties back to an exact git state (see build_provenance.py).
## Building any other way leaves provenance "unknown" — flagged at
## runtime as unknown_sha. Always uses --env-file .env (compose-dir gotcha).
build:
	GIT_SHA=$$(git rev-parse HEAD) \
	GIT_BRANCH=$$(git rev-parse --abbrev-ref HEAD) \
	GIT_DIRTY=$$([ -n "$$(git status --porcelain)" ] && echo true || echo false) \
	BUILD_TS=$$(date -u +%Y-%m-%dT%H:%M:%SZ) \
	$(COMPOSE) --env-file .env build api worker-cron worker-tickloop

## Start backend services (db, api, worker) in detached mode
up:
	$(COMPOSE) up -d db api worker

## Stop and remove containers (data volumes are preserved)
down:
	$(COMPOSE) down

## ─── Phase 11Z incident-response: DB volume safety ──────────────────────
.PHONY: db-clean-test db-clean-dev verify-deploy

## Run alembic upgrade head against the ISOLATED `pg-11v-test`
## container. NEVER touches `compose_pgdata` (the dev volume).
## Expects pg-11v-test to be running on the compose_backend network.
##
## Phase 15i.R hardening (post-2026-05-11 incident; see
## docs/ops/INCIDENT_2026_05_11_dev_db_unintended_migration.md).
## Three layers of routing safety, all passed in the same exec:
##   1. -e DATABASE_URL=...              env.py reads this
##   2. -x url=...                       env.py honors this with
##                                        higher precedence than env
##   3. -e ALEMBIC_REQUIRE_TEST_TARGET=1 env.py refuses to run if the
##                                        resolved hostname is the
##                                        known dev DB
## env.py logs the resolved target host:port:db to stderr BEFORE any
## DDL runs.
db-clean-test:
	@echo "[db-clean-test] applying alembic upgrade head against pg-11v-test"
	@docker exec \
	  -e DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
	  -e ALEMBIC_REQUIRE_TEST_TARGET=1 \
	  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
	    alembic -c infra/alembic/alembic.ini \
	    -x url=postgresql+psycopg://test:test@pg-11v-test:5432/test \
	    upgrade head"

## Wipe the dev `compose_pgdata` volume. REFUSES unless caller sets
## REQUIRE_VOLUME_DELETE_CONFIRMATION=I_UNDERSTAND_THIS_DELETES_DATABASE
## AND --force-dev-wipe is forwarded. Loops back into the safe wrapper.
db-clean-dev:
	@bash scripts/safe_compose_down.sh -v --force-dev-wipe

## Deploy-readiness verification. MUST NOT wipe compose_pgdata.
## Migration check uses the isolated test DB.
verify-deploy:
	@echo "[verify-deploy] rebuild api"
	$(COMPOSE) --env-file .env build api
	@echo "[verify-deploy] import smoke"
	@docker exec compose-api-1 python -c "import apps.api.src.main as m; print('routes=', len(m.app.routes))"
	@echo "[verify-deploy] alembic upgrade against ISOLATED test DB"
	@$(MAKE) db-clean-test
	@echo "[verify-deploy] regression suite"
	@docker exec \
	  -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
	  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
	    apps/api/tests/integration/research/ apps/api/tests/unit/research/ \
	    apps/api/tests/integration/test_options_shadow_eval_pg.py --no-header -q"
	@echo "[verify-deploy] DONE - compose_pgdata UNTOUCHED"

## ─── Phase 11Z hardening: backup + safe verify ─────────────────────────
.PHONY: db-backup db-restore-preview verify-deploy-safe

## Take timestamped pg_dump of dev DB. Refuses to overwrite.
## Honors $$BACKUP_DIR (default .backups), $$BACKUP_KEEP (default 10).
db-backup:
	@bash scripts/backup_dev_db.sh

## Show what restoring the newest backup WOULD do (dry diff). No restore.
db-restore-preview:
	@latest=$$(ls -1t .backups/devdb_*.sql 2>/dev/null | head -1); \
	if [ -z "$$latest" ]; then \
	  echo "[restore-preview] no backup found in .backups/" >&2; exit 2; \
	fi; \
	echo "[restore-preview] newest backup: $$latest"; \
	echo "[restore-preview] size: $$(wc -c < $$latest) bytes"; \
	echo "[restore-preview] tables in dump:"; \
	grep -E "^(CREATE TABLE|COPY|INSERT INTO)" "$$latest" \
	  | awk '{print $$2, $$3, $$4}' | sort -u | head -40

## Same as verify-deploy plus a backup-age preflight. Refuses to run
## unless a fresh-enough backup exists. Override with:
##   SKIP_BACKUP_CHECK=I_ACCEPT_DATA_LOSS_RISK make verify-deploy-safe
verify-deploy-safe:
	@if [ "$$SKIP_BACKUP_CHECK" = "I_ACCEPT_DATA_LOSS_RISK" ]; then \
	  echo "[verify-deploy-safe] backup-age check SKIPPED by env"; \
	else \
	  latest=$$(ls -1t .backups/devdb_*.sql 2>/dev/null | head -1); \
	  if [ -z "$$latest" ]; then \
	    echo "[verify-deploy-safe] REFUSED: no .backups/devdb_*.sql found"; \
	    echo "  Run: make db-backup"; exit 2; \
	  fi; \
	  age=$$((( $$(date +%s) - $$(stat -c %Y "$$latest" 2>/dev/null || stat -f %m "$$latest") ) / 3600)); \
	  if [ "$$age" -gt 24 ]; then \
	    echo "[verify-deploy-safe] REFUSED: newest backup is $$age h old (>24h)"; \
	    echo "  Run: make db-backup  OR  set SKIP_BACKUP_CHECK=I_ACCEPT_DATA_LOSS_RISK"; \
	    exit 2; \
	  fi; \
	  echo "[verify-deploy-safe] backup OK ($$age h old): $$latest"; \
	fi
	@$(MAKE) verify-deploy

## Tail logs for all services (Ctrl-C to stop)
logs:
	$(COMPOSE) logs -f

## Apply migrations + seed stub symbols
seed:
	$(COMPOSE) exec api alembic -c infra/alembic/alembic.ini upgrade head
	$(COMPOSE) exec api python -m scripts.seed_symbols

## MVP — seed curated model portfolios + compute track records (idempotent).
## Run after `make migrate`/`make seed` so the model_portfolio tables exist.
seed-model-portfolios:
	$(COMPOSE) exec api python -m scripts.seed_model_portfolios

## Run Python linters (ruff + mypy)
lint:
	ruff check .
	mypy apps/api apps/worker

## Run backend test suite
test:
	pytest --tb=short -q

.PHONY: test-auth
## M1/M1B auth coverage — build the test image (INSTALL_TEST_DEPS=true brings in
## pytest) and run the auth + isolation suite against the ISOLATED test DB.
## Run before merging ANY public-auth change so M1/M1A/M1B coverage can't be
## skipped accidentally. Requires the dev `db` service + investment_platform_test.
test-auth:
	docker build -f infra/docker/api.Dockerfile --build-arg INSTALL_TEST_DEPS=true -t arthos-api-test .
	docker run --rm --network compose_backend \
	  -e TEST_DATABASE_URL=postgresql+psycopg://invest:dev_only_password@db:5432/investment_platform_test \
	  -e INTEGRATION_DB_ALLOW_UNSAFE=1 arthos-api-test \
	  python -m pytest apps/api/tests/integration/test_accounts_m1_pg.py \
	    apps/api/tests/integration/test_login_rate_limit_pg.py \
	    apps/api/tests/integration/test_auth_ops_m1c_pg.py \
	    apps/api/tests/integration/test_profile_pg.py \
	    apps/api/tests/integration/test_feedback_pg.py \
	    apps/api/tests/integration/test_feedback_report_pg.py \
	    apps/api/tests/unit/test_feedback_report.py \
	    apps/api/tests/integration/test_paper_user_portfolio_pg.py \
	    apps/api/tests/unit/test_agent_gateway_tokens.py \
	    apps/api/tests/integration/test_agent_gateway_pg.py \
	    apps/api/tests/integration/test_agent_gateway_http_pg.py \
	    apps/api/tests/integration/test_agent_jobs_pg.py \
	    apps/api/tests/integration/test_elite_authz_matrix_pg.py \
	    apps/api/tests/integration/test_scheduler_pg.py --no-header -q

.PHONY: prune-login-attempts
## M1C — delete old login_attempt rows (honors AUTH_LOGIN_ATTEMPT_RETENTION_DAYS;
## never prunes rows within the active window+lockout horizon). Manual/admin run.
prune-login-attempts:
	docker exec compose-api-1 sh -lc "cd /app && PYTHONPATH=/app python scripts/prune_login_attempts.py"

.PHONY: feedback-report feedback-report-json feedback-report-7d
## M5A — anonymized demand-validation report from user_feedback_signal.
feedback-report:
	docker exec compose-api-1 sh -lc "cd /app && PYTHONPATH=/app python scripts/report_feedback_signals.py"
feedback-report-json:
	docker exec compose-api-1 sh -lc "cd /app && PYTHONPATH=/app python scripts/report_feedback_signals.py --json"
feedback-report-7d:
	docker exec compose-api-1 sh -lc "cd /app && PYTHONPATH=/app python scripts/report_feedback_signals.py --days 7"

.PHONY: public-beta-preflight public-beta-preflight-prod
## M6 — read-only deploy preflight. dev never blocks; prod exits 1 on any error.
public-beta-preflight:
	docker exec compose-api-1 sh -lc "cd /app && PYTHONPATH=/app python scripts/preflight_public_beta.py --mode dev"
public-beta-preflight-prod:
	docker exec compose-api-1 sh -lc "cd /app && PYTHONPATH=/app python scripts/preflight_public_beta.py --mode prod"

## Start Vite dev server (frontend only — backend must already be up)
web-dev:
	cd apps/web && npm run dev

# ---------------------------------------------------------------------------
# Phase OPS1 — paper trading automation
# ---------------------------------------------------------------------------
.PHONY: paper-daily paper-daily-dry paper-daily-date paper-daily-force paper-daily-no-shadow

## Run today's paper-trading pipeline (frozen strategy, read-only adapter)
paper-daily:
	python -m scripts.run_paper_daily

## Dry run (no DB writes, summary only)
paper-daily-dry:
	python -m scripts.run_paper_daily --dry-run

## Run for specific date: make paper-daily-date D=2026-04-22
paper-daily-date:
	@test -n "$(D)" || (echo "usage: make paper-daily-date D=YYYY-MM-DD" && exit 1)
	python -m scripts.run_paper_daily --date $(D)

## Force recompute (overwrite existing snapshot)
paper-daily-force:
	python -m scripts.run_paper_daily --force-recompute

## Skip shadow evaluation step
paper-daily-no-shadow:
	python -m scripts.run_paper_daily --skip-shadow
