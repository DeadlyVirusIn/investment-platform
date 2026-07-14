# Polygon Credential Log-Leak — Incident + Redaction Release (Stage-B1 baseline)

Branch: `release/stage-b1-redaction` (from deployed `release/stage-b1-ingest-contracts @ 1fb6e28`).
Scope: **redaction-only**. No migration, execution lease, scheduler ordering,
snapshot health, Trust Center, confidence wording, Agent Gateway, web, or other
Elite feature. Diff is 5 files (sanitizer, api+worker loguru install, tick_loop
DB-store scrub, tests).

## Root cause
httpx `raise_for_status()` errors carry the full request URL; provider adapters
pass `apiKey` as a query param, so the exception string contains
`…apiKey=<live key>`. Logging `{exc}` leaked it. The pre-existing `_redact` util
missed it: the query-param regex was case-SENSITIVE (missed `apiKey`), the
bare-token regex requires pure alnum (the real key contains `_`), and the util
was never installed on the global loguru sink.

## Fix
- `_redact.py`: case-insensitive param scrub (apiKey/api_key/token/secret/key/…),
  value class matches percent-encoded + `_`/`.`/`-`; header-form scrub; bounded
  ≤4000. Preserves host/path/status/non-secret params.
- `install_global_redaction()`: loguru patcher scrubbing every message; wired
  into api + worker main after `logger.add()`.
- `redact_error_for_storage()`: scrub for `job_run.error_message` (tick_loop,
  both raised + returned-failure paths) — the DB path bypasses loguru.
- Never mutates the outbound request (scrub is on log/store copies).

## Behavior-unchanged proof
File-level diff = 5 files, redaction only. No route, schema, schedule, or
feature-flag change. Import scan: the only new import is `_redact` in the two
mains + tick_loop.

## Build / deploy / rollback / verify (PREPARED — not executed)
```
# build (on the VM, from the release checkout)
GIT_SHA=$(git rev-parse --short HEAD) docker compose --env-file .env \
  -f infra/compose/docker-compose.yml build api worker-cron worker-tickloop

# tag rollback BEFORE deploy (rollback-stageb1 images already exist)
docker tag compose-api:latest compose-api:rollback-redaction   # + worker-cron, worker-tickloop

# deploy (recreate ONLY the 3 affected services; no DB, no web, no caddy)
docker compose --env-file .env -f infra/compose/docker-compose.yml up -d \
  --no-deps api worker-cron worker-tickloop

# verify (deliberate fixture error, then grep)
docker exec compose-api-1 python -c "from loguru import logger; \
  from apps.api.src.options.data_provider._redact import install_global_redaction; \
  install_global_redaction(logger); \
  logger.warning('test https://api.polygon.io/x?apiKey=SHOULD_NOT_APPEAR')"
docker logs --since 2m compose-api-1 2>&1 | grep -c "SHOULD_NOT_APPEAR"   # expect 0
docker logs --since 2m compose-api-1 2>&1 | grep -c "apiKey=<REDACTED>"   # expect >=1

# rollback (if regression)
docker tag compose-api:rollback-redaction compose-api:latest   # + workers
docker compose --env-file .env -f infra/compose/docker-compose.yml up -d \
  --no-deps api worker-cron worker-tickloop
```
Rollback is image-retag + recreate; no schema/data touched (redaction is
code-only). Hard stop: not deployed; owner approval required.
