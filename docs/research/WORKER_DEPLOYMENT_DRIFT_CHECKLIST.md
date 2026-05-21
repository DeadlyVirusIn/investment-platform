# Worker deployment-drift checklist

**Status**: Diagnostic + checklist. NO broad sync implemented yet.
**Trigger**: 2026-05-19 sell-side outage caused by stale `paper_service.py` + `models.py` on `compose-worker-cron-1` / `compose-worker-tickloop-1`.

---

## What drifted

| File | API container | Worker containers (pre-fix) | Resolved this session? |
|------|-----------------------|------------------------------|--------------------------|
| `apps/api/src/domain/paper_trading/paper_service.py` | NEW (Phase L M079, requires `source` kwarg) | OLD (2026-04-19) | YES |
| `apps/api/src/db/models.py` | NEW (Phase L: `PaperEquitySnapshot.recorded_at` + `source`) | OLD (no recorded_at/source columns on ORM) | YES |

The two files are tightly coupled (paper_service writes ORM rows). Deploying one without the other left workers in a broken intermediate state. Both are now synced.

---

## Why Phase L deploy only reached the API container

Reconstructed root cause:

1. Phase L Day 1 (D1.2-D1.4) added M079 migration + ORM updates + `paper_service.snapshot_equity_now(*, source: str)` signature
2. The migration ran against the DB (schema columns added)
3. `models.py` and `paper_service.py` were `docker cp`'d to `compose-api-1` during D1.4 to make the API container see the new ORM
4. **No equivalent `docker cp` happened to the worker containers**
5. Worker containers continued running Docker-image-baked versions of these files (timestamp 2026-04-19)
6. Workers' import paths point to `/app/apps/api/src/...` — same paths, different content
7. Live cron at 2026-05-19 03:00 UTC tried to close positions, hit stale signature, "succeeded" silently because the stale script didn't pass `source=` either (compatible old/old)
8. After today's `paper_service.py`-only deploy: stale models.py blocked PaperEquitySnapshot construction → `TypeError`
9. After today's `models.py` deploy: full sell-side functional

---

## Why this happened operationally

- No volume mount for `apps/` directories in `infra/compose/docker-compose.yml`
- Files baked into worker Docker images during initial build
- `docker cp` is the team's manual deploy mechanism for hot-fixes
- During Phase L, deploys were optimized for "make the API container see the change" because that's where most tests hit
- Worker containers were assumed to be "behaviorally identical" but they weren't — they have separate file systems
- No tooling enforced parity

---

## Containers checked + status

| Container | Role | Reasoning modules | paper_service | models | Status |
|-----------|------|---------------------|----------------|--------|--------|
| `compose-api-1` | HTTP API | ALL NEW | NEW | NEW | Fully synced |
| `compose-worker-tickloop-1` | scheduler/tick loop | ALL NEW (per UI1 deploys) | NEW (today) | NEW (today) | Synced |
| `compose-worker-cron-1` | cron-fired jobs | ALL NEW (per UI1 deploys) | NEW (today) | NEW (today) | Synced |
| `compose-db-1` | PostgreSQL | n/a | n/a | n/a | Schema migrated |

---

## Files modified during Phase L (potential future drift candidates)

Per the forensic audit, 12 backend files were modified during Phase L. Their stale status on workers as of today:

| File | Likely impact if stale on worker |
|------|------------------------------------|
| `apps/api/src/db/models.py` | **FIXED today** — broke PaperEquitySnapshot writes |
| `apps/api/src/domain/paper_trading/paper_service.py` | **FIXED today** — broke snapshot_equity_now signature |
| `apps/api/src/api/paper.py` | API-only — workers don't import |
| `apps/api/src/domain/paper_trading/pending_replay.py` | Imported by replay path — possible drift |
| `apps/api/src/domain/ops/health_checks.py` | API-only — health endpoint |
| `apps/api/src/domain/briefing/narrative.py` | API-only — briefing endpoint |
| `apps/api/src/api/freshness.py` | API-only |
| `apps/api/src/api/alpha_lab.py` | API-only |
| `apps/api/src/api/operator.py` | API-only |
| `apps/api/src/api/performance_paper.py` | API-only |
| `apps/api/src/domain/performance/paper_performance.py` | Possibly imported by worker — risk of drift |
| `apps/api/src/domain/pnl/engine.py` | Possibly imported by worker — risk of drift |
| `apps/api/src/main.py` | API-only |
| `apps/api/src/config/__init__.py` | Possibly imported by worker — risk of drift |

