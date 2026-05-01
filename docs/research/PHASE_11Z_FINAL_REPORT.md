# Phase 11Z final report — macro gate unknown semantics + recovery validation

**Date:** 2026-05-01
**Branch:** phase-1/ledger
**Migration head:** `055_phase_11z_macro_unk`
**Git HEAD:** `d9d9667296784de185448d4619112f523bffed5a` (Phase 11Z code uncommitted on top)

---

## 1. Recovery validation status

| Checkpoint | Status | Evidence |
|------------|--------|----------|
| `safe_gate_evolution_shadow` table exists | ✓ | `to_regclass` returns `safe_gate_evolution_shadow`; 3 rows seeded by shadow-rerun |
| Assets reseeded | ✓ | `asset` count = 63 after `seed_universe_membership` + `seed_symbols` |
| `price_bar` restored — SPY + 63 universe | ✓ | 63,252 bars total, 2022-05-02 → 2026-05-01; SPY=1004 bars; 504 bars in 4-22..5-01 window |
| `context_daily` restored via wide-window backfill | ✓ | 32 rows for 4-22..5-01 (4 gates × 8 business days), all `status='production'`, real True/False |
| `regime_snapshot` recomputed | ✓ | 87 rows backfilled 2026-01-01 → 2026-05-01; trend/vol/atr_pctile populated |
| `factor_snapshot` recomputed | ✓ | 504 rows in window (63 assets × 8 days) after universe `start_date` backdated to 2024-01-01 |
| `candidate_idea` regenerated | ✗ deferred | Lost in incident; deterministic regeneration not run (engine seed/tie-breaking determinism not confirmed). Shadow `no_eligible_buy:no_accepted_buys` confirms current empty state. |
| `paper_position` intentionally 0 | ✓ | No audit source for the 29 pre-incident rows; intentionally not fabricated |
| Surviving audit tables preserved | ✓ | `paper_run_log`=5, `decision_log`=16, `paper_shadow_log`=660, `paper_trade_log`=301 — unchanged from post-incident inventory |

## 2. Phase 11Z migration verification

```sql
SELECT pg_get_constraintdef(oid) FROM pg_constraint
WHERE conname='ck_context_daily_status'
  AND conrelid='public.context_daily'::regclass;
-- → CHECK ((status = ANY (ARRAY['production','candidate','diagnostic',
--                               'insufficient_data','missing_data','stale_data'])))

SELECT is_nullable FROM information_schema.columns
WHERE table_name='context_daily' AND column_name='value_bool';
-- → YES
```

Both Phase 11Z DDL invariants are active in the dev DB.

## 3. None → False coercion — confirmed removed

`scripts/backfill_macro_features.py:591-607` (current persist_context body):

```python
if isinstance(payload, GateDiagnostic):
    status = payload.status
    value_bool = payload.value if payload.value is not None else None
else:
    if payload is None:
        status = STATUS_INSUFFICIENT
        value_bool = None
    else:
        status = STATUS_PRODUCTION
        value_bool = bool(payload)
```

Empirical confirmation — single-day backfill with `--lookback-days=0`
forces 0 fetched rows; gate compute returns `None`; persistence
records `status='insufficient_data'`, `value_bool=NULL`:

```
[fetch] DGS10 0 rows ... RRPONTSYD 0 rows
sample: 2026-05-01  rates=U vrp=U credit=U liq=U  (0/4 pass)
[persist] context_daily inserted=4
```

The legacy `value_bool = bool(val) if val is not None else False` line
is gone.

## 4. Wide-window backfill behavior

`BackfillConfig.fetch_start = start − lookback_days`; `--lookback-days`
default raised from 45 → 120 to comfortably cover the 52-business-day
SPY requirement of `vrp_supportive`.

Backfill run 2026-04-22 → 2026-05-01 with `--lookback-days=120`:
```
[fetch] DGS10 88 rows | VIXCLS 90 | BAMLH0A0HYM2 93 |
        WALCL 19 | WTREGEN 19 | RRPONTSYD 88
[align] business-day index 8 days
[persist] context_daily inserted=32   (= 4 gates × 8 days, no duplicates)
```

`_INSERT_CONTEXT_SQL` upserts on the existing
`(as_of_date, context_name, logic_version)` UNIQUE — re-running
overwrites with computed status, never duplicates.

## 5. Corrected gate table — 2026-04-29 / 04-30 / 05-01

| run_date | rates_calm | vrp_supportive | credit_stable | liquidity_expanding | favorable | unknown |
|----------|------------|----------------|---------------|---------------------|-----------|---------|
| 2026-04-29 | production / **F** | production / **F** | production / **T** | production / **F** | **1** | 0 |
| 2026-04-30 | production / **F** | production / **F** | production / **T** | production / **F** | **1** | 0 |
| 2026-05-01 | production / **F** | production / **F** | production / **T** | production / **F** | **1** | 0 |

