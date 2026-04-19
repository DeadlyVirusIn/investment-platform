# Investment Intelligence Platform

A personal, self-hosted investment dashboard that aggregates portfolio data,
runs a rule-based recommendation engine, and delivers a daily briefing. Built
for a single user; no multi-tenancy, no third-party auth. Architecture
decisions are documented in `docs/architecture.md` and informed by an
extensive debate synthesis (see `docs/` folder).

---

## Quickstart

### Prerequisites
- Docker + Docker Compose v2
- Node 20+ (for frontend dev only)
- A Tiingo free-tier API key (500 EOD req/hr)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in POSTGRES_PASSWORD, TIINGO_API_KEY, and FERNET_KEY
```

Generate a Fernet key if needed:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Start backend services

```bash
docker compose -f infra/compose/docker-compose.yml up -d db api worker
```

Wait ~15 s for Postgres to initialise, then verify:
```bash
docker compose -f infra/compose/docker-compose.yml ps
curl http://localhost:8000/api/health
```

### 3. Run the frontend (local dev)

```bash
cd apps/web
npm install
npm run dev
```

### 4. Open the app

Navigate to **http://localhost:5173**

The Vite dev server proxies `/api/*` to `http://localhost:8000`.

---

## Seed data

```bash
make seed
```

Runs `alembic upgrade head` (applies all migrations) then a Python script
that inserts a stub symbol list so the watchlist and recommendations pages
have something to show.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full system design:
ingestion pipeline, DB schema, recommendation engine, alert delivery, and
security model.

---

## Project layout

```
apps/
  api/       FastAPI backend
  web/       React + Vite frontend
  worker/    APScheduler background jobs
infra/
  compose/   Docker Compose files (dev + prod overlay)
  docker/    Dockerfiles
  caddy/     Caddyfile for production reverse proxy
packages/
  engine-config/   engine.yaml — recommendation engine weights
docs/        Architecture, data providers, ledger model, onboarding
```

---

## License

Personal use only — no license granted.