The remaining 3-4 "possibly imported by worker" files are not currently exercised but could surface as drift later.

---

## Recommended worker-deploy verification check (manual)

For the worker containers, after ANY Phase L-related backend change:

```bash
# Quick diff check against running worker
for c in compose-worker-tickloop-1 compose-worker-cron-1; do
  for f in \
    apps/api/src/db/models.py \
    apps/api/src/domain/paper_trading/paper_service.py \
    apps/api/src/domain/paper_trading/auto_trader.py \
    apps/api/src/domain/paper_trading/paper_execution.py \
    apps/api/src/domain/paper_trading/pending_replay.py \
    apps/api/src/domain/performance/paper_performance.py \
    apps/api/src/domain/pnl/engine.py \
    apps/api/src/config/__init__.py
  do
    docker exec $c stat -c '%Y' /app/$f 2>/dev/null
  done
done
```

Compare timestamps to the host's `stat -c '%Y' <file>`. Mismatched timestamps = drift.

---

## How to prevent future divergence (do NOT implement yet)

Three options, in increasing scope:

### Option 1 — Documentation discipline (~0 effort)

- Maintain a `docs/ops/PHASE_L_DEPLOY_INVENTORY.md` listing every file modified during Phase L
- Any worker container restart MUST verify all files in the inventory match host
- Process: every Phase L PR adds modified files to the inventory

**Pros**: zero code change. Pros: catches obvious cases.
**Cons**: requires discipline. Easy to forget.

### Option 2 — `docker-compose.yml` volume mount for `apps/` (small effort)

- Add bind mount in `infra/compose/docker-compose.yml` for both worker services:
  ```yaml
  volumes:
    - ../../apps:/app/apps:ro
  ```
- Worker containers always read live host code
- A `docker restart` is enough to pick up changes; no `docker cp` needed

**Pros**: structural fix. No way to forget.
**Cons**: requires container restart on every change. Slightly slower startup. Read-only mount prevents containers from writing into `apps/` (good).
**Risk**: alters production-like fidelity (production usually doesn't mount source).

### Option 3 — Rebuild worker images on every code change (large effort)

- Rebuild `compose-worker-*` images whenever `apps/api/src/**` or `apps/worker/src/**` changes
- Use docker-compose `build` step
- Each restart pulls fresh baked image

**Pros**: closest to production
**Cons**: slow (~30-60s per change). Heavy for hot-fix iteration.

---

## Recommended posture (no implementation yet)

**Short-term**: Option 1 — document the deploy inventory. Continue using `docker cp` for hot-fixes. Add a `WORKER_DEPLOY_INVENTORY.md` to `docs/ops/` listing the 14 files above + any future additions.

**Medium-term**: Option 2 — add bind mount for `apps/`. Treats dev environment as "live-reload" rather than "image-baked". This is consistent with how the team currently iterates (frequent `docker cp` after edits).

**Production / long-term**: Option 3 — image rebuild. Only when deploying to a non-dev environment where rebuild fidelity matters.

DO NOT IMPLEMENT any of these yet. The sell-side recovery is the validated work. The deployment-hygiene improvements are a separate, deliberate decision.

---

## Checklist for any future Phase-L-class change

Before merging a backend change that affects worker code paths:

- [ ] Identify which files changed (`git diff --stat`)
- [ ] For each changed file under `apps/api/src/**`:
  - [ ] Is it imported by `apps/worker/src/**`? (`grep -rln "from apps.api.src.<file>" apps/worker/src`)
  - [ ] If yes, `docker cp` to both worker containers
  - [ ] If no, deploy to api container only
- [ ] Restart affected containers
- [ ] Run a manual integration test that exercises the changed path on the affected container
- [ ] Verify no exceptions in worker logs for 5 minutes after restart
- [ ] Verify `forbidden_phrases.py` + `resolver_anchor_lint.py` rc=0
- [ ] Verify snapshot suite 9/9 PASS

This checklist would have caught the sell-side breakage during Phase L D1.4 if it had been applied.

---

## Closing note

The drift bug was insidious because:
1. Worker job_run status reported `success` (old/old code path didn't fail)
2. No exception was raised that an operator would see
3. The artifact file was named per `as_of` date (overlapping previous runs)
4. Sells just... didn't happen, silently, for ~3 weeks

The two visible symptoms — "buys aren't producing trades" (the live anchor bug) and "sells aren't producing trades" (the deployment drift bug) — masked each other. Once buys started producing trades again, the sell-side gap became operationally critical.

Both bugs are now fixed. The lifecycle works.