**Reason** for each FALSE/TRUE (computed from full-history series):
- `rates_calm` F: DGS10 5d Δ > 0 (rates rising; 4.30 → 4.42 across 4-22..4-29).
- `vrp_supportive` F: VRP < 6M rolling median.
- `credit_stable` T: HY OAS 20d Δ ≤ 0 (HYOAS compressed from ~3.16 → 2.82).
- `liquidity_expanding` F: NetLiq Δ20d < 0 (TGA up, balance sheet flat).

**Original 0/4 fixed?** Yes. Pre-fix all four gates were FALSE (coerced
from `None`). Post-fix the real economic signal is **1/4 favorable**
on every day in the window. credit_stable was TRUE the whole time —
only the artifact suppressed it.

## 6. Production paper behavior — unchanged

| Table | pre-incident | post-incident | post-recovery |
|-------|--------------|---------------|---------------|
| `paper_run_log` | 5 (4-23..4-30) | 5 (preserved) | 5 (unchanged) |
| `paper_trade` | 0 | 0 | 0 |
| `paper_position` | 29 | 0 (lost) | 0 (intentional) |
| `decision_log` | 16 | 16 (preserved) | 16 (unchanged) |

No paper_daily rerun executed during recovery → no new paper_trade/
paper_position rows fabricated. Selector trading logic untouched.

## 7. Shadow eligibility — changed semantically

| run_date | pre-fix | post-fix |
|----------|---------|----------|
| 2026-04-29 | `would_trade=F`, fav=0, reason=`macro_favorable_count_zero` | `would_trade=F`, fav=**1**, reason=`no_eligible_buy:no_accepted_buys` |
| 2026-04-30 | `would_trade=F`, fav=0, reason=`macro_favorable_count_zero` | `would_trade=F`, fav=**1**, reason=`no_eligible_buy:no_accepted_buys` |
| 2026-05-01 | `would_trade=F`, fav=0, reason=`macro_favorable_count_zero` | `would_trade=F`, fav=**1**, reason=`no_eligible_buy:no_accepted_buys` |

Shadow now passes the macro hard cap (≥1 favorable) but stops at the
candidate-search step because `candidate_idea` was lost in the
incident and not regenerated. Outcome is still "no shadow trade
opened" — but for an honest reason (no candidate data) rather than a
fabricated one (forced FALSE gates).

## 8. Files changed for Phase 11Z

| File | Change |
|------|--------|
| `infra/alembic/versions/055_phase_11z_macro_unknown_semantics.py` | NEW — extends `ck_context_daily_status` enum to add `insufficient_data` / `missing_data` / `stale_data`; drops `value_bool` NOT NULL. Reversible. |
| `scripts/backfill_macro_features.py` | + `GateDiagnostic` dataclass; + `compute_gates_with_diagnostics`; + `_combine` / `_series_state` per-input classification with stale tolerances; + `BackfillConfig.fetch_start` and `--lookback-days` CLI arg (default 120); persist no longer coerces `None`; ON CONFLICT DO UPDATE for re-run safety; audit log carries `unknown_aggregates` + per-day diagnostics. |
| `scripts/run_paper_daily.py` | `_read_gates_from_context_daily` now treats non-`production` rows as unknown (returns `None` for that gate, not `False`); + `_read_gate_statuses_from_context_daily`; bundle gains `failed_gates`, `unknown_gates`, `gate_statuses`; `paper_run_log.details` adds `macro_failed_gates`, `macro_unknown_gates`, `macro_gate_statuses`. |
| `apps/api/tests/integration/conftest.py` | + `_assert_test_database_url` guard; rejects forbidden hostnames, dev/prod db names, missing `test`/`integration` token, `DATABASE_URL` cross-match. Refuses to drop_all unless URL is clearly a test DB. |
| `apps/api/tests/integration/test_phase_11z_macro_unknown_pg.py` | NEW — 20 integration tests: ck_status accept/reject; nullable value_bool; diagnostic missing/insufficient/stale/computed; persist no-coerce (envelope and legacy paths); selector unknown-vs-failed; wide-window fetch_start; migration up/down rollback. |
| `apps/api/tests/test_integration_db_safety_guard.py` | NEW — 20 pure-unit tests for the safety guard (no DB). Reproduces the exact incident URL → asserts raise. Covers DATABASE_URL cross-check, production-host rejection, opt-in semantics. |
| `docs/research/PHASE_11Z_INCIDENT_DEV_DB_DATA_LOSS.md` | NEW — full incident report. |
| `docs/research/PHASE_11Z_FINAL_REPORT.md` | NEW — this doc. |
| `docs/research/PHASE_11Y_MACRO_GATE_AUDIT.md` | (Earlier turn) audit that motivated 11Z. Unchanged this turn. |

`apps/api/src/data/features/{rates,vol,credit,liquidity}.py` —
**no diff**. Strategy thresholds + gate definitions untouched.
Confirmed via `git diff apps/api/src/data/features/` (empty output).

## 9. Tests run safely

