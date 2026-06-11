# Operational Hardening Backlog

Planned operational hardening work captured after the
2026-05-08 scheduler incident (commit `0a6d90a`,
`fix(scheduler): Restore daily loop completion before next run`).

Each entry is **planned work**, not a future emergency. The
incident exposed observability + validation gaps that allowed
two latent bugs (FRED env propagation; Decimal/float TypeError)
to silently fail multiple consecutive daily runs.

These items should be picked up as deliberate hardening
sprints, NOT mixed with feature work or hotfixes.

---

## H1 — `max_drawdown_pct` schema drift in `paper_run_log`

> **STATUS: FIXED (P6E.0, 2026-06-11).** Root cause was in
> `activation.py:_gather_health_inputs` — the risk-control proxy
> selected `max_drawdown_pct` ordered by `snapshot_date` from
> `paper_portfolio_snapshot`, whose real columns are `max_dd_pct` +
> `as_of_date`. The UndefinedColumn error poisoned the transaction so
> the `system_health_score` INSERT failed every nightly run (table had
> 0 rows ever). Fixed the query and added `session.rollback()` to all
> four proxy except-blocks so no single failed read can poison the
> health write again. Verify post-deploy: `system_health_score` gains
> a row on the next alpha_nightly run.

**Symptom**: `alpha_nightly` logs the following on every run:

```
WARNING: column "max_drawdown_pct" does not exist
INTO system_health_score (...)  →  InFailedSqlTransaction
```

`alpha_nightly` catches the transaction abort and exits 0,
so the daily loop is not blocked, but `system_health_score` is
not written and downstream "system health" surfaces are stale.

**Action**:

1. Locate the migration that introduced the column reference.
2. Diff `paper_run_log` schema vs the model definition.
3. Either add the missing column via a forward migration, or
   patch `apps.api.src.alpha.activation:_gather_health_inputs`
   to read from the column that actually exists.
4. Add a startup-time schema sanity check (compare ORM column
   list vs `information_schema.columns`) so future drift fails
   fast rather than logging warnings forever.

**Risk**: low. Read-only paper data; no trading invariants.

---

## H2 — Restore daily-loop log visibility (supercronic `-quiet`)

> **STATUS: OBSOLETE (P6E.0, 2026-06-11).** The W1 worker rebuild
> replaced supercronic entirely — `worker.Dockerfile` CMD is now
> `python -m apps.worker.src.main` (job-schedule tick-loop). There is
> no supercronic binary or `-quiet` flag left to fix; worker stdout
> (boot env validation, tick-loop lines) is already visible via
> `docker logs` (verified P6D.39). No action.

