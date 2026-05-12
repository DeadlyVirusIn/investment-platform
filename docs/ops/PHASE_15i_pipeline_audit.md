# Phase 15i — Pipeline & ML Lifecycle Operational Audit

**Date:** 2026-05-11 (Monday)
**Branch:** `phase-1/ledger`
**Audit type:** READ-ONLY discovery. No code, scheduler, schema, or config changes. Code-walk evidence only. Pure proposal output for §§4–10.
**Companion document:** `docs/ux/PHASE_15g_freshness_audit.md` (UI-side freshness audit completed earlier today; live endpoint probes from there are referenced rather than re-probed).

---

## 1. TL;DR — operational state on 2026-05-11

**Headline answer: the daily pipeline almost certainly did not run for trading-date 2026-05-11, and the architecture explains why this is structurally invisible.**

There is **no scheduled run that fires on Monday for Monday data.** The system has two parallel schedulers and both are calibrated for *prior-day* trading data, not same-day:

1. **Supercronic** in the `worker-cron` container fires `/app/scripts/run_daily_loop.sh` at **03:30 America/New_York, Tuesday–Saturday** (`infra/docker/worker.crontab:11`). On Monday morning at 03:30 ET it runs the loop for last Friday's bars. It does not run again until Tuesday 03:30 ET, which is when Monday's trading-day pipeline would actually execute.
2. **DB-backed tick-loop** in the `worker-tickloop` container polls `job_schedule` every 60 s (`apps/worker/src/scheduler/tick_loop.py:27`) and runs registered jobs whose `next_run_at <= now`. The seeded crons are **22:00, 22:30, 23:00, 23:30 ET Monday–Friday** (`scripts/seed_symbols.py:31-52`).

Neither scheduler matches the "16:30 ET / 20:30 UTC" cadence asserted in the 15g audit doc. **No schedule with that timing exists in the repo.** The 15g doc was working off folklore, not code.

The 22:00 ET tickloop firing on Monday WOULD update price/recommendations for Monday's data — but the 15g audit was performed at 23:37 UTC = 19:37 ET, **before** the 22:00 ET tickloop was due to fire. So the 15g findings ("Monday pipeline didn't run") are consistent with "no scheduled run had yet fired for Monday" rather than with "a scheduled run failed". This is a different root cause than the 15g doc inferred.

Evidence that the daily pipeline did not run today (2026-05-11):

- `/api/recommendations` first pick `generated_at = 2026-05-09T02:30 UTC` (15g §2.2). That is the Saturday 03:30 ET worker-cron run for Friday's bars. There has been no recommendation generation since.
- `/api/paper/summary as_of_date = 2026-05-09` (Saturday).
- `/api/paper/state as_of_date = 2026-05-08` (Friday).
- `/api/paper/equity` last point = `2026-05-09`.
- Health markers `/tmp/last_daily_loop_success` and `/tmp/last_daily_loop_failure` (`scripts/run_daily_loop.sh:17-18`) — written by the cron loop; visible only via `/api/scheduler/health` (`apps/api/src/api/scheduler_health.py:97-100`).
- The `daily_run_status` table (`infra/alembic/versions/016_daily_run_status.py`) is keyed by `run_date PRIMARY KEY` and would carry one row per trading day — not probed live but is the canonical store for tickloop-style daily runs.

**Trigger model in plain English.** Today's price bars are not finalized until ~16:00 ET. The 22:00 ET tickloop ingests them, the 22:30 / 23:00 / 23:30 jobs cascade. Then on Tuesday at 03:30 ET the cron container runs the umbrella `run_daily_loop.sh` which performs the engine pipeline, paper-trading run, alpha nightly, ML shadow training, hybrid monitor — and persists the last-success marker. **So "today's data lands tonight, today's full daily-loop runs tomorrow morning."** This is operationally normal but it means a 15g-style probe at 19:37 ET on a Monday will *always* see Friday/Saturday data — and there is no UI affordance that explains this to the user.

**Net findings:**

- Two schedulers run side-by-side; neither has a single canonical "did the pipeline run today" surface.
- A `daily_run_status` table exists and is the closest thing to a run ledger, but only the `daily_runner.py` orchestrator writes it (`apps/api/src/domain/ops/daily_runner.py:74-105`); the `run_daily_loop.sh` cron does NOT write it. The cron writes `/tmp` markers instead.
- A second table, `paper_run_log` (`infra/alembic/versions/036_phase_paper_run_log.py`), is written by `run_paper_daily.py` and stores per-day paper trading state — but only for the paper subsystem.
- There is no unified ledger covering ingest → engine → paper → ML → shadow with per-stage rows.
- There is no `/api/freshness` endpoint. There is `/api/jobs/health`, `/api/jobs/status`, `/api/scheduler/health` — three nominally-overlapping surfaces, none of which map cleanly to a per-channel freshness contract.

The product can show Friday's reality on a Monday evening without lying about which scheduler ran or didn't, because the scheduler ledger and the freshness-presentation layer are not joined.

---

## 2. Scheduling reality — discovered by code inspection

Each numbered question gets a grounded answer. "No evidence found in repo" is itself a finding.

### 2.1 — What scheduler exists?

**Two coexisting schedulers in production:**

(a) **Supercronic** inside the `worker-cron` Docker container (`infra/docker/worker.Dockerfile:11-15` installs supercronic v0.2.29; line 42 sets `CMD ["supercronic", "-quiet", "/app/crontab"]`). Crontab is `infra/docker/worker.crontab`. This is process-level user-space cron with no syslog dependency. PID 1 of the container.

(b) **DB-backed Python tick-loop** inside the `worker-tickloop` container (`infra/compose/docker-compose.yml:113-118` runs `python -m apps.worker.src.main`, which calls `apps/worker/src/main.py:18 asyncio.run(run())`, which is `apps/worker/src/scheduler/tick_loop.py:170 run()`). This polls the `job_schedule` Postgres table every 60 s for due jobs.

These two schedulers do not share state. They live in separate containers, with separate restart policies, and write to disjoint surfaces.

### 2.2 — What triggers daily pipeline?

(a) **Cron expression `30 3 * * 2-6`** in `infra/docker/worker.crontab:11`. This fires `/app/scripts/run_daily_loop.sh` once per Tuesday-through-Saturday morning (container `TZ=America/New_York`, Dockerfile line 39).

(b) The tick-loop fires individual jobs whose seeded crons are at `22:00`, `22:30`, `23:00`, `23:30 Mon–Fri ET` (`scripts/seed_symbols.py:31,41,46,51`).

### 2.3 — What time does it run?

| Mechanism | Local (ET) | UTC | Days |
|---|---|---|---|
| `worker-cron` umbrella loop | 03:30 | 07:30 (08:30 in EST) | Tue–Sat |
| `ingest_prices_daily` (tickloop) | 22:00 | 02:00 (next day) | Mon–Fri |
| `run_recommendations_for_all_accounts` | 22:30 | 02:30 (next day) | Mon–Fri |
| `score_recommendation_outcomes` | 23:00 | 03:00 (next day) | Mon–Fri |
| `run_paper_trading` (tickloop) | 23:30 | 03:30 (next day) | Mon–Fri |
| `v2_promotion_snapshot` | Mon 00:15 | Mon 04:15 (or 05:15 EST) | Mon |

There is no 16:30 ET / 20:30 UTC schedule of any kind. **No evidence found in repo** for the cadence the 15g audit asserted.

Note that `run_paper_trading` (tickloop) ≠ `run_daily_loop.sh` (cron). The cron umbrella calls the heavier `scripts/run_paper_daily.py` (Phase OPS1, `Makefile:123`) which is a much wider script (ingest macro, gates, selector, paper portfolio, shadow eval). The tickloop's `run_paper_trading` is the older, lighter `apps/worker/src/jobs/run_paper_trading.py` runner. They are not the same path.

