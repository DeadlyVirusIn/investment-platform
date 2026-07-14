# Production Readiness Audit — Onboarding/Portfolio Wave (2026-06-18)

Covers commits `89edd50 … f6b8c88` (14). Branch `mvp/ideas-you-can-follow`.
Net: **40 files, +2055/-133**. One migration. No destructive ops.

## Safety verdict: SAFE to deploy

- **Only schema change is migration 103** — `INSERT` one `job_schedule` cron row
  (`ON CONFLICT DO NOTHING`); downgrade deletes only that row. No DROP/ALTER on
  any data table.
- **No data migration alters user portfolios or trades.** Scanned the full diff:
  no `DROP TABLE` / `DELETE FROM paper_position|paper_trade|paper_portfolio|lot|
  transaction` / `TRUNCATE` / `ALTER … DROP`.
- `refresh_company_names` only `UPDATE asset SET name WHERE name IS NULL` —
  fills nulls, never overwrites, never touches portfolio/trade rows.
- `paper_canonical` read now get-or-creates an **empty** per-user book + commits
  — additive (creates empty rows); existing books/positions untouched.
- All API serializer changes (name, sector) are **additive fields**.

## Commit → change-type map

| Commit | Area | Migration | Env | Worker | Risk |
|---|---|---|---|---|---|
| 89edd50 | Plan cards (web) | — | — | — | none |
| 2038b46 | doc | — | — | — | none |
| c014577 | options lane (web) | — | — | — | none |
| 9d4646f | sector serialize (api) + jargon (web) | — | — | — | additive |
| 3b87add | company names (api+worker+web) | **103** | POLYGON_API_KEY (api had it) | **refresh_company_names job** | additive |
| 4bbc149 | deploy hardening | — | **POLYGON_API_KEY → workers** | — | config |
| 1261b3d | options universe (api) + enrich (web) | — | — | chain_ingest universe | additive |
| 786e91e | doc | — | — | — | none |
| 6a5be60 | strategy labels (web) | — | — | — | none |
| 15ab7b6 | P1 activation (web) | — | — | — | none |
| 538f5c2 | P0 onboarding (web) | — | — | — | none |
| af4b158 | portfolio resolution (api) | — | — | — | additive (read get-or-creates) |
| 5411a9a | spine + portfolio edu (web) | — | — | — | none |
| f6b8c88 | spine polish (web) | — | — | — | none |

## Migration list
- **103_company_name_refresh** (revises 102_portfolio_follow_fk) — adds the
  nightly `refresh_company_names` cron row. Additive, reversible.
- 100/101/102 predate this wave (already in the Private-Beta runbook).

## Env var changes
- `POLYGON_API_KEY` — now required on **api AND both workers**
  (`docker-compose.yml` updated; `4bbc149`). Already present for api.
  Without it: company-name backfill + nightly refresh no-op gracefully.
- No new secrets beyond Polygon (already held). Tiingo/FRED unchanged.

## Worker changes
- New job **`refresh_company_names`** (registry + scheduled by 103, cron
  `30 5 * * *`). Idempotent, null-safe.
- `chain_ingest.DEFAULT_UNIVERSE` expanded with 10 equities — affects the
  options chain-snapshot job (more symbols ingested in-hours). Additive.
- Worker image **must be rebuilt** to carry both, else the cron logs a
  no-handler and the universe stays ETF-only.

## Deployment dependency graph (safe order)

```
1. Set env       POLYGON_API_KEY on api + worker-tickloop + worker-cron
2. Migrate       alembic upgrade head   → 103 (additive cron row)
3. Build images  api, worker-tickloop, worker-cron, web   (must carry this code)
4. Deploy        up -d (recreate) api + workers + web
5. Backfill      run refresh_company_names ONCE (fills asset.name)   [in-hours not required]
6. Smoke         per-user books, name/sector in payloads, onboarding surfaces
```
Frontend is independent (names/sector degrade to ticker-only if the api lags).

## Rollback plan
- **Code:** redeploy the prior api/worker/web images; or `git revert` the range.
- **Schema:** `alembic downgrade 102_portfolio_follow_fk` — removes only the
  `refresh_company_names` cron row. No data touched.
- **Data:** backfilled `asset.name` and per-user empty books are additive — safe
  to leave or prune; no portfolio/trade data was modified, so nothing to undo
  there.
- **Env:** removing `POLYGON_API_KEY` from workers reverts the nightly job to a
  graceful no-op.

## Production deployment checklist
1. [ ] `.env` on prod has `POLYGON_API_KEY` (+ TIINGO/FRED as before).
2. [ ] `POLYGON_API_KEY` reaches api, worker-tickloop, worker-cron (compose).
3. [ ] `alembic -c infra/alembic/alembic.ini upgrade head` → head `103`.
4. [ ] Build api + worker-tickloop + worker-cron + web from this commit.
5. [ ] `up -d` recreate all four; health green.
6. [ ] Run `refresh_company_names` once (worker exec) → asset.name populated.
7. [ ] Smoke:
   - `GET /paper/canonical/stock` with two `X-Auth-User-Id` → **different**
     `portfolio_id`, both 0 positions / `no_live_snapshot` (never the shared
     Replay-Recovery id).
   - `GET /recommendations?latest=true` → items carry `name` + `sector`.
   - Web `/v2/discover` → progress spine + Continue-path card; cards show
     `Name (TICKER)` + sector chip.
8. [ ] Existing users: spot-check one known device → its own book, positions
   intact (no regression).
9. [ ] **Cache headers** — the edge/Caddy must serve `index.html` with
   `Cache-Control: no-cache` (so browsers always revalidate the HTML and pick up
   new asset references), while the hashed `/assets/*.js` / `*.css` bundles stay
   long-cacheable (`Cache-Control: public, max-age=31536000, immutable`). Vite
   content-hashes the bundles, so this prevents users seeing a stale layout from
   an old cached HTML. No in-app version checking is used — this is purely an
   edge cache-header policy.

## Known non-blockers
- The read endpoint now writes (get-or-create + commit on GET) — idempotent,
  creates only empty portfolio rows. Fine for beta scale.
- Anonymous callers (no header) still resolve the shared demo book — intentional.
