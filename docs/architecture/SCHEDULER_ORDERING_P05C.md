# P0-5C — Scheduler Ordering & Latency (Design Proposal)

**Status:** proposal only — nothing implemented, no production schedules changed. · **Date:** 2026-07-10 · Follow-up to the closed P0-5 (see 2026-07-10 closure evidence).

## Observed defect (production, 2026-07-10)

`run_paper_exit_cycle` (due 23:00 UTC) started at **00:15:12** — 75 minutes late and **after** `run_paper_trading` (due 23:30). Root cause: `tick_loop._tick()` claims every due job and then `await asyncio.gather(...)` — the worker's loop is **blocked until its slowest claimed job finishes**, so later slots queue behind long runs and the intended ordering (exits free slots *before* new entries) inverts. Exactly-once was preserved (P0-5A claim untouched); this is purely latency/ordering.

## Requirements (binding)

1. Exits run before new entries on every trading night.
2. The atomic DB claim (`UPDATE … WHERE next_run_at <= now RETURNING id`) stays byte-identical — exactly-once must not be re-litigated.
3. No global worker blocking: a long job must not delay unrelated due jobs beyond one tick.
4. Bounded execution: per-job timeout with explicit failure recording.
5. Restart/recovery: a worker dying mid-job must not strand the schedule.
6. Tests: two-worker claim races and delayed-job scenarios.

## Design

### D1 — Fire-and-track tasks (removes global blocking)
`_tick()` stops awaiting its jobs. Claimed jobs become tracked `asyncio.Task`s in a module-level set; the loop returns to sleeping immediately, so the next tick fires on schedule and claims newly-due jobs even while earlier jobs run. The existing `_MAX_CONCURRENT` semaphore still caps parallelism. Completion handling (job_run close, logging) moves into the task itself (it already is — `_execute_job` is self-contained).

### D2 — Explicit dependency edge, not clock hope
Clock ordering ("23:00 < 23:30") failed precisely because of queuing. Encode the one real ordering constraint directly: `run_paper_trading` begins with a **precondition check** — if `run_paper_exit_cycle` has a `job_run` with `status='running'` for today, or its schedule shows today's slot still unclaimed (`next_run_at <= its cron slot for today`), the auto-trader waits (bounded, e.g. poll ≤20 min) or proceeds with a loud `ordering_violated` log if the exit cycle failed. This keeps ordering correct under any latency without a workflow engine. (Generalization — a `run_after` column on `job_schedule` — is deliberately deferred: one edge exists today; a framework is over-engineering.)

### D3 — Bounded runtime
`_execute_job` wraps `job_fn()` in `asyncio.wait_for(timeout=JOB_TIMEOUT_SECONDS)` (default 3600, env-overridable; per-job override later if needed). Timeout ⇒ `job_run.status='error'`, `error_summary='timeout after …s'`; the schedule's `next_run_at` was already advanced at claim, so the job simply resumes its normal cadence — no retry storm.

### D4 — Restart/recovery
A worker killed mid-job leaves `job_run.status='running'` forever (already true today). Add a startup sweep: rows `running` with `started_at < now − JOB_TIMEOUT` → `status='orphaned'` + log. Schedules are unaffected (claim already advanced `next_run_at`), so recovery is observational, not corrective — consistent with P0-5B's "visible, never silent" posture.

### Explicit non-changes
No Celery/Redis/queue service; no change to `_claim_due_job` SQL; no change to cron expressions or `job_schedule` rows in this release; no multi-edge dependency framework.

## Failure behavior summary

| Scenario | Behavior |
|---|---|
| Exit cycle still running at 23:30 | auto-trader waits (bounded), then runs; ordering preserved |
| Exit cycle failed tonight | auto-trader proceeds after bounded wait + `ordering_violated` warning (missing exits must not also kill entries) |
| Job exceeds timeout | recorded error; next cadence unaffected |
| Worker dies mid-job | `orphaned` sweep on next startup; exactly-once unaffected |

## Test plan

- **Two-worker claim race** (exists: `test_scheduler_claim_pg.py::test_concurrent_claim_has_exactly_one_winner`) — must stay green byte-identically.
- **Non-blocking tick:** stub a slow job; assert a second due job's `started_at` lands within one tick interval, not after the slow job.
- **Ordering edge:** exit-cycle running ⇒ paper-trading waits; exit-cycle failed ⇒ paper-trading proceeds with warning after bounded wait.
- **Timeout:** stub job sleeping past `JOB_TIMEOUT` ⇒ `job_run.status='error'`, loop alive, next cadence normal.
- **Orphan sweep:** seed a stale `running` row ⇒ startup marks `orphaned`, never re-executes it.
- **Delayed-job regression:** simulate the 2026-07-10 night (22:00/22:30/23:00/23:30 slots with a long 23:30-adjacent job) ⇒ assert exit precedes entries.

## Rollout (when approved — not part of Honest Numbers)

Dev worktree → tests → deploy workers only (same clean-worktree procedure, rollback tags) → observe two consecutive nights: exit `started_at` within 5 min of 23:00 and strictly before `run_paper_trading`. Rollback = previous worker image tag.