### 2.4 — Which container/process owns it?

| Job | Container | Process |
|---|---|---|
| Daily umbrella loop | `worker-cron` | `supercronic` (PID 1) → bash `/app/scripts/run_daily_loop.sh` |
| All tickloop jobs | `worker-tickloop` | `python -m apps.worker.src.main` |
| API surface for both | `api` | `uvicorn apps.api.src.main:app` |

`worker-cron` and `worker-tickloop` are built from the same `infra/docker/worker.Dockerfile` — they differ only in `command:` (compose lines 118 and the cron container which falls back to the Dockerfile CMD).

### 2.5 — What script/function is supposed to run? (entry point file:line)

| Layer | Entry point |
|---|---|
| Cron umbrella shell | `scripts/run_daily_loop.sh:96-217` |
| Engine pipeline (stage 0) | `scripts/run_engine_pipeline.py` (`run_daily_loop.sh:111`) |
| Market-data precheck | `scripts/check_market_data_ready.py:150 main()` |
| Paper daily | `scripts/run_paper_daily.py` (`run_daily_loop.sh:162-167`) |
| Alpha nightly | `apps.api.src.jobs.alpha_nightly` |
| ML shadow | `apps.api.src.jobs.nightly_ml_shadow:main` |
| Hybrid monitor | `apps.api.src.jobs.ml_hybrid_monitor_nightly:main` |
| Shadow strategy | `scripts.run_shadow_strategy` |
| Safe gate evolution shadow | `scripts.run_safe_gate_evolution_shadow` |
| Tickloop entrypoint | `apps/worker/src/main.py:14 main()` → `apps/worker/src/scheduler/tick_loop.py:170 run()` |
| Tickloop job dispatcher | `apps/worker/src/jobs/registry.py:246 REGISTRY` |
| Live-forward orchestrator (tickloop-callable, also CLI-callable) | `apps/api/src/domain/ops/daily_runner.py:130 run_daily_pipeline()` (also `apps/worker/src/jobs/run_daily_pipeline.py:16 run_daily_pipeline_job()`) |

Note the duplication. The cron loop calls `scripts/run_paper_daily.py` directly. The tickloop calls `apps/worker/src/jobs/run_paper_trading.py` (different code path). The Phase 11 `daily_runner.py` orchestrator is callable from CLI (`scripts/run_daily.py`) and from the tickloop (registry entry `run_daily_pipeline`) but is **not** invoked by the cron umbrella. Three independent definitions of "the daily pipeline" coexist, with no single name.

### 2.6 — What logs prove it ran?

For the cron umbrella:
- Container stdout (supercronic forwards) — visible via `docker logs compose-worker-cron-1`.
- Inside the container: `/tmp/last_daily_loop_success` (UTC ISO timestamp) and `/tmp/last_daily_loop_failure` (`run_daily_loop.sh:17-18`).
- The `worker_cron_tmp` Docker volume bind-mounts `/tmp` (`docker-compose.yml:188-189`) so the API container can read it at `/var/scheduler_markers` (`docker-compose.yml:91`, env `SCHEDULER_MARKER_DIR=/var/scheduler_markers`).
- `paper_run_log` table — written by `scripts/run_paper_daily.py` (writer at `apps/api/src/data/strategy/paper_run_log.py write_paper_run_log`).

For the tickloop:
- `job_run` table (`apps/api/src/db/models.py:570-585`) — one row per execution, status in {`running`, `success`, `error`}, `error_message` capture (`tick_loop.py:65-110`).
- `job_schedule.last_run_at` and `job_schedule.next_run_at` (`models.py:554-555`).
- Container stdout (loguru → stderr).

For the live-forward orchestrator (`daily_runner.py`):
- `daily_run_status` table (`infra/alembic/versions/016_daily_run_status.py`), one row per `run_date`, with `summary_json` carrying per-stage detail.

There is **no single log** that proves "the entire daily intent for date X completed." The closest is `daily_run_status.run_date` but it is only written by `daily_runner.run_daily_pipeline()`, which the cron umbrella does not call.

### 2.7 — What database rows prove it ran?

| Stage / artifact | Table | Freshness column |
|---|---|---|
| Price ingest | `price_bar` | `ts` (per bar) |
| Engine context | `context_daily` | `as_of_date` |
| Regime | `regime_snapshot` | `as_of_date` (PK) |
| Factor | `factor_snapshot` | `as_of_date` |
| Candidates | `candidate_idea` | `as_of_date` |
| Recommendations | `recommendation` | `generated_at` (`db/models.py:311-313`) |
| Paper run | `paper_run_log` | `run_date` (UNIQUE), `started_at`, `finished_at`, `status` |
| Paper trade | `paper_trade` | `fill_ts` |
| Paper equity | `paper_equity_snapshot` | `as_of_date` |
| Tickloop job | `job_run` | `started_at`, `finished_at` |
| Daily-runner | `daily_run_status` | `run_date` PK, `started_at`, `finished_at` |
| ML shadow | `ml_model_run` | `created_at`, `train_end_date`, `test_end_date` |
| Hybrid snapshot | `ml_hybrid_performance_snapshot` | `as_of_date`, `window_days` |
| Options chain | `options_chain_snapshot`-family tables | `snapshot_at_utc` |
| Shadow run | `shadow_run_log` | (per `models.py:1113`) |

The freshness-by-table evidence is rich but scattered. There is no view or summary that joins them.

### 2.8 — What endpoints reflect it ran?

Existing:
- `/api/jobs/health` and `/api/jobs/status` — read `JobSchedule` + `JobRun` (`apps/api/src/api/jobs.py:28-128`). Tickloop only.
- `/api/scheduler/health` — reads tickloop `job_schedule` + `job_run` AND the `/tmp` markers via `MARKER_DIR` mount (`apps/api/src/api/scheduler_health.py:69-118`). Closest single-pane-of-glass.
- `/api/paper/summary` — surfaces last paper-run `as_of_date` and `pipeline_status` (per 15g §2.1).
- `/api/recommendations` — recommendations with `generated_at` per row (per 15g §2.2).
- `/api/health` (FastAPI built-in) — only confirms the API process is alive (`apps/api/src/main.py:280-286`).
- `/api/system/health` — returns `overall: "healthy"` with `items=[]` (per 15g §2.5). **Trust hazard already documented.**

Missing (per 15g §2.7):
- `/api/freshness` — 404
- `/api/today` — 404
- `/api/now` — 404
- `/api/ops/status` — 404 (despite a `/api/jobs/status` route that nearly answers; routing-name mismatch)

### 2.9 — What happens on failure?

Cron umbrella (`run_daily_loop.sh`):
- `set -u` is on, but `set -e` is **deliberately off** (line 14). Each job is wrapped in `set +e ... rc=$? ... set -e 2>/dev/null || true`.
- Required vs optional taxonomy is enforced by `run_job` (lines 49-94). A required job failure increments `FAILED_REQUIRED`; on completion, the script writes `/tmp/last_daily_loop_failure` and exits 1. Otherwise writes `/tmp/last_daily_loop_success` and exits 0.
- Optional jobs may skip silently when their Python module is missing (lines 60-69 — heuristic via `importlib.util.find_spec`).

Tickloop (`tick_loop.py`):
- `_execute_job` (lines 53-112) wraps the call in try/except. On exception, status becomes `error`, the traceback goes into `job_run.error_message`, and the loop continues.
- The outer `_tick` is also try/except (lines 181-184) — single tick failure does not kill the loop.

