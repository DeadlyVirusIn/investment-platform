# Paper-trading replay — 2026-05-02 incident-response report

**Status:** complete. Operator-only replay executed via
`scripts/replay_paper_history.py`.

**Window replayed:** 2026-04-24 → 2026-05-01 (6 business days:
Fri 4-24, Mon-Fri 4-27 → 5-01).

**Confirmation env used:** `PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY`.

**Pre-replay backup:** `.backups/predump_20260502_134551.sql`
(taken before the first commit; covers paper_*, decision_log,
paper_portfolio).

---

## What was lost on 2026-05-02

`docker volume rm compose_pgdata` (run during deploy-readiness
verification) destroyed the dev DB volume. Pre-wipe snapshot:

| Table | Rows lost |
|---|---|
| paper_trade | 5 |
| paper_run_log | 6 |
| decision_log | 16 |
| paper_shadow_log | 660 |
| paper_trade_log | 301 |

Recovered upstream (re-fetched + recomputed before replay):
asset (63), universe_membership (63), price_bar (63252),
context_daily (32), features_daily (399, partial),
regime_snapshot (87), factor_snapshot (504),
candidate_idea (504), safe_gate_evolution_shadow (8).

---

## What the replay produced

Deterministic re-run of `scripts.run_paper_daily` for each business
date in the recovery window. No strategy changes, no threshold
tuning, no fabrication.

| Table | Pre-replay | Post-replay | Delta |
|---|---:|---:|---:|
| decision_log | 0 | **6** | +6 |
| paper_run_log | 0 | **6** | +6 |
| paper_trade | 0 | **0** | 0 |
| paper_trade_log | 0 | **0** | 0 |
| paper_shadow_log | 0 | **0** | 0 |
| paper_portfolio_snapshot | 0 | **6** | +6 |
| anomaly_event | 0 | **0** | 0 |

Per-date result (all 6 status=ok, paper_daily rc=0):

| Date | Engine | Action | Gates |
|---|---|---|---|
| 2026-04-24 | none | skip | 1/4 (credit_stable=T; rates/vrp/liq=unknown) |
| 2026-04-27 | none | skip | 1/4 |
| 2026-04-28 | none | skip | 1/4 |
| 2026-04-29 | none | skip | 1/4 |
| 2026-04-30 | none | skip | 1/4 |
| 2026-05-01 | none | skip | 1/4 |

All six dates landed in the same regime: `stress=True,
directional=False`, only one of four production gates favorable
(credit_stable). The selector did not fire on any date. This
matches what was observed live during the same window before the
wipe — the macro state was unfavorable for both engines.

---

## Honest accounting — what could NOT be recovered

The wipe destroyed years of accumulated history that lived **only**
in `compose_pgdata`. The 6-day replay window cannot reproduce any
of the following:

| Table | Pre-wipe | Replayed | Gap | Why |
|---|---:|---:|---:|---|
| paper_trade | 5 | 0 | -5 | Trades were entered on dates outside [4-24, 5-01]. The selector did not fire on any date in our recovery window. Nothing to fabricate. |
| paper_trade_log | 301 | 0 | -301 | Append-only log of every paper trade attempt across the platform's full operating history (months/years). Re-running 6 days regenerates 0 rows because the selector skipped on all 6. |
| paper_shadow_log | 660 | 0 | -660 | Shadow-strategy diagnostics persisted by every paper run since the system went live. 6 days of replay only adds shadow rows when the paper_daily shadow step writes new candidates — and on these 6 dates the shadow step persisted only diagnostic context flags (not new shadow_log rows). |
| decision_log | 16 | 6 | -10 | Decisions span the full operating window; we recover one per replayed date but lose all decisions from dates outside [4-24, 5-01]. |
| paper_run_log | 6 | 6 | 0 | The pre-wipe count of 6 happens to match exactly because runs prior to the recovery window had already been pruned/aged out. |

**Lost is lost.** Per the rule in
`docs/ops/DB_VOLUME_SAFETY.md` §6 of "Recovery if the wipe still
happens": **do not fabricate** paper_trade / paper_run_log /
decision_log / paper_shadow_log / paper_trade_log rows for dates
outside the replayed window. The replay is the only honest answer.

---

## Idempotency verification

After all 6 commits, re-running 2026-04-24 with the same command
(no `--replace-date`) returned `status=refused_existing`,
`paper_daily_rc=None`, no row deltas — exactly the contract the
script is meant to enforce.

```
2026-04-24  status=refused_existing    rc=None
    decision_log              1 →  1   (=0)
    paper_run_log             1 →  1   (=0)
    paper_portfolio_snapshot  1 →  1   (=0)
    note: rows present; --replace-date not set
```

---

## Safety properties that held throughout

* Replay refused `--commit` until
  `PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY`
  was set in the env.
* Replay default mode is `--dry-run` (no DB writes) when neither
  flag is given.
* Replay refused to overwrite an already-replayed date without
  `--replace-date`.
* Replay only writes to: `decision_log`, `paper_run_log`,
  `paper_trade`, `paper_trade_log`, `paper_shadow_log`,
  `paper_portfolio_snapshot`, `anomaly_event`, `context_daily`
  (the last via the underlying `run_paper_daily` diagnostic step).
* Replay does NOT touch: `research_*`, `options_paper_*`,
  `user_account`, `organization`, `subscription_*`,
  `safe_gate_evolution_shadow`, `candidate_idea`, `regime_snapshot`,
  `factor_snapshot`, `price_bar`, `asset`. CI test
  `apps/api/tests/unit/test_replay_paper_history.py::test_no_forbidden_table_writes_in_source`
  pins this list to source-code grep.
* Replay is NOT in the worker job registry, the tickloop scheduler,
  or any cron entry. CI test
  `test_replay_not_referenced_in_scheduler_or_cron` pins this.
* Every per-date `DELETE` statement is bound to `{'d': target}` —
  it is impossible for `--replace-date` to drop rows from a
  different date.

---

## Files added

* `scripts/replay_paper_history.py` — operator-only replay script
* `apps/api/tests/unit/test_replay_paper_history.py` — 20 safety
  tests pinning the contract above

## Test summary

```
apps/api/tests/unit/test_replay_paper_history.py ........  20 passed
apps/api/tests/unit/test_db_volume_safety_guard.py ..       2 passed
```
