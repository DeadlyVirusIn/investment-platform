# Public-Beta / Oracle Readiness (M6)

Audit + checklist for a safe first public/Oracle deploy. **No deploy is performed
by this doc.** Run `make public-beta-preflight-prod` against the target env before
shipping. Supersedes the stale `PRIVATE_BETA_DEPLOY.md` (which expects head 102).

## Commit chain (auth → demand stack)

M1 `2122a48` · M1A `64bb390` · M1B `f3571f0` · M1C `64c0ebc` · M2 `1428cbf` ·
M3 `62196e5` · M4 `06001f8` · M4A `825f27a` · M5 `3c832f5` · M5A `bb9e9d9`.
Alembic head: **`107_user_feedback_signal`**.

## Deployment prerequisites

- Docker + Docker Compose on the target host (Oracle VM `150.136.38.189`, project `investment-platform`).
- Prod compose: `infra/compose/docker-compose.prod.yml` + **Caddy** (`infra/caddy/Caddyfile`, `:80`, `/api/*`→`api:8000`, static SPA from `/srv/web`). The web image (`infra/docker/web.Dockerfile`) is **build-artifact only** (`npm ci && npm run build` → `dist/`); Caddy serves it — there is no built-in web server.
- Postgres 17 volume provisioned + backed up before first migrate.
- HTTPS terminated at Caddy/Cloudflare (required for `SESSION_COOKIE_SECURE`).

## Required production env (set in the prod `.env`)

| Var | Prod value | Notes |
|---|---|---|
| `AUTH_DISABLED_LOCAL` | **false** | dev `.env` ships `true` — must flip. |
| `DEMO_DEVICE_MODE` | **false** | device-header identity is demo-only. |
| `SESSION_COOKIE_SECURE` | **true** | not in dev `.env` (defaults false); set behind HTTPS. |
| `DATABASE_URL` | prod DSN | psycopg v3 sync driver. |
| `FERNET_KEY` | prod key | secret encryption; **rotate**, never reuse the dev key. |
| `POSTGRES_USER/PASSWORD/DB` | prod creds | strong password (dev uses `dev_only_password`). |
| `AUTH_TRUST_PROXY_HEADERS` | true (behind proxy) | + `AUTH_TRUSTED_PROXY_CIDRS` = ingress/Cloudflare ranges, so login rate-limiting keys on the real client IP. |
| `CORS_ALLOWED_ORIGINS` | SPA origin | **see CORS blocker below.** |

Placeholders are documented in `.env.example` (M6 section). Never commit real secrets.

## Known pre-deploy blockers (must fix before public traffic)

1. **CORS is hardcoded** to `http://localhost:5173` (`apps/api/src/main.py:185-191`). For prod the allowed origin must become the SPA domain (make it env-driven from `CORS_ALLOWED_ORIGINS`). The prod preflight flags a localhost origin. **Deferred to the deploy sprint (app-behavior change + needs a rebuild/test); not changed in this audit.**
2. **`SESSION_COOKIE_SECURE` absent from `.env`** → defaults false. Add `=true` in prod.
3. **`AUTH_DISABLED_LOCAL=true`** in the dev `.env` — must be false in prod.
4. **Rotate the Finnhub key** (prior value was exposed) and any other key before prod; the dev `FERNET_KEY`/DB password must not be reused.
5. **Cron orchestration:** `worker-cron` runs `scripts/run_daily_loop.sh` (03:30 ET, Tue–Sat) via supercronic — confirm the supercronic wiring exists in the prod compose/entrypoint on the target host (not visible in the base compose).
6. **Stale deploy doc:** `PRIVATE_BETA_DEPLOY.md` targets head 102 — use this doc + head 107.

## Trusted proxy / Cloudflare / Caddy

Behind Caddy (and optionally Cloudflare), the direct peer is the proxy. Set
`AUTH_TRUST_PROXY_HEADERS=true` and `AUTH_TRUSTED_PROXY_CIDRS` to the proxy/Cloudflare
egress CIDRs so the rate-limiter reads `CF-Connecting-IP` / the first `X-Forwarded-For`.
With trust off (or empty CIDRs) it safely falls back to the direct IP. Details:
`docs/ops/AUTH_M1_RUNTIME_CHECKLIST.md` (M1C section).

## Commands (run on the target host)

- **Migrate:** `make seed` → `alembic -c infra/alembic/alembic.ini upgrade head` (head `107`). Back up first (`make db-backup`).
- **Health:** `GET /api/health` (status/version/time; compose healthcheck) + `GET /api/scheduler/health`.
- **Frontend build:** `npm ci && npm run build` (in the web image) → `dist/` served by Caddy.
- **Backend tests:** `make test-auth` (auth/profile/feedback/report isolation suite, isolated test DB) and `make verify-deploy-safe`.
- **Preflight:** `make public-beta-preflight-prod` (exits 1 on any blocker).
- **Demand report:** `make feedback-report` (+ `-json`, `-7d`).
- **login_attempt pruning:** `make prune-login-attempts` (cron it on the host; no scheduler added).

## Provider credential checklist

| Provider | Required? | Purpose |
|---|---|---|
| Tiingo (`TIINGO_API_KEY`) | **required** | core price data. |
| FRED (`FRED_API_KEY`) | recommended | macro stage of the daily pipeline. |
| Polygon (`POLYGON_API_KEY`) | optional | company names / earnings / news (graceful-degrade). |
| Finnhub (`FINNHUB_API_KEY`) | optional | catalysts/news — **rotate before prod**. |
| Benzinga (`BENZINGA_API_KEY`) | optional | news + sentiment. |
| Tradier (`TRADIER_ACCESS_TOKEN`) | optional | options chain (sandbox; options are paper-only, dormant by default). |
| Gemini/Anthropic research keys | optional | research adapters (default OFF). |

Core paper-trading needs Tiingo (+ FRED for macro). Everything else degrades gracefully.

## Rollback plan

- DB: restore the pre-migrate `pg_dump` (`make db-backup` produced `.backups/devdb_*.sql`); or `alembic downgrade <prev>` (every M-series migration has a tested `downgrade`).
- App: redeploy the previous image tag (images are provenance-stamped with `GIT_SHA`); compose `up -d` the prior tag.
- Flags: any unsafe behavior can be reverted by env (`AUTH_DISABLED_LOCAL`/`DEMO_DEVICE_MODE`/`OPTIONS_ENABLED`) + restart — no code change needed.

## Post-deploy smoke checklist

1. `GET /api/health` → 200; `GET /api/scheduler/health` → schedules present.
2. `make public-beta-preflight-prod` on the host → OK (all tables, head 107, no unsafe flags).
3. Auth: signup → `/api/session` authenticated → own (non-shared) book; logout → `/api/session` false; bad password → 401 generic; **spoofed `X-Auth-User-Id` (no cookie) → shared demo, never a targeted user** (the M1A/M1C check, now with `DEMO_DEVICE_MODE=false`).
4. Cookie inspection: `arthos_session` is `Secure; HttpOnly; SameSite=Lax`.
5. Profile + feedback round-trip; `make feedback-report` shows the smoke signals.
6. Demo book intact (if seeded): `bc207e65` NAV ≈ $105,211, realized ≈ +$5,952, 30 open positions.
7. Watch worker heartbeats + the first 03:30-ET daily loop marker.