Daily-runner (`daily_runner.py`):
- Each stage in its own try/except (lines 200-225). A stage crash sets `stage_failed`, marks `final_status="failed"`, and re-raises to the outer except (line 316) which finalizes the row. Then `dispatch(alerts)` (line 331).
- `Alert(severity, code, message, payload)` system in `apps/api/src/domain/ops/alerting.py`.

**Failure surfacing is internally robust per layer, but no layer reaches a user-visible UI gracefully.** A required cron-loop job failing produces (a) a `/tmp/last_daily_loop_failure` marker, (b) an exit code 1, (c) container stdout. None of these reach `/api/system/health` (which returns hard-coded healthy).

### 2.10 — Is there retry?

No. None of the three layers retries individual stages. The cron loop runs each stage exactly once. The tickloop runs each job exactly when due — if it fails, the next due fire is the next cron interval (typically 24 hours later). The daily-runner has no retry on stage crash; it raises and finalizes.

`scripts/check_market_data_ready.py:191-198` returns exit 3 (NOT-ready) which the cron loop treats as "skip paper_daily this run." That is a *defer*, not a retry — and there is no rescheduled retry within the same day.

### 2.11 — Is there alerting?

There is an alerting layer in `apps/api/src/domain/ops/alerting.py` (`SEV_INFO`, `SEV_WARNING`, `SEV_CRITICAL`, `Alert`, `dispatch`) used by `daily_runner.py`. The cron umbrella does NOT integrate with this layer — it writes `/tmp` markers and exits.

`scripts/daily_health_alerts.sh` is a host-side bash check that reads `/api/scheduler/health`, `/api/ml/hybrid/status`, and the DB directly via `docker exec ... psql` to print INFO/WARN/ALERT lines. Exit code 0/1/2. **It is not invoked from any cron — only manual or ad-hoc.** No mention in `run_daily_loop.sh` or `worker.crontab`.

So: there is alerting *plumbing* but no alerting *delivery* configured anywhere. **No evidence found in repo** of a Slack / email / PagerDuty / webhook destination wired into `dispatch()`.

### 2.12 — Is there idempotency?

Partial:
- `daily_runner.run_daily_pipeline` enforces a per-`run_date` lock via `DailyRunStatus.run_date PRIMARY KEY`; second invocation with same date and existing `running` or `success` status raises `AlreadyRan` (`daily_runner.py:163-176`). `--force` overrides.
- `paper_run_log` has `UniqueConstraint(run_date, name="ux_paper_run_log_run_date")` (alembic 036:55-56). One row per `run_date`. `scripts/run_paper_daily.py` upserts; `--force-recompute` overwrites.
- `recommendation` has `ux_recommendation_snap` unique on `(asset_id, model_version, snapshot_hash)` (`models.py:328-332`). Idempotent on identical input snapshots.
- Tiingo backfill uses ON CONFLICT DO NOTHING (`apps/worker/src/jobs/registry.py:117`).
- Options chain ingest uses INSERT ... ON CONFLICT DO NOTHING on natural key (per `options_chain_snapshot.py:30-32` docstring).

But:
- The tickloop `run_paper_trading` job has no per-day lock visible in this read.
- The cron umbrella shell has no in-script per-`as_of_date` ledger write — its only "did this date run" memory is `/tmp/latest_bar_date` and the marker files. Re-running it back-to-back would re-execute every stage.

### 2.13 — Is there lock/overlap protection?

- Cron umbrella: `flock -n 9` on `/tmp/quant_daily_loop.lock` (`run_daily_loop.sh:30-37`). Two concurrent cron fires cannot overlap — second exits cleanly. Lock cleared via `trap 'flock -u 9' EXIT`.
- Tickloop: an `asyncio.Semaphore(_MAX_CONCURRENT=3)` (`tick_loop.py:28,118`). Bounds within-tick parallelism; does NOT prevent two ticks from launching the same just-due job (60 s polling vs sub-second job-due window).
- daily-runner: per-`run_date` row lock (see §2.12).

There is no cross-scheduler coordination. The tickloop's `run_paper_trading` could in principle run at 23:30 ET on the same day that the cron's `run_paper_daily.py` runs at 03:30 ET on the next morning, hitting the same `paper_run_log` row. The 24-hour window hides the race, but it is not architectural — it is timetable-only.

### 2.14 — Is there a market-calendar guard?

Partial:
- `daily_runner._is_trading_day(d)` checks `d.weekday() < 5` (Mon–Fri only) — **no holiday calendar** (`daily_runner.py:69-71`, comment explicitly: `"No holiday calendar — acceptable simplification."`).
- Cron umbrella: weekday gating happens via cron `dow=2-6` (Tue–Sat). No holiday awareness.
- `check_market_data_ready.py` does not consult a calendar — it checks "is there a price_bar within `MAX_BAR_AGE_CAL_DAYS=4` days?" (line 33). This indirectly absorbs holidays because Tiingo bars only exist on trading days.

So: weekday filtering is enforced; US holiday filtering is not. On a US holiday, the cron will fire and the engine will skip cleanly because `check_market_data_ready` will return 3 (no fresh bar). The cleanliness depends on the precheck, not on a holiday calendar.

### 2.15 — Is there weekend/holiday behavior?

- Saturday cron fire (03:30 ET) processes Friday's bars — explicitly designed (`worker.crontab:7-9` comment).
- Sunday: no cron fire (cron `dow=2-6` excludes Sunday).
- Tickloop jobs do not fire weekend (`cron_expr=* * * * 1-5` for all five seeded jobs in `seed_symbols.py:31,41,46,51`).
- Holidays: see §2.14. No explicit handling.
- `daily_runner` returns `status="skipped"` and emits `SEV_INFO` "market_closed" alert when `_is_trading_day(d)` is False (`daily_runner.py:147-158`). Writes one row to `daily_run_status`.

### 2.16 — Is ML training separate from daily inference?

Yes, partially. The `nightly_ml_shadow` job (called from `run_daily_loop.sh:181`) runs *training* on accumulated labeled data (`apps/api/src/jobs/nightly_ml_shadow.py:39-65`). The result is stored in `ml_model_run` and the trained model artifact in the file-based registry (`models/model_registry.json`). **Inference at decision time** is separate — it runs in the request path of `apps/api/src/ml/shadow/scorer.py` and `runtime.py`. The two are joined only by `model_id` written to the registry.

ML is **strictly advisory** — `ML_CAN_AFFECT_TRADES=false` is enforced by `daily_health_alerts.sh:144-149` and the `ml_hybrid_monitor_nightly.py` snapshot logic. Training is daily; promotion to "execution-affecting" is gated by an operator-approval flag (`ML_PROMOTION_REQUIRE_OPERATOR_APPROVAL=true` in compose).

### 2.17 — Are options pipelines separate?

Yes.
- `apps/worker/src/jobs/options_chain_snapshot.py` is a job *function*, but its docstring (lines 1-13) explicitly states: **"NOT yet registered in registry / cron."** It exists as code only.
- The chain ingest is therefore not running on any schedule. The options endpoints (per 15g §2.6) still serve data, which suggests historical chain snapshots were ingested manually or by a one-off backfill, not by an active scheduled job.
- `scripts/run_options_paper_exec.py` is **operator-triggered only**, with hard `OPTIONS_PAPER_EXEC_CONFIRM` env confirmation gating (`run_options_paper_exec.py:14-16, 30-31`). Default is dry-run.
- `scripts/run_options_paper_eval.py`, `scripts/run_options_shadow_eval.py`, `scripts/run_options_promotion_eval.py` exist but **none are registered** in any cron or tickloop registry.
- `scripts/run_post_ingest_paper_cycle.py` is operator-triggered post-ingest cleanup; not scheduled.

