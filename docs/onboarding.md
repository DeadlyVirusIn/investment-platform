> **ARCHIVED 2026-07-09** — describes the pre-auth single-user Phase-0 design
> (2026-04); superseded by the actual layout under apps/api/src/ and apps/worker/src/.
> Kept for history; do not use for implementation.

# Onboarding Guide

> For future self: how to find things and where to add things.

---

## Repo Layout

```
investment-platform/
├── apps/
│   ├── api/                  FastAPI app
│   │   ├── routers/          One file per route group (portfolio, watchlist, …)
│   │   ├── models/           SQLAlchemy ORM models
│   │   ├── schemas/          Pydantic request/response schemas
│   │   ├── services/         Business logic (engine calls, briefing gen)
│   │   └── main.py           App factory + lifespan
│   ├── web/                  React SPA (Vite)
│   │   └── src/
│   │       ├── pages/        One component per route
│   │       ├── components/   Shared UI components
│   │       └── lib/          Utilities (api.ts, cn.ts)
│   └── worker/               APScheduler background process
│       ├── jobs/             One file per scheduled job
│       ├── providers/        Data provider clients + rate limiters
│       └── engine/           Recommendation engine core
├── infra/                    Dockerfiles, Compose, Caddyfile
├── packages/
│   └── engine-config/        engine.yaml — edit signals/weights here
└── docs/                     Architecture, data providers, ledger, this file
```

---

## Adding a New Data Provider

1. Create `apps/worker/providers/<provider_name>.py`.
2. Implement a client class with `fetch_*` methods and a `TokenBucket` rate
   limiter (see existing providers for the pattern).
3. Add a row to `docs/data-providers.md` with the rate limits.
4. Create a job in `apps/worker/jobs/ingest_<provider>.py` that calls the
   client and upserts into the DB.
5. Register the job in `apps/worker/scheduler.py`.
6. Add the provider's API key to `.env.example` and `infra/compose/docker-compose.yml`
   environment blocks.

---

## Adding a New Job

1. Create `apps/worker/jobs/<job_name>.py`.
2. Define an `async def run()` function.
3. Register in `apps/worker/scheduler.py`:

```python
scheduler.add_job(
    jobs.my_new_job.run,
    CronTrigger(hour=6, minute=0, timezone="UTC"),
    id="my_new_job",
    replace_existing=True,
)
```

4. The job should write a `job_run` record (use the `record_job_run` helper).
5. The `JobsHealth` page will automatically pick it up via `/api/jobs/health`.

---

## Adding a New API Endpoint

1. Create or edit a router file in `apps/api/routers/`.
2. Add Pydantic schemas to `apps/api/schemas/`.
3. Register the router in `apps/api/main.py`.
4. Add the corresponding fetch call in the relevant `apps/web/src/pages/*.tsx`.

---

## Editing Engine Weights

Edit `packages/engine-config/engine.yaml`. Changes take effect after
restarting the worker (`make down && make up` or `docker compose restart worker`).

The worker validates the YAML schema on startup — invalid config will cause
the worker to exit with a descriptive error.

---

## Running Migrations

```bash
# Create a new migration (auto-detect model changes)
alembic revision --autogenerate -m "your description"

# Apply
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

Alembic config is in `alembic.ini` at the repo root. The `DATABASE_URL` env
var is read automatically.

---

## Common Debugging

| Symptom | Where to look |
|---------|--------------|
| API 500 errors | `docker compose logs api` |
| Worker not running jobs | `docker compose logs worker`; check `job_run` table |
| Stale data badges everywhere | Worker may be down or rate-limited; check `job_run` |
| Frontend type errors | `cd apps/web && npx tsc --noEmit` |
| Migration drift | `alembic current` vs `alembic heads` |