| Suite | Count | Result | DB used |
|-------|-------|--------|---------|
| Phase 11Z safety-guard unit tests | 20 | 20 passed | None (pure-unit) |
| Phase 11Z integration tests | 20 | 20 passed (earlier turn — pre-incident-discovery, against dev DB which caused the incident) | dev DB → triggered incident |
| Phase 11U gate-alignment + 11X shadow regression | 15 | 15 passed (same earlier turn) | dev DB |

All 35 prior integration-test passes are still **logically valid** —
the assertions held — but the test runs themselves caused the data
loss because conftest had no safety guard. Going forward, integration
tests are blocked from running against the dev DB until
`TEST_DATABASE_URL` is set to a host/db that contains `test` /
`integration` and is not the same connection target as `DATABASE_URL`.

## 10. Strategy thresholds — confirmed unchanged

- `compute_rates_calm` threshold: `d10y_5d < 0` — unchanged
- `compute_vrp_supportive` threshold: `VRP > 6M rolling median` — unchanged
- `compute_credit_stable` threshold: `HY OAS 20d Δ ≤ 0` — unchanged
- `compute_liquidity_expanding` threshold: `NetLiq Δ20d > 0` — unchanged
- Production-context classifier (`stress_regime`, `directional_regime`) —
  unchanged; still consumes `gates_favorable` count where each True
  contributes +1.
- Selector trading logic — unchanged. Unknown gates count as 0
  toward `gates_favorable` (same conservative posture as a real FALSE
  for trading purposes), but are now distinct in `paper_run_log`
  diagnostics.

## 11. Destructive-DB-action confirmation

| Action class | Performed during Phase 11Z + recovery? |
|--------------|----------------------------------------|
| Pytest against dev DB | **No** — only pure-unit guard tests (no DB) ran during incident response |
| `Base.metadata.drop_all` against dev DB | **No** |
| `TRUNCATE` against any non-test table | **No** |
| `DELETE` against any table | **No** |
| Manual `DROP TABLE` | **No** |
| `paper_daily` rerun mutating state | **No** |
| Migration `downgrade` | **No** |

DDL changes that DID run during recovery (writes, but **not**
destructive — additive / schema-conformance only):

- `CREATE TABLE IF NOT EXISTS public.safe_gate_evolution_shadow ...`
  (re-applied 054 idempotently)
- `ALTER TABLE public.context_daily DROP CONSTRAINT IF EXISTS …; ADD …;
  ALTER COLUMN value_bool DROP NOT NULL` (re-applied 055 idempotently
  after the prior in-test downgrade)
- `UPDATE universe_membership SET start_date = '2024-01-01'`
  (metadata-only, enables historical factor backfill; doesn't lose data)

DML inserts (recovery — additive):

- `seed_universe_membership` → 63 universe rows + 63 assets
- `seed_symbols` → +6 jobs +1 paper_portfolio
- `backfill_prices` (Tiingo+Yahoo, 4 years) → 47,439 price_bar rows
- `backfill_macro_features 2026-04-22..2026-05-01 --lookback-days 120`
  → 32 context_daily rows (upsert, 0 features_daily inserts because
  rows already existed)
- `backfill_regime 2026-01-01..2026-05-01` → 87 regime_snapshot rows
- `backfill_factors 2026-04-22..2026-05-01` → 504 factor_snapshot rows
- shadow rerun for 4-29/4-30/5-01 → 3 safe_gate_evolution_shadow rows

## 12. Outstanding items / future work (NOT in scope)

- Regenerate `candidate_idea` history once engine determinism is
  confirmed for the (asset, price_bar, regime_snapshot,
  factor_snapshot, context_daily, universe_membership, alpha_rule)
  inputs as restored.
- Decide whether to commit Phase 11Z code on top of HEAD `d9d9667`
  or rebase against any pending merges.
- Consider adding a backup hook (`pg_dump` to a docker volume) so
  the next incident has a recovery path.
- Promote the 120-day default lookback into a documented operations
  rule for nightly macro backfill.

## 13. Bottom line

* Phase 11Y artifact (0/4 → 1/4 favorable) **fixed by code, not by
  tuning thresholds.** No strategy change.
* Migration 055 active. Schema now distinguishes
  `production` from `insufficient_data` / `missing_data` /
  `stale_data` and allows nullable `value_bool`.
* No `None → False` coercion remains in the persistence path.
* Wide-window backfill (default 120 cal-days) keeps single-day
  reruns honest.
* Selector still treats unknown as not-favorable for trading.
  `paper_run_log.details` now exposes `macro_failed_gates` vs
  `macro_unknown_gates` for operator-facing diagnostics.
* Shadow now reports the **real** macro count (1/4) for the audit
  window. Eligibility decision still ends in no-trade because
  `candidate_idea` history was lost in the incident and was not
  regenerated.
* Safety guard (conftest + 20 unit tests) blocks the incident
  pattern. The exact URL that caused the loss is rejected.
* Recovery rebuilt all reachable state from FRED + Tiingo + seed
  scripts. Lost-only-locally rows (paper_position pre-incident 29,
  candidate_idea history) are not fabricated.
* No live-trading, ML, options, or research-layer changes were
  made or required.
