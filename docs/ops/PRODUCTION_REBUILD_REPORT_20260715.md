# Production Rebuild Report — 2026-07-15

**Verdict: REBUILD COMPLETE — PRODUCTION ON 7e0af44, DB 109, ELITE FLAGS OFF.**
Explicitly authorized scope executed; migrations 110–121 were **NOT**
applied (Approval Point B remains not granted). All VM commands ran via
the vm-guard marker workflow; secrets redacted.

## Phase-0 freeze (17:41 UTC, `ptcgp-server`)

Baseline matched the approved state exactly: checkout `1d9b175` (dirty,
24 entries); DB `109_research_run`; P-1 orphans 0; `job_run` FK valid;
zero Elite env vars in api/worker containers; 6/6 services healthy;
running images api `6c92822f4a1b`, workers `173e16c16617` (started
2026-07-10), web `node:20-alpine` (bind-mount dev-server pattern —
"rebuild WebUI" = clean source + container recreate); disk 87%,
docker: 8 images/4.1GB, build cache 0.

## Disk safety + drift closure

- Removed: `.env.bak.1782170484`, `.env.bak.admin1` (after verifying
  `.env` active), dangling layers, post-build cache (~116MB), stale
  `PickPage.tsx.p1bak` via `git clean`.
- Protected & retained: `proddb_pre_p1_20260715.dump` (+checksum),
  orphan archive CSV (local), running images, new rollback tags, `.env`.
- **Drift archived**: `~/backups/checkout_drift_20260715.tar.gz` (124KB
  — all 24 modified/untracked entries) BEFORE checkout reset.
- Checkout reset: `git fetch` + `git checkout -f 7e0af44…` + scoped
  `git clean` → **clean tree at exactly `7e0af44`** (tree = the
  canonical deployment source; drift no longer part of runtime OR
  source).
- Deviation (documented): the <85% pre-build target was unreachable
  without deleting protected assets; build proceeded on 4.1GB free
  (sufficient). Post-build spike to 97% was recovered to **92%** by
  retiring the SUPERSEDED `rollback-stageb1` image generation (IDs
  recorded: api `6ea901549eaa`, workers `816c723d069f`) after the new
  deployment verified green — the `pre-elite-rebuild-20260715`
  generation is the active rollback. Real fix remains the OCI 30→50GB
  disk expansion (backlog).

## Rollback preparation (verified before replacement)

| Service | Running image (pre) | Rollback tag |
|---|---|---|
| api | `6c92822f4a1b` | `compose-api:pre-elite-rebuild-20260715` |
| worker-cron | `173e16c16617` | `compose-worker-cron:pre-elite-rebuild-20260715` |
| worker-tickloop | `173e16c16617` | `compose-worker-tickloop:pre-elite-rebuild-20260715` |
| web | generic `node:20-alpine` + source | source rollback = `checkout_drift_20260715.tar.gz` + `git checkout 1d9b175` |

Rollback procedure (unchanged DB): `docker tag compose-<svc>:pre-elite-rebuild-20260715 compose-<svc>:latest && docker compose --env-file .env -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.prod.yml up -d --no-deps <svc>`; for web, restore the checkout then force-recreate.

## Build (from the clean `7e0af44` checkout, GIT_SHA baked)

`docker compose … build api worker-cron worker-tickloop` → exit 0,
"no error strings" in the captured log. New images: api
`ae721095227b`, worker-cron `c7da1bbd46c9`, worker-tickloop
`c6c84a136340` (~1.05GB each, layers shared). Web has no built image by
design. Image-level preflight relied on the strongest available
evidence: G7 boot-on-109 (this exact code), V1 clone boots, and the
same-tree test gates — plus the staged replacement below acting as the
per-service canary.

## Replacement timeline (service-scoped, `--no-deps`)

| Time (UTC) | Action | Result |
|---|---|---|
| 22:11 | web `up -d` (no config delta — source already clean) | running |
| 22:12:23 | **api recreated** | healthy in 30s; `/api/health` 200 |
| 22:13:06 | **worker-cron + worker-tickloop recreated** | both healthy |
| 22:36:32 | **web force-recreated** (fresh npm install) | healthy; :5173 → 200 |

PostgreSQL + caddy untouched (`StartedAt` 2026-06-23 unchanged). Only
the four approved services carry new StartedAt values. No restart loops.

## Post-rebuild verification (all green)

- **DB**: `109_research_run`; P-1 orphans **0**; **zero** 110–121
  tables; `research_run` **0 before and after** smoke (write audit:
  zero Elite writes — at 109 the tables don't even exist to write to).
- **App** (local + public HTTPS `app.arthosfinance.xyz`): health,
  recommendations (list+limit), session (anon), canonical paper,
  model-portfolios, WebUI root — all **200**; public api health 200.
- **Elite-off proof**: `/api/agent/whoami`, `/api/theses`,
  `/api/admin/inbox/tasks`, `/api/admin/experiments/runs`,
  `/api/admin/lessons`, `/api/system/posture` — all **404**. WebUI has
  no Elite navigation (flag-gated route registration; `VITE_*` unset).
- **Logs (10m window)**: api/cron/tickloop/web — **0** error/traceback/
  missing-relation lines. No migration attempts, no external
  notification attempts.
- **Paper safety**: 54 `user:` books vs 19 engine-side books present;
  engine-set exclusion helpers pinned by the isolation suites run on
  this exact tree pre-deploy (12 + 149 passed); no trading job ran
  during the window; cost stamp + lease inert (columns/tables absent at
  109; flags absent).
- Env posture per container: zero Elite/Post-Elite variables present
  (grep across api/cron/tickloop = 0 matches); DATABASE_URL unchanged;
  ingest-contract posture unchanged.

## Residual risks

1. Disk 92% after recovery — schedule the OCI 30→50GB expansion; until
   then avoid keeping >1 rollback image generation.
2. Web remains a Vite dev-server pattern in prod (pre-existing
   architecture, unchanged by this rebuild) — a static-build web image
   is a future hardening item.
3. First post-deploy nightly (03:30 ET) should be watched — V7-style
   48h monitoring before any further change.

## What changed / what did not

Changed: 4 containers (new images/new source), prod checkout now clean
at `7e0af44`, 2 `.env.bak` files removed, stageb1 rollback tags retired
(recorded), drift archived. **Not changed**: PostgreSQL (data + service),
caddy, `.env`, DB schema (109), flags (none exist), git branches
(no force-push), P-1 backup + orphan archive retained.