So: options is **observably unscheduled**. The empty `as_of` on every options endpoint (15g §2.6) is consistent with this — nothing is updating freshness because nothing is running on a clock.

### 2.18 — Are paper trade fills separate?

Yes — multi-tier:
- Cron umbrella → `scripts/run_paper_daily.py` → calls a frozen-strategy adapter, updates portfolio, may emit fills.
- Tickloop → `apps/worker/src/jobs/run_paper_trading.py` → older lightweight runner.
- Replay → `scripts/replay_paper_*.py` (multiple files in `scripts/`) — operator-triggered for missing days.
- Post-ingest cleanup → `scripts/run_post_ingest_paper_cycle.py` (not scheduled).

The fact that paper fills are touched by *four* code paths is a known operational hazard (the 2026-05-08 trust-fix volume mount comment in `docker-compose.yml:135-141` documents the consequence — JSONL skip files were disappearing because writers and readers used different filesystems).

### 2.19 — Are shadow evaluations separate?

Yes:
- ML shadow training: `apps/api/src/jobs/nightly_ml_shadow.py` (called from cron umbrella).
- Strategy shadow: `scripts/run_shadow_strategy.py` (called from cron umbrella, optional).
- Safe gate evolution shadow: `scripts/run_safe_gate_evolution_shadow.py` (called from cron umbrella, optional).
- Options shadow: `scripts/run_options_shadow_eval.py` (NOT scheduled).
- Hybrid monitor: `apps/api/src/jobs/ml_hybrid_monitor_nightly.py` (called from cron umbrella).

So: stock-side shadow evaluations DO run via cron umbrella; options-side shadow evaluation does NOT.

### 2.20 — Are freshness timestamps propagated?

Inconsistently. Per 15g §2:
- `recommendation.generated_at` exists per row but the derived `pick.stale_data` flag is unreliable.
- `paper_run_log.run_date` exists; `/api/paper/summary` surfaces `as_of_date`.
- Options endpoints expose **no** `as_of` / `generated_at` (15g §2.6).
- `/api/system/health` exposes `as_of=null` and `items=[]`.
- `/api/market/events` is the lone consistently-fresh channel — and it computes per-request, not from a stored timestamp.

The data layer carries timestamps; the API layer often loses them; the UI has no global "last cycle" reference. No DB row exists that says "the entire pipeline completed at X" for any single timestamp.

---

## 3. Per-stage daily run evidence for 2026-05-11

For each stage: did it run today? what artifact would prove a run? when was the last successful run? what script owns it?

(All "last successful run" inferences below derive from the live evidence captured in the 15g audit at 23:37 UTC. Where the 15g audit did not surface a value, this audit marks it UNKNOWN rather than re-probing.)

### 3.1 Market data ingestion (price bars, EOD)

- **Today?** UNKNOWN — but the 22:00 ET tickloop firing was due *after* the 15g probe at 19:37 ET, so likely not yet run at audit time. Should run tonight at 22:00 ET if the worker-tickloop container is up.
- **Artifact:** `price_bar.ts` for any in-universe symbol on 2026-05-11.
- **Last successful run:** `/api/jobs/status.latest.price_bar_ts` would answer; not surfaced in 15g audit. The 22:00 ET Friday run (2026-05-08) is the most recent guaranteed one.
- **Owner:** `apps/worker/src/jobs/ingest_prices_daily.py` (Tiingo → Yahoo fallback). Job name `ingest_prices_daily`, cron `0 22 * * 1-5`.

### 3.2 Macro + regime context update

- **Today?** NO — Saturday cron run (2026-05-09 03:30 ET) processed Friday's bars; no run since.
- **Artifact:** `context_daily.as_of_date`, `regime_snapshot.as_of_date`.
- **Last successful run:** Inferable from `/paper/state.as_of_date = 2026-05-08` (15g §2.1) — context_daily for 2026-05-08 is the most recent.
- **Owner:** `scripts/run_engine_pipeline.py` (cron umbrella stage 0) → calls `compute_regime_snapshot` and a macro-backfill stub. ALSO callable as tickloop registry `compute_regime_snapshot`.

### 3.3 Event ingestion (catalysts / market events)

- **Today?** YES — `/api/market/events.generated_at = 2026-05-11T23:37 UTC` (15g §2.3).
- **Artifact:** Per-request computation; NOT persisted to a single freshness column.
- **Last successful run:** Always-fresh per request (SEC EDGAR + Polygon + Benzinga adapters in `apps/api/src/domain/market_events/service.py`).
- **Owner:** Live request handler `/api/market/events` (`apps/api/src/api/market_events.py:28-37`). No scheduled fetch.

### 3.4 Feature generation

- **Today?** NO — same answer as §3.2; features build on top of macro + regime + price_bar.
- **Artifact:** `factor_snapshot.as_of_date`.
- **Last successful run:** 2026-05-08 (Friday), per same chain of reasoning.
- **Owner:** `compute_factor_snapshots` (registry job; also called by `run_engine_pipeline.py`).

### 3.5 Recommendation generation

