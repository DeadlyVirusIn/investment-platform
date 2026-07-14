# ArthOS MVP — Private Beta Deploy Runbook

"Ideas you can follow and prove." Branch `mvp/ideas-you-can-follow`.
This is the deploy-ready checklist for a Private Beta of the MVP (Sprints A–G).

## Prerequisites
- Postgres reachable; `DATABASE_URL` set.
- `POLYGON_API_KEY` + `TIINGO_API_KEY` set (price data already backfilled to total-return via BP34).
- Edge/gateway must inject a stable per-user identity header **`X-Auth-User-Id`** on every `/api/*` request (the web app already sends a per-browser device id; for real accounts, map the IdP subject here).

## Deploy steps (in order)
1. **Migrate** — apply schema (adds model_portfolio tables + FK):
   ```
   make migrate            # or: alembic -c infra/alembic/alembic.ini upgrade head
   ```
   Expected head: `102_portfolio_follow_fk`.
2. **Seed model portfolios** (idempotent — curated portfolios + track records):
   ```
   make seed-model-portfolios     # python -m scripts.seed_model_portfolios
   ```
   Expected: 4 portfolios (steady-compounders, dividend-growers, american-megacaps, everyday-brands).
3. **Build + deploy** the new api + web images (the running service must carry Sprint A–G code, not a prior image):
   ```
   docker compose --env-file .env -f infra/compose/docker-compose.yml build api web
   docker compose --env-file .env -f infra/compose/docker-compose.yml up -d api web
   ```
4. **Smoke check:**
   - `GET /api/model-portfolios` -> 4 portfolios with non-null `return_pct`.
   - `GET /api/model-portfolios/steady-compounders` -> holdings + curve.
   - `POST /api/model-portfolios/steady-compounders/follow` with `X-Auth-User-Id: test1` -> `opened` non-empty; **401 without the header**.
   - `GET /api/paper/canonical/stock` with two different `X-Auth-User-Id` values -> different `portfolio_id`.
   - Web: `/` redirects to `/v2/discover`; nav shows only Discover / My Portfolio / Learn / Me; `/overview` bounces to `/v2` unless operator flag set.

## What's gated / operator-only
- `/advanced` opts a browser into operator mode (localStorage `arthos_operator`), then `/overview` + labs/options/ops/legacy. Not reachable for beginners.
- Options subsystem and quant labs are behind that gate.

## Rollback
- Code: redeploy the previous image; `git revert` the branch.
- Schema: `alembic downgrade 100_paper_position_attribution` (drops the 4 MVP tables; additive, no other data touched).
- Per-run data (follows/adds) lives in per-user paper portfolios; safe to leave or prune.

## Known limits for Private Beta (P1/P2 — acceptable, track for GA)
- Identity is a per-browser device id (header-based), not a full IdP — fine for invite-only beta; wire Clerk/Supabase before Public Beta.
- Rate limit on Follow/Add is in-process (per worker) — move to Redis when scaling beyond one worker.
- Model-portfolio track records are survivorship-biased one-shot backtests (disclosed in-product).
- Live before/after UI screenshots require a running dev server; capture during QA.