**Symptom**: `worker.Dockerfile` runs supercronic with `-quiet`,
which suppresses every job's stdout/stderr. `docker logs
compose-worker-cron-1` only shows the final exit-code line. Root
cause analysis on the May-8 incident required ~5 minutes of
`docker exec` to reproduce the failure manually.

**Action**:

1. Remove `-quiet` from the `CMD` line in `worker.Dockerfile`.
2. Verify supercronic now prints the daily-loop `START` /
   `SUCCESS` / `FAIL` lines + per-stage stdout.
3. Recreate `worker-cron` only.
4. Optionally: pipe daily-loop output through `tee` to a
   file in `worker_cron_tmp` volume so the API can serve a
   "last run log" endpoint.

**Risk**: trivial. Behaviour change is purely additive logging.

---

## H3 — Scheduler observability endpoint

**Goal**: a single API endpoint that surfaces, for each
required job in the daily loop:

- last successful run timestamp
- last failed run timestamp
- last per-stage outcome
- max-stale-after threshold per data source
- a colour-coded status the WebUI can render without polling
  multiple endpoints

**Why**: the May-8 outage was visible via `/tmp` markers but
not in any UI surface beyond a single boolean "loop failed".
The five required jobs each have independent failure modes;
a single boolean masks which.

**Action**:

1. Extend `apps/api/src/api/scheduler_health.py` with per-job
   status from `paper_run_log` + `/tmp/last_*` markers.
2. WebUI Ops surface renders one row per required job with
   timestamp + status + last error excerpt.

---

## H4 — Stale-table monitoring + alerts

**Goal**: detect when `context_daily`, `regime_snapshot`,
`factor_snapshot`, `candidate_idea`, or `paper_run_log` lag
behind `price_bar` by more than N trading days, regardless of
the daily-loop exit code.

**Why**: the May-8 incident kept `price_bar` advancing nightly
(via `ingest_prices_daily` in worker-tickloop) while the four
downstream tables silently fell 4+ days behind. The daily loop
returned non-zero, but no proactive alert fired.

**Action**:

1. Add a tickloop job `monitor_table_freshness` that runs hourly,
   reads `MAX(as_of_date)` per table, computes lag in trading
   days vs `price_bar`, and writes to a `freshness_snapshot`
   table.
2. Trigger an alert when lag exceeds 1 trading day for any of
   the four downstream tables.
3. WebUI banner reads the freshness table directly.

---

## H5 — Env propagation validation at container startup

**Symptom (root cause of bug #1 on May 8)**: `FRED_API_KEY`
was declared in `.env` but never propagated to any container
in `docker-compose.yml`. The macro_backfill stage of
`run_engine_pipeline.py` raised a config error every run.

**Action**:

1. Add a startup-time sanity check in each container that
   asserts every env var listed in
   `apps/api/src/config/__init__.py` as required-by-feature
   is present and non-empty when that feature is enabled.
2. Container exits non-zero with a clear message if a required
   env is missing — preferred over a silent runtime failure
   four hours later in cron.
3. Add a `make verify-env` target that diffs `.env.example`
   keys vs `docker-compose.yml` `environment:` blocks and
   fails CI on drift.

---

## H6 — ML insufficient-data telemetry

**Observation**: `nightly_ml_shadow` returned
`status=SKIPPED_INSUFFICIENT_DATA n_scored=0` after the fix.
That status is correct, but it surfaces only as a single line
in the daily-loop log. Operators have no time-series view of
how often this state occurs or how close to the threshold the
data sits.

**Action**:

1. Persist `ml_shadow_run` rows for every invocation including
   skipped runs, with: `status`, `n_decisions_total`,
   `n_decisions_with_labels`, `min_required`.
2. Operator dashboard charts the trend so the "ML is advisory
   only because data is insufficient" state is visible.

**Why this matters**: we cannot promote ML to non-advisory
without these counters; right now an operator would have to
grep logs to know if data is approaching the threshold.

---

## H7 — Replay transparency

**Observation**: `paper_trade_log.source` distinguishes
`live` / `dev` / `replay` / `test`, but the daily-loop output
does not call out when a replay run silently fed data into
the labelling pipeline. Decimal/float bug #2 may have been
masked by replay rows for an unknown duration.

**Action**:

1. Daily-loop summary line includes per-source row counts
   (real / replay / dev / test).
2. WebUI Brief view's "recovered" chip extends to a per-page
   chip showing "X of Y positions recovered from replay" so
   operators see drift before it dominates.

---

## H9 — Auto-trigger post-ingest paper cycle

**Symptom (2026-05-08 trust incident)**: pending fills sat
unreplayed for 3 days because `scripts/run_post_ingest_paper_cycle`
is operator-triggered only. No cron step picks up the JSONL
backlog after fresh price bars + factor/regime snapshots land.

**Action**:

1. Add a `pending_replay` step to `run_daily_loop.sh` between
   `engine_pipeline` and `paper_daily`. Or add a tickloop job
   that fires after `ingest_prices_daily` succeeds.
2. Idempotent — pending_replay already writes `.replayed.jsonl`
   markers and re-runs are no-ops.
3. Optional: surface a "last replay run" timestamp in the
   scheduler-health endpoint.

**Risk**: low. The runner already enforces every safety
invariant (next-bar guard, dedup, paper-only). Auto-triggering
the call doesn't relax anything.

---

## H10 — Orchestration-state observability

**Goal**: explicitly distinguish orchestration states across
fills / replay / lifecycle / scheduler / copilot surfaces. Multiple
hidden states currently collapse into "pending" and produce trust
failures (the 2026-05-08 incident is the canonical example —
"held by next-bar guard" was conflating four different states).

The surface vocabulary to support:

| State | Meaning |
|-------|---------|
| `waiting_for_market_data` | Price bars / factor snapshots not yet ingested for the relevant date |
| `waiting_for_next_bar` | A bar after `submitted_at` is genuinely not yet available |
| `ready_for_replay` | Bar exists; awaiting operator (or H9 auto-trigger) |
| `waiting_for_operator` | Generic operator-action-needed state |
| `waiting_for_scheduler` | Cron has not fired the relevant step yet |
| `replay_in_progress` | Replay cycle is currently running |
| `replay_completed` | `.replayed.jsonl` marker present; no further action |

**Action**:

1. Pick one canonical orchestration-state enum and propagate
   through:
   - `/api/performance/paper/pending-fills` (partial — H10 starts
     here; the May-8 trust fix shipped a 3-of-7 subset)
   - `/api/scheduler/health`
   - WebUI Brief view "what changed" surface
   - Discord formatter
   - paper_run_log.summary
2. Document the state-machine transitions and their truth
   sources (DB column, file marker, lock file, computed at
   read time).
3. Ban "pending" as a free-form string anywhere in the
   surface layer; require an explicit state.

**Why this matters**: the May-8 incident was caused by
`historical rejection state` masquerading as `current readiness
state`. Without an explicit enum, future status surfaces will
keep drifting back into the same failure mode.

---

## H8 — Pipeline freshness monitoring

**Goal**: a single dashboard panel showing, for each pipeline
stage, the lag between `as_of` and "now":

- `ingest_prices_daily`
- `run_engine_pipeline.macro_backfill`
- `run_engine_pipeline.regime_snapshot`
- `run_engine_pipeline.factor_snapshots`
- `run_engine_pipeline.generate_stock_candidates`
- `paper_daily`
- `alpha_nightly`
- `nightly_ml_shadow`
- `ml_hybrid_monitor_nightly`

Each stage gets a "fresh / stale / stuck" classification with
a recommended action.

**Why**: subsumes H1–H4 once data layout exists. Build this
last, after the lower-level pieces.

---

## Sequencing recommendation

| Order | Item | Reason |
|-------|------|--------|
| 1 | **H2** | Trivial; restores log visibility for everything else |
| 2 | **H5** | Prevents the env-propagation root cause class entirely |
| 3 | **H4** | Catches future stale-table failures before they extend 4 days |
| 4 | **H1** | Closes the alpha_nightly schema drift |
| 5 | **H3** | Surfaces per-job state to WebUI |
| 6 | **H6** | Required before ML promotion can be considered |
| 7 | **H7** | Replay transparency for operator audit |
| 8 | **H8** | Unifies H1–H6 into a single dashboard view |
| 9 | **H9** | Auto-trigger post-ingest paper cycle from daily loop or post-ingest tickloop step |
| 10 | **H10** | Canonical orchestration-state enum across fills / replay / scheduler / copilot |

H2 + H5 are quick wins (≤ 1 day each). H3, H4, H6 are
multi-day. H8 is a small UI on top of H1–H6 once they're done.
H9 is a small one-line cron addition once the volume mounts in
the 2026-05-08 trust fix have been validated through a few
cycles. H10 is a multi-touch refactor — schedule after H3 + H6
since both write into the new enum.

---

## Out of scope for this backlog

- UX-2 / UX-3 / UX-4 visual work
- Trading logic
- Execution rules
- DB schema for paper trading
- Engine-A / Engine-B promotion gates
- Options work

These have their own roadmaps. Hardening is independent.