- **Today?** NO — `/api/recommendations` first pick `generated_at = 2026-05-09T02:30 UTC` (15g §2.2). That is the Saturday 03:30 ET cron processing Friday's bars.
- **Artifact:** `recommendation.generated_at`.
- **Last successful run:** 2026-05-09T02:30 UTC.
- **Owner:** `apps/worker/src/jobs/registry.py:142 run_recommendations_for_all_accounts()` (tickloop job). Cron `30 22 * * 1-5`. **Should also have run last Friday at 22:30 ET (= Sat 02:30 UTC) — which is the timestamp we see.** Confirms the tickloop fired Friday but has not fired again since (because Saturday and Sunday are excluded by `1-5` and Monday's 22:30 ET is still in the future at audit time).

### 3.6 Signal ranking

- **Today?** NO — same dataset as §3.5.
- **Artifact:** `ranked_signal` table (alembic 020).
- **Last successful run:** 2026-05-09 batch.
- **Owner:** Part of `run_recommendations_for_all_accounts` (downstream).

### 3.7 Paper portfolio valuation

- **Today?** NO — `/api/paper/summary as_of_date = 2026-05-09`, `/api/paper/equity` last point `2026-05-09` (15g §2.1).
- **Artifact:** `paper_equity_snapshot.as_of_date`.
- **Last successful run:** 2026-05-09 (Saturday cron processing Friday's bars).
- **Owner:** `scripts/run_paper_daily.py` (cron stage 1) AND `apps/worker/src/jobs/run_paper_trading.py` (tickloop).

### 3.8 Paper trade fill

- **Today?** NO — no paper trades since Friday's session (15g §2.1).
- **Artifact:** `paper_trade.fill_ts`.
- **Last successful run:** Last Friday's session, processed Saturday morning.
- **Owner:** Multi-tier — see §2.18.

### 3.9 Risk calculation

- **Today?** UNKNOWN — `/api/options/risk-summary` returns data with no `as_of` (15g §2.6). Risk surface is observably stale by the same logic chain as §3.7 (depends on portfolio valuation), but the endpoint cannot prove it.
- **Artifact:** No persistent freshness column; computed live from `paper_trade` + `options_paper_trade` joins.
- **Last successful run:** UNKNOWN per endpoint shape; structurally tied to last paper run.
- **Owner:** `apps/api/src/options/routes_readonly.py` aggregations.

### 3.10 Options chain update

- **Today?** UNKNOWN — `/api/options/strategies` and friends return data with no `as_of` (15g §2.6). The job function exists (`apps/worker/src/jobs/options_chain_snapshot.py`) but is **not registered** anywhere (line 8-13 docstring confirms).
- **Artifact:** `options_chain_snapshot.snapshot_at_utc`.
- **Last successful run:** UNKNOWN — would require querying the DB directly. Likely stale; possibly from a one-off backfill weeks ago.
- **Owner:** `run_options_chain_snapshot_job()` (defined but unscheduled).

### 3.11 Options strategy evaluation

- **Today?** NO — no scheduler runs `scripts/run_options_paper_eval.py` or related.
- **Artifact:** `options_paper_strategy_*` tables (alembic 062-063).
- **Last successful run:** UNKNOWN — operator-triggered.
- **Owner:** `scripts/run_options_paper_eval.py`, `scripts/run_options_shadow_eval.py`.

### 3.12 Shadow evaluation

- **Today?** PARTIAL — strategy shadow + safe-gate-evolution shadow + ML shadow are all called from the cron umbrella (`run_daily_loop.sh:181-208`), so the most recent run was Saturday 03:30 ET. Since then: nothing.
- **Artifact:** `ml_model_run`, `paper_shadow_log`, `safe_gate_evolution_shadow`.
- **Last successful run:** 2026-05-09 ~03:30 ET (Saturday morning Friday-data pass).
- **Owner:** Multiple — see §2.19.

### 3.13 ML training

- **Today?** NO — `nightly_ml_shadow` runs from cron umbrella; last fire was Saturday morning.
- **Artifact:** `ml_model_run.created_at`, `ml_model_run.train_end_date`.
- **Last successful run:** 2026-05-09 ~03:30 ET.
- **Owner:** `apps/api/src/jobs/nightly_ml_shadow.py:39-65`.

### 3.14 Freshness summary write

- **Today?** N/A — **no such write exists.** There is no job that writes a single "freshness summary" row.
- **Artifact:** Would-be `pipeline_freshness` or `freshness_snapshot` table — does not exist.
- **Last successful run:** N/A.
- **Owner:** No owner.

---

## 4. Existing run-tracking ledger — does one exist?

**Three partial ledgers exist; none of them is unified.**

### 4.1 `daily_run_status` (Phase OPS / live-forward orchestrator)

`infra/alembic/versions/016_daily_run_status.py`:

```
run_date          DATE PRIMARY KEY
started_at        TIMESTAMPTZ
finished_at       TIMESTAMPTZ
status            VARCHAR(16)         -- success | failed | skipped | running
stage_failed      VARCHAR(64)
alert_count       INTEGER
summary_json      JSONB
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ
```

**Strengths:** PK on `run_date` enforces single-row-per-day. JSONB summary carries per-stage detail. Status enum covers the lifecycle.

**Weaknesses:**
- Only `daily_runner.run_daily_pipeline` writes it. The cron umbrella does not.
- Single row per day = no per-stage row. To know which stage of which substage failed, you parse `summary_json`.
- No watermark fields (input/output `as_of_date` per stage).
- No `triggered_by`, no `run_id` (the date *is* the ID), no `idempotency_key` separate from the date.
- No retry counter.

### 4.2 `paper_run_log` (Phase DAILY-VISIBILITY)

`infra/alembic/versions/036_phase_paper_run_log.py`:

```
id                       UUID PK
run_date                 DATE        -- UNIQUE (ux_paper_run_log_run_date)
started_at               TIMESTAMPTZ
finished_at              TIMESTAMPTZ
status                   TEXT
decisions_evaluated      INTEGER
trades_opened            INTEGER
trades_closed            INTEGER
trades_skipped           INTEGER
exploratory_trades       INTEGER
strict_trades            INTEGER
blocked_by_gates         INTEGER
blocked_by_anomaly       INTEGER
blocked_by_data_quality  INTEGER
net_pnl_today            NUMERIC(18,4)
nav_start                NUMERIC(18,4)
nav_end                  NUMERIC(18,4)
summary                  TEXT
warnings                 JSONB
details                  JSONB
```

**Strengths:** Excellent per-day paper-trading state with rich counts and JSONB fallback.

**Weaknesses:** Paper-only. No engine, no ingest, no ML, no options, no shadow.

### 4.3 `job_schedule` + `job_run` (tickloop)

`infra/alembic/versions/001_initial_schema.py:243` and the SQLAlchemy models at `apps/api/src/db/models.py:547-585`:

```
job_schedule:
  id, name (UNIQUE), cron_expr, enabled,
  next_run_at, last_run_at, created_at, updated_at

job_run:
  id, job_schedule_id (FK), started_at, finished_at,
  status (running|success|error), error_message, duration_seconds
```

**Strengths:** Per-execution rows, error capture, duration. Adequate for tickloop visibility.

**Weaknesses:** Only the tickloop uses it. The cron umbrella jobs do not write `job_run` rows. No per-stage breakdown for multi-stage jobs. No watermark fields.

### 4.4 The gap

There is no single ledger covering the union of cron umbrella stages, tickloop jobs, daily-runner stages, and ML / shadow / options runs. To answer "did the daily pipeline complete for 2026-05-11" requires consulting:
- `/tmp/last_daily_loop_success` marker (cron) — only via API container with mounted volume.
- `daily_run_status` row for 2026-05-11 (daily-runner — but cron umbrella does not write).
- `paper_run_log` row for 2026-05-11 (paper subsystem).
- `job_run` rows for tickloop jobs whose `started_at::date = 2026-05-11`.
- `recommendation.generated_at` (engine).
- `price_bar.ts` (ingest).
- `ml_model_run.created_at` (ML).

### 4.5 Proposed minimal unified ledger (PROPOSAL — not implemented)

```
pipeline_run                   -- one row per (trading_date, stage)
  id                  UUID PK
  trading_date        DATE NOT NULL
  stage               TEXT NOT NULL          -- e.g. "ingest_prices",
                                             -- "macro_context", "regime",
                                             -- "factor", "candidate",
                                             -- "recommendation",
                                             -- "paper_trading",
                                             -- "ml_shadow_train",
                                             -- "options_chain_snapshot", ...
  run_id              UUID NOT NULL          -- groups stages of one orchestrator pass
  status              TEXT NOT NULL          -- pending | running | success
                                             --        | partial | failed | skipped
  started_at          TIMESTAMPTZ
  finished_at         TIMESTAMPTZ
  duration_ms         BIGINT
  triggered_by        TEXT NOT NULL          -- "cron" | "tickloop" | "manual" | "api"
  idempotency_key     TEXT                   -- = stage || trading_date by default
  retry_count         INTEGER NOT NULL DEFAULT 0
  input_watermark     JSONB                  -- e.g. {"price_bar_max_ts": "..."}
  output_watermark    JSONB                  -- e.g. {"recommendation_count": 100, "as_of": "..."}
  rows_read           INTEGER
  rows_written        INTEGER
  error_class         TEXT
  error_message       TEXT
  metadata            JSONB
  UNIQUE (trading_date, stage, idempotency_key)
  INDEX (trading_date, stage)
  INDEX (run_id)
  INDEX (status, trading_date)
```

This proposal is to be **written by orchestrator code only**, never by job code. It is a *ledger of orchestrator decisions and outcomes*, not a substitute for `paper_run_log` / `daily_run_status` / `job_run`. Existing ledgers stay; the unified ledger is purely additive.

The ledger should be the authoritative source for `/api/freshness` (§7).

---

## 5. Daily orchestrator gaps

The discovery in §§2-3 surfaces these specific fragility points (each cited):

1. **Two schedulers, no joined state.** `worker-cron` (supercronic) and `worker-tickloop` (DB-backed) run in separate containers with separate restart policies, separate logging, and separate notion of "did this job run." The cron writes `/tmp` markers; the tickloop writes `job_run` rows. There is no read that reconciles the two. (`docker-compose.yml:111-200`, `tick_loop.py`, `run_daily_loop.sh`)
2. **No 16:30 ET schedule for same-day data.** The 15g audit assumed a 16:30 ET pipeline; the repo has none. Today's data is processed *tonight* (22:00 ET tickloop) or *tomorrow morning* (03:30 ET cron umbrella). For an investor opening the app at market close, the data is structurally stale — and there is no UI affordance for this. (`worker.crontab:11`, `seed_symbols.py:31`)
3. **Cron umbrella does not write `daily_run_status`.** `run_daily_loop.sh` writes only `/tmp/last_daily_loop_success` and `paper_run_log` (via `run_paper_daily.py`). The Phase OPS `daily_runner.py` ledger (which would be ideal) is bypassed. The same-day-state question "did anything run for 2026-05-11" cannot be answered from `daily_run_status` alone.
4. **`ml_can_affect_trades` and similar critical flags read from DB only via `daily_health_alerts.sh`** which is not on any cron. Failure to lock execution would not be alerted by anything that runs automatically. (`daily_health_alerts.sh:144-149`)
5. **Idempotency is per-table, not per-stage.** Re-running `run_daily_loop.sh` would re-execute every stage from the top; idempotency in the destination tables (recommendation, paper_run_log) prevents data corruption but wastes work and obscures "what was the actual sequence today." A run ledger would catch this.
6. **No same-day retry.** A job failure produces a marker file and exits. The next attempt is the next cron tick (typically next morning). For a transient failure (DB hiccup, API rate limit), there is no retry-with-backoff. (`run_daily_loop.sh:78-93`, `tick_loop.py:80-110`)
7. **No US holiday calendar.** `daily_runner._is_trading_day` is weekday-only with an explicit acknowledgement (`daily_runner.py:69-71`). On July 4 (a weekday), the pipeline runs, the precheck returns "no fresh bar" (correct), and the day appears as a `skipped` row. That is not wrong, but a calendar would let upstream surfaces say "market closed for July 4" instead of "market data not ready."
8. **Cron umbrella has no asyncio job stop / global timeout.** A stage that hangs (e.g., a Tiingo call without a timeout) blocks subsequent stages until container restart. The script has no per-stage timeout watchdog.
9. **Lock files survive in `/tmp`.** `flock -n 9` works at the kernel level (not file-presence), so a stale lock file is benign on Linux — but the marker ambiguity is still a UX hazard for operators (`scheduler_health._lock_held` returns "presence" not "held", explicit comment at `scheduler_health.py:51-57`).
10. **Failure visibility ends at marker files + container stdout.** No alerting wired (§2.11). The 15g `/api/system/health` returns hard-coded healthy. An operator who is not actively `docker logs`-ing the worker-cron container will not know about a failed Tuesday morning run until they notice tickets stop appearing.

---

## 6. Proposed daily orchestrator design

PROPOSAL ONLY. Not implemented. Per the user brief, the orchestrator should run once per trading day, market-calendar aware, idempotent, lock-protected, retry-safe per stage, fail visibly + calmly, write ledger rows + freshness summary.

### 6.1 The 12-step daily sequence

The user brief specifies a 12-step sequence; mapping each to existing code where possible:

| # | Step | Existing script (where) | Gap |
|---|---|---|---|
| 1 | Confirm trading day (calendar lookup) | `_is_trading_day` (`daily_runner.py:69-71`) | Holiday calendar missing |
| 2 | Acquire run lock for `(trading_date)` | `flock` in cron, `daily_run_status` PK in orchestrator | Two locks, no shared key |
| 3 | Open ledger row(s) for the run | `paper_run_log` (paper only); `daily_run_status` (orchestrator only) | No unified `pipeline_run` |
| 4 | Ingest market data (Tiingo → Yahoo) | `apps/worker/src/jobs/ingest_prices_daily.py` | Cron umbrella does not call it directly — assumes tickloop already ran |
| 5 | Update macro + regime context | `scripts/run_engine_pipeline.py` | OK; called by cron stage 0 |
| 6 | Compute factors | `compute_factor_snapshots` | OK; via engine pipeline |
| 7 | Generate candidates | `generate_stock_candidates` | OK; via engine pipeline |
| 8 | Generate recommendations | `run_recommendations_for_all_accounts` (tickloop) | NOT called by cron umbrella; relies on tickloop having fired earlier |
| 9 | Run paper trading (decisions + fills) | `scripts/run_paper_daily.py` (cron) OR `run_paper_trading` (tickloop) | Two paths; conflict possible |
| 10 | Update options chain + strategies | `options_chain_snapshot.py` (function exists) | NOT scheduled; nothing runs |
| 11 | Run shadow evaluations | `run_shadow_strategy.py`, `safe_gate_evolution_shadow.py`, `nightly_ml_shadow.py` | OK; cron umbrella calls all three |
| 12 | Write freshness summary row + dispatch alerts | `dispatch(alerts)` exists (`alerting.py`) | Freshness summary write does not exist; alert delivery channel not wired |

### 6.2 Key properties

- **Single canonical orchestrator.** Replace the three competing definitions (cron umbrella shell / `daily_runner.py` / tickloop registry) with one entry. The cron and the tickloop should both call it; ledger rows distinguish via `triggered_by`.
- **Per-stage ledger row.** Each of the 12 stages writes one `pipeline_run` row (started → success/failed/skipped). On retry, increment `retry_count` rather than insert a new row.
- **Market-calendar guard.** Use a real US-equity calendar (pandas-market-calendars or equivalent). Skip with `status="skipped"` and `metadata.reason="market_closed_holiday"`.
- **Cross-scheduler lock.** Use `pipeline_run.UNIQUE(trading_date, stage, idempotency_key)` — a second attempt for the same triple either no-ops or increments retry_count atomically. Eliminates supercronic / tickloop race.
- **Per-stage retry with bounded backoff.** Three retries with 60 s / 5 min / 30 min backoff for transient failures. Permanent failures (e.g., schema mismatch) skip retry.
- **Calm failure.** A failed stage emits a `SEV_WARNING` alert; a failed *required* stage emits `SEV_CRITICAL`. Alert dispatch goes through a wired channel (Slack/email/log) — currently `dispatch()` is a no-op for un-wired destinations.
- **Freshness summary write.** After all stages complete, write one row to a `pipeline_freshness_summary` table with the per-channel last-success timestamps. This is the source for `/api/freshness` (§7).
- **Same-day partial retry.** If the cron's 03:30 ET run fails for `paper_trading`, an operator-triggered `make paper-daily-date D=2026-05-11` should succeed without re-running successful upstream stages.

### 6.3 What does NOT change

- Existing tables stay. `daily_run_status`, `paper_run_log`, `job_schedule`, `job_run` continue to be written by their current owners.
- The cron container and tickloop container both stay. The orchestrator is a callable; the schedulers remain the triggers.

---

## 7. Proposed `/api/freshness` contract

PROPOSAL. Not implemented.

### 7.1 Shape

```json
{
  "trading_date": "2026-05-11",
  "last_successful_cycle_at": "2026-05-09T07:30:00Z",
  "overall": "stale",
  "channels": {
    "recommendations": {
      "status": "stale",
      "as_of": "2026-05-09T02:30:00Z",
      "last_run_id": "...uuid...",
      "message": "Recommendations from Saturday close — awaiting next refresh."
    },
    "portfolio": { ... },
    "events":    { ... },
    "options":   { ... },
    "risk":      { ... },
    "ml":        { ... }
  }
}
```

### 7.2 Channel data sources

| Channel | Backing source | Freshness column |
|---|---|---|
| `recommendations` | `recommendation` table | `MAX(generated_at)` over last 24h |
| `portfolio` | `paper_run_log` | `MAX(finished_at) WHERE status='success'` |
| `events` | live request to `market_events.service` | `now()` minus a small drift band |
| `options` | `options_chain_snapshot` | `MAX(snapshot_at_utc)` |
| `risk` | derived from `paper_trade` + `options_paper_trade` | derived from latest portfolio snapshot |
| `ml` | `ml_hybrid_performance_snapshot` | `MAX(as_of_date)` per `window_days=7` |

For each channel, `last_run_id` joins to the proposed `pipeline_run` ledger (`run_id` column in §4.5).

### 7.3 SLAs (carry forward from 15g §5)

| Channel | Fresh | Degraded | Stale |
|---|---|---|---|
| recommendations | < 16h | 16-30h | > 30h |
| portfolio | < 30m intraday / < 16h overnight | 30m–4h / 16-30h | > 4h / > 30h |
| events | < 6h | 6-24h | > 24h |
| options | < 6h | 6-24h | > 24h |
| risk | < 30m intraday | 30m-4h | > 4h with positions open |
| ml | < 24h | 24-48h | > 48h |

### 7.4 `overall` aggregation

Worst-of across `recommendations`, `portfolio`, `events`, `risk`. Options and ML are *informational* — they degrade `overall` only if their `status="stale"` AND their channel is currently being surfaced to the user (i.e., user is on `/options` or `/alpha-lab`).

### 7.5 Message generation

Each channel carries a deterministic, human-friendly `message` derived from `(status, age_human, last_run_id present?)`:

- Fresh: `"Refreshed N minutes ago"` or `"Refreshed at HH:MM ET"` (no operator vocabulary).
- Degraded: `"Last refresh: <human time>; awaiting next cycle."`
- Stale: `"<channel> is from <weekday> close — awaiting next refresh."`

Anti-patterns explicitly disallowed in 15g §6.2 are inherited: no "scheduler failure", no "job dead", no operator vocabulary.

### 7.6 Caching

`/api/freshness` should be safe to call on every request (it is read-only and aggregates indexed lookups). A 5-second in-memory cache in the API process is acceptable but not required for correctness.

---

## 8. ML training lifecycle audit

### 8.1 How is ML trained today?

`apps/api/src/jobs/nightly_ml_shadow.py:39-65`. Called from `run_daily_loop.sh:181` as a *required* job in the cron umbrella. So: nightly Tue–Sat at 03:30 ET, on the prior trading day's data. Default model types `logistic,ridge,rf` (env `ML_SHADOW_MODEL_TYPES`).

### 8.2 Where are model artifacts stored?

File-based registry: `models/model_registry.json` (`apps/api/src/ml/model_registry.py:24 REGISTRY_PATH`). Append-only JSON list (line 5-8). **Currently empty: `[]`** (per `models/model_registry.json` content).

This is a finding. Either no models have ever been registered through this CLI, or the registration step in nightly training does not call `register()`. The trainer at `apps/api/src/ml/shadow/trainer.py` and runtime at `apps/api/src/ml/shadow/runtime.py` may use a different artifact path.

### 8.3 How is current model version selected?

The registry has no "current" pointer. `register()` is append-only with no promotion concept (`model_registry.py:5-12` declares `status` is always `"shadow_only"` in v1). Selection of which model serves predictions at runtime is **not** governed by this registry — it must happen elsewhere (likely the `ml_model_run` table, ordered by `created_at DESC`).

### 8.4 Is there a model registry table?

No SQL table named `model_registry`. There IS:
- `models/model_registry.json` (file, currently empty).
- `ml_model_run` (`infra/alembic/versions/030_phase_ml3_shadow.py`) — one row per training run.
- `model_scorecard` (`infra/alembic/versions/019_model_scorecard.py`) — per-model performance metrics.

The closest thing to a "current model version" is `ml_model_run` ordered by `created_at`.

### 8.5 Is promotion gated by shadow evaluation?

Yes, per the `ml_hybrid_performance_snapshot` flow + `apps/api/src/ml/shadow/promotion_guard.py`. Compose env (`docker-compose.yml:62-63`): `ML_PROMOTION_REQUIRE_OPERATOR_APPROVAL: true`. So promotion is gated by (a) snapshot-based metrics and (b) explicit operator action.

Hard execution lock: `ML_CAN_AFFECT_TRADES: false` (compose line 64). This is a global kill-switch; while false, no model promotion can affect actual trades. The script `daily_health_alerts.sh:144-149` alerts if it ever flips to true.

### 8.6 How old is the current model?

UNKNOWN from this audit — the file registry is empty, so `models/model_registry.json` cannot tell us. Would require a live `SELECT MAX(created_at) FROM ml_model_run`. This is itself a finding: there is no UI surface that tells an operator the age of the active model.

### 8.7 Is `current_model_version` exposed anywhere?

`/api/ml/hybrid/status` is referenced by `daily_health_alerts.sh:142,155`. It exists at `apps/api/src/api/ml_hybrid.py` — would expose `mode` and `ml_can_affect_trades` but not directly a `current_model_version`. The ML shadow scoring runtime references model identity internally; no API field surfaces "version X trained on Y, promoted on Z."

**Finding:** Model lifecycle is well-defined in the code (training cadence, promotion gate, kill switch) but invisible at the surface. A user or operator cannot answer "which model is making the calls, when was it trained, how is it doing" without joining DB tables manually.

---

## 9. Daily verification script proposal

PROPOSAL: `scripts/check_daily_pipeline_health.py`. Not implemented.

### 9.1 Purpose

A single command, runnable from cron or a host operator's shell, that returns a human-readable health summary and a UNIX-friendly exit code. Designed to be the operator's first read after suspecting something is off.

### 9.2 Checks performed

1. **Recommendations freshness.** `MAX(generated_at) FROM recommendation`. SLA: < 30h. Fail if exceeded.
2. **Portfolio freshness.** `MAX(finished_at) FROM paper_run_log WHERE status='success'`. SLA: < 30h overnight, < 4h intraday with positions open.
3. **Pipeline ran today.** EXISTS row in `daily_run_status WHERE run_date=current_date AND status IN ('success','running')` OR `/tmp/last_daily_loop_success` newer than today 06:00 UTC.
4. **No stage stuck `running`.** No `daily_run_status` row with `status='running'` and `started_at < now() - interval '4 hours'`.
5. **Output non-zero unexpectedly.** `recommendation.count(*) WHERE generated_at::date = current_date` > 0 if today is a trading day.
6. **Freshness endpoint says stale after expected window.** `/api/freshness.overall != "stale"` after 23:00 ET on a trading day.
7. **Tickloop alive.** `MAX(last_run_at) FROM job_schedule WHERE enabled=true` within the last 24 hours.
8. **`ml_can_affect_trades` is false** (regression check on the global kill switch).
9. **`ml_hybrid_mode` is `advisory`** (regression check).
10. **Active model age.** `MAX(created_at) FROM ml_model_run` within last 7 days.

### 9.3 Exit codes

- `0` — OK. All checks pass.
- `1` — DEGRADED. At least one channel exceeds fresh SLA but stays inside degraded SLA.
- `2` — STALE. At least one channel exceeds stale SLA.
- `3` — FAILED. A check returned a hard failure (e.g., today should have data but does not; pipeline did not run).
- `4` — UNREACHABLE. Could not connect to DB or API.

### 9.4 Output format

Plain text, one check per line, ending with a single-line summary:

```
[OK]       recommendations         fresh   age=03h12m
[STALE]    portfolio               stale   age=2d05h   sla=30h
[OK]       pipeline_today          ran     started=2026-05-11T07:30Z
[FAILED]   freshness_endpoint      404
...
summary: 7 OK, 1 DEGRADED, 1 STALE, 1 FAILED → exit 3
```

Optional `--json` flag for machine consumption.

### 9.5 Integration

NO mandatory alerting integration in v1. The script is purely a diagnostic — operators chain it to mail/Slack/whatever themselves (same model as `daily_health_alerts.sh` today). A `--log-file PATH` option appends one line per check to a rolling log if requested.

---

## 10. Minimal implementation plan

Five tightly-scoped commits, ranked by impact-per-risk. Each is a *proposal*; none is built in this audit.

### 15i.A — Ledger schema (Alembic migration; write-only)

- **Files touched:** `infra/alembic/versions/065_pipeline_run_ledger.py` (new), `apps/api/src/db/models.py` (add `PipelineRun` ORM class).
- **Effort:** S (single migration, simple CREATE TABLE, no data migration).
- **Risk:** low. Additive only. No existing code reads or writes the new table; nothing depends on it yet.
- **Rationale for ordering:** must exist before orchestrator can write to it. Releasing the schema independently de-risks the rest.

### 15i.B — Daily orchestrator skeleton

- **Files touched:** new `apps/api/src/domain/ops/daily_orchestrator_v2.py`, refactor `apps/worker/src/jobs/run_daily_pipeline.py` to call it, optionally update `scripts/run_daily_loop.sh` to call the same orchestrator (so cron and tickloop converge).
- Behaviors: market-calendar guard; per-stage `pipeline_run` row write; `flock`-equivalent via DB unique constraint; per-stage retry with bounded backoff; freshness summary write at end.
- **Effort:** M-L (new orchestrator + cutting over two existing call sites).
- **Risk:** medium. Touches both schedulers' entry points. Mitigation: leave existing `daily_runner.py` and `run_paper_daily.py` callable directly; the new orchestrator is an additional layer that delegates.
- **Rationale for ordering:** depends on 15i.A. Should ship behind a feature flag so the cron umbrella keeps using the legacy path until the new path is observed clean.

### 15i.C — `/api/freshness` endpoint

- **Files touched:** new `apps/api/src/api/freshness.py`, register in `apps/api/src/main.py`.
- **Effort:** S.
- **Risk:** low. Read-only. Reads the ledger from 15i.A and existing tables.
- **Rationale for ordering:** depends on 15i.B writing the ledger; can ship before UI consumption work in 15h.

### 15i.D — `scripts/check_daily_pipeline_health.py`

- **Files touched:** new script; reuses `apps/api/src/db.SessionLocal` and HTTP-fetches `/api/freshness`.
- **Effort:** S.
- **Risk:** low. Pure read; non-zero exit codes only.
- **Rationale for ordering:** can land at any time after 15i.A; most useful after 15i.B + 15i.C.

### 15i.E — ML lifecycle visibility surface

- **Files touched:** new `apps/api/src/api/ml_lifecycle.py` (current model age, training history, promotion eligibility, kill-switch state); register in `main.py`.
- Optional: extend `models/model_registry.json` writers in `apps/api/src/jobs/nightly_ml_shadow.py` to actually call `register()` so the file becomes the durable record.
- **Effort:** M.
- **Risk:** low for the read endpoint, medium for the registry writer change (which mutates the model promotion lineage).
- **Rationale for ordering:** independent of 15i.A-D. Ships when ML deserves UI attention.

---

## 11. Highest-risk operational gaps (ranked top 10)

Distinct from the UI-side gaps surfaced in 15g.

1. **Two parallel schedulers with no shared run ledger.** The cron and tickloop independently believe they are "running the daily pipeline"; an operator cannot answer "did the daily pipeline complete for date X" from a single source. (`docker-compose.yml:111-200`, `tick_loop.py`, `run_daily_loop.sh`)
2. **Cron umbrella does not write `daily_run_status`.** The Phase OPS ledger silently misses every cron-triggered run. (`run_daily_loop.sh` writes only `/tmp` markers; `daily_runner.py:93-105` is the only writer.)
3. **No same-day data path.** Today's price bars are not processed until tonight (22:00 ET tickloop) and not aggregated into a daily-runner pass until tomorrow morning (03:30 ET cron umbrella). For Monday-evening users, the data layer is *structurally* yesterday-or-older. The 15g audit interpreted this as "the pipeline didn't run"; the operational truth is "the schedulers are not architected for same-day use." (`worker.crontab:11`, `seed_symbols.py:31`)
4. **Options pipelines have no scheduler.** `options_chain_snapshot.py:1-13` documents the function as defined but unscheduled; no other scheduler picks it up. Endpoints serve possibly-very-old data with no `as_of`. (15g §2.6 + `options_chain_snapshot.py`)
5. **No US-holiday calendar.** `daily_runner._is_trading_day` is weekday-only with explicit acknowledgement. On July 4 the precheck saves the day but the user sees "no fresh bar" rather than "market closed for holiday." (`daily_runner.py:69-71`)
6. **Alerting plumbing exists but no destination is wired.** `dispatch(alerts)` runs on every daily-runner invocation but `apps/api/src/domain/ops/alerting.py` has no observed Slack/email/webhook integration in production code. Failures fall into container stdout. (`daily_runner.py:331`, alerting module)
7. **Model registry file `models/model_registry.json` is empty `[]`.** Either no model has ever been registered through the documented CLI, or the nightly trainer bypasses it. The "current model" is invisible. (`models/model_registry.json`, `manage_model_registry.py`)
8. **The `paper_run_log.status='partial' with 0 trades`** is conflated with "no-trade day expected" — `daily_health_alerts.sh:99-115` heuristically distinguishes them by checking `context_daily.MAX(as_of_date)` against `paper_run_log.run_date`. This is fragile to ANY context-daily skew.
9. **No same-day retry logic.** A transient DB or API failure during the 03:30 ET cron run leaves the day stale until the next 03:30 ET tick (24h) unless an operator manually invokes `make paper-daily-date D=...`. There is no retry-with-backoff anywhere. (`run_daily_loop.sh:78-93`)
10. **`/api/system/health` returns hard-coded `healthy` with `items=[]`.** Already documented in 15g §2.5. From an ops perspective, this is the highest-risk endpoint in the whole API surface — any future banner reading from it would render confidently green during a total pipeline outage.

---

## 12. What is already correct (preserve)

These five items the audit found that should NOT be changed in any implementation phase.

1. **`flock -n 9` lock in `run_daily_loop.sh:30-37`.** Solid kernel-level overlap protection. Would only get worse if replaced.
2. **`scripts/run_paper_daily.py` idempotency (`UNIQUE(run_date)` on `paper_run_log` + `--force-recompute`).** Clean upsert semantics; any new orchestrator should reuse this pattern.
3. **`scripts/check_market_data_ready.py` precheck with the per-stage diagnostic file at `/tmp/market_data_diagnostics`.** Phase 11W-incident-tested; saves the loop from the macro-context-pinning bug. (`check_market_data_ready.py:78-145`)
4. **`daily_runner.py` per-stage try/except + `summary_json` accumulation.** The pattern of "isolate each stage, never let one kill the others, accumulate alerts, finalize once" is exactly right; the new orchestrator should mimic it.
5. **`ML_CAN_AFFECT_TRADES=false` global kill switch in compose + the alerter check at `daily_health_alerts.sh:144-149`.** The kill switch is the load-bearing safety property; it works as designed and should not be replaced.

---

*Audit conducted 2026-05-11 from code inspection only. No live re-probes (15g audit's live evidence is referenced in §3 as authoritative for time-bound claims). No code, scheduler, or schema modifications.*
