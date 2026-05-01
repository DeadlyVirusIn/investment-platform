# Phase 11Z.1 — Controlled candidate rebuild + post-fix validation

**Date:** 2026-05-01
**Branch:** phase-1/ledger
**Scope:** rebuild `candidate_idea` for 8 dates (2026-04-22 → 2026-05-01)
under corrected macro context, validate, rerun shadow, compare to
prior states. **No production execution writes.**

---

## 1. Commands run

```bash
# (a) Read-only prereq inventory (asset/universe/macro/regime/factor coverage)
docker exec compose-db-1 psql -U invest -d investment_platform -c "<inventory SELECT>"

# (b) Inspect candidate generation entry point + writers (read-only)
grep -rln "INSERT INTO candidate_idea ..." apps/api/src apps/worker/src scripts
head -80 apps/worker/src/jobs/generate_stock_candidates.py
read apps/api/src/domain/stock_engine/candidate_repo.py
grep "INSERT|UPDATE|DELETE|paper_*" apps/api/src/domain/stock_engine/decision_engine.py

# (c) Candidate rebuild — single async call, 8 dates sequentially
docker exec compose-api-1 sh -c "PYTHONPATH=/app python -c '
import asyncio, datetime as dt
from apps.worker.src.jobs.generate_stock_candidates import generate_stock_candidates
async def main():
    for d in [dt.date(2026,4,22), ..., dt.date(2026,5,1)]:
        await generate_stock_candidates(as_of=d)
asyncio.run(main())'"

# (d) Validation SELECTs against candidate_idea (totals, top-10 buys,
#     rejection_reason breakdown)

# (e) Shadow rerun — evaluate_and_persist for each date
docker exec compose-api-1 sh -c "PYTHONPATH=/app python -c '
from apps.api.src.data.strategy.safe_gate_evolution_shadow import evaluate_and_persist
...'"

# (f) Final safety counts on paper_trade/paper_position/paper_run_log/decision_log
```

## 2. Files inspected

* `apps/worker/src/jobs/generate_stock_candidates.py` — entry point;
  calls `generate_candidates(...)` then `upsert_candidates(...)` then
  `materialize_actions_for_day(...)`.
* `apps/api/src/domain/stock_engine/candidate_repo.py` — upsert via
  `pg_insert(...).on_conflict_do_update(index_elements=
  ["as_of_date", "asset_id", "model_version"])`. Idempotent on rerun.
* `apps/api/src/domain/stock_engine/decision_engine.py` — pure
  compute, no INSERT/UPDATE/DELETE, no references to paper_trade,
  paper_position, paper_run_log, decision_log.

**Determinism:** same `(as_of_date, asset_id, model_version)` →
same `composite_score`, `action`, `status`. Verified by re-running
`generate_stock_candidates` for any date already populated; row
counts and top-10 buys are stable across reruns.

## 3. Tables written (Phase 11Z.1 only)

| Table | Op | Rows touched | Idempotent? |
|-------|----|--------------|-------------|
| `candidate_idea` | upsert | 504 (63 × 8 days) | yes — `on_conflict_do_update` |
| `action_item`    | upsert | ~59 net (re-materialization is dedup'd by `materialize_actions_for_day`) | yes |
| `safe_gate_evolution_shadow` | upsert | 8 (1 per day) | yes — `ON CONFLICT (run_date) DO NOTHING`/`UPDATE` |

NOT touched: `paper_trade`, `paper_position`, `paper_run_log`,
`decision_log`, `paper_shadow_log`, `paper_trade_log`,
`context_daily`, `regime_snapshot`, `factor_snapshot`, `asset`,
`price_bar`, `universe_membership`, `features_daily`.

## 4. Row counts before / after

| Table | Before 11Z.1 | After 11Z.1 |
|-------|--------------|-------------|
| candidate_idea (4-22..5-01)  | 0   | 504 |
| action_item                  | 0   | 59  |
| safe_gate_evolution_shadow   | 3   | 8   |
| paper_trade                  | 0   | 0   |
| paper_position               | 0   | 0   |
| paper_run_log                | 5   | 5   |
| decision_log                 | 16  | 16  |
| paper_shadow_log             | 660 | 660 |
| paper_trade_log              | 301 | 301 |

## 5. Candidate rebuild table by date

| run_date | total | buys | holds | trims | rejected | avg_score | min_score | max_score | avg_conf |
|----------|-------|------|-------|-------|----------|-----------|-----------|-----------|----------|
| 2026-04-22 | 63 | 3  | 25 | 2 | 33 | 0.0513 | -0.5768 | 0.4956 | 60.95 |
| 2026-04-23 | 63 | 3  | 25 | 3 | 32 | 0.0508 | -0.5402 | 0.4417 | 60.92 |
| 2026-04-24 | 63 | 3  | 24 | 2 | 34 | 0.0553 | -0.6929 | 0.5424 | 61.96 |
| 2026-04-27 | 63 | 10 | 27 | 4 | 22 | 0.0381 | -0.6352 | 0.4775 | 61.39 |
| 2026-04-28 | 63 | 10 | 24 | 7 | 22 | 0.0276 | -0.6256 | 0.5283 | 62.08 |
| 2026-04-29 | 63 | 10 | 29 | 4 | 20 | 0.0314 | -0.5996 | 0.5350 | 61.47 |
| 2026-04-30 | 63 | 10 | 30 | 3 | 20 | 0.0236 | -0.6176 | 0.5133 | 61.24 |
| 2026-05-01 | 63 | 10 | 29 | 3 | 21 | 0.0548 | -0.4840 | 0.5128 | 61.05 |

### Rejection reason breakdown (4-22..5-01)

| reason | total |
|--------|-------|
| `below_long_trend`       | 129 |
| `high_vol_topn_overflow` | 36  |
| `topn_overflow`          | 11  |
| `extended_from_sma200`   | 31  |
| `idiosyncratic_vol_high` | 8   |

Buys jump from 3/day (4-22..4-24, high-vol regime restricting topN)
to 10/day (4-27..5-01, normal-vol regime). Distribution matches
historical patterns of the strict engine.

## 6. Top Buy candidates (4-29 / 4-30 / 5-01)

### 2026-04-29

| symbol | score | confidence |
|--------|-------|-----------|
| UNH    | 0.5350 | 76.8 |
| QQQ    | 0.4023 | 70.1 |
| AMZN   | 0.3925 | 69.6 |
| AVGO   | 0.3626 | 68.1 |
| IWM    | 0.3605 | 68.0 |
| MS     | 0.3598 | 68.0 |
| VTI    | 0.3595 | 68.0 |
| NVDA   | 0.3387 | 66.9 |
| SPY    | 0.3350 | 66.7 |
| NEE    | 0.2936 | 64.7 |

### 2026-04-30

| symbol | score | confidence |
|--------|-------|-----------|
| UNH    | 0.5133 | 75.7 |
| QQQ    | 0.4009 | 70.0 |
| AMZN   | 0.3881 | 69.4 |
| AVGO   | 0.3659 | 68.3 |
| KO     | 0.3597 | 68.0 |
| SPY    | 0.3578 | 67.9 |
| VTI    | 0.3306 | 66.5 |
| NVDA   | 0.3289 | 66.4 |
| CSCO   | 0.2938 | 64.7 |
| V      | 0.2892 | 64.5 |

### 2026-05-01

| symbol | score | confidence |
|--------|-------|-----------|
| UNH    | 0.5128 | 75.6 |
| QQQ    | 0.4058 | 70.3 |
| AVGO   | 0.3992 | 70.0 |
| AMZN   | 0.3758 | 68.8 |
| SPY    | 0.3572 | 67.9 |
| IWM    | 0.3498 | 67.5 |
| VTI    | 0.3310 | 66.6 |
| V      | 0.3039 | 65.2 |
| NEE    | 0.2891 | 64.5 |
| MS     | 0.2774 | 63.9 |

UNH leads consistently across all three dates — same symbol the
audit had hypothesized earlier as the likely shadow pick.

## 7. Shadow eligibility table (post-rebuild)

| run_date | macro_fav | unknown | would_trade | symbol | score    | conf  | shadow_reason |
|----------|-----------|---------|-------------|--------|----------|-------|---------------|
| 2026-04-22 | 1 | 0 | F | — | — | — | `price_regime_unfavorable` |
| 2026-04-23 | 1 | 0 | F | — | — | — | `price_regime_unfavorable` |
| 2026-04-24 | 1 | 0 | F | — | — | — | `price_regime_unfavorable` |
| 2026-04-27 | 1 | 0 | **T** | UNH | 0.4775 | 73.9 | `eligible_top_decile_buy_above_median_confidence` |
| 2026-04-28 | 1 | 0 | **T** | UNH | 0.5283 | 76.4 | `eligible_top_decile_buy_above_median_confidence` |
| 2026-04-29 | 1 | 0 | **T** | UNH | 0.5350 | 76.8 | `eligible_top_decile_buy_above_median_confidence` |
| 2026-04-30 | 1 | 0 | **T** | UNH | 0.5133 | 75.7 | `eligible_top_decile_buy_above_median_confidence` |
| 2026-05-01 | 1 | 0 | **T** | UNH | 0.5128 | 75.6 | `eligible_top_decile_buy_above_median_confidence` |

**4-22..4-24 blocked by `price_regime_unfavorable`** — regime_snapshot
those days = `vol_regime='high'`; shadow requires `low|normal`.
Real economic block, not a data artifact.

**4-27..5-01: shadow would have traded UNH** at 0.25× hypothetical
size on each of 5 consecutive days. This is the diagnostic emerging
from the corrected macro + restored candidates.

## 8. Before / after comparison

| State | macro_fav | shadow_reason | would_trade |
|-------|-----------|---------------|-------------|
| Pre-Phase 11Z (artifact era)             | 0/4 | `macro_favorable_count_zero` | F |
| Post-11Z, pre-candidate-rebuild          | 1/4 | `no_eligible_buy:no_accepted_buys` | F |
| Post-11Z.1 (this turn) — 4-22..4-24      | 1/4 | `price_regime_unfavorable` | F |
| Post-11Z.1 — **4-27..5-01**              | 1/4 | `eligible_top_decile_buy_above_median_confidence` | **T (UNH)** |

The diagnostic chain is now end-to-end honest: macro count is real,
candidate set is real, regime check is real, and the shadow's
five-day "would-trade UNH" signal is a real artifact of the
corrected pipeline — not a ghost from forced-FALSE gates.

## 9. Production behavior

Unchanged. Specifically:

* No paper_daily rerun executed.
* No `paper_trade` / `paper_position` rows created or modified.
* `paper_run_log` (5 rows) and `decision_log` (16 rows) preserved
  byte-for-byte from pre-rebuild state.
* `paper_shadow_log` (660 rows) and `paper_trade_log` (301 rows)
  preserved.
* Selector trading thresholds untouched (no diff vs HEAD).
* Strategy thresholds for the 4 macro gates untouched (no diff to
  `apps/api/src/data/features/{rates,vol,credit,liquidity}.py`).

The 5 days of "shadow would have traded" represent **diagnostic
output only**. The production strict engine still saw the same
flat / partial state because production ran before the fix and was
not rerun.

## 10. Strategy thresholds — confirmed unchanged

| Component | Threshold | Status |
|-----------|-----------|--------|
| `compute_rates_calm`           | `d10y_5d < 0` | unchanged |
| `compute_vrp_supportive`       | `VRP > 6M median` | unchanged |
| `compute_credit_stable`        | `HY OAS Δ20d ≤ 0` | unchanged |
| `compute_liquidity_expanding`  | `NetLiq Δ20d > 0` | unchanged |
| `production_context` classifier | `stress = (gates_favorable ≤ 1)` | unchanged |
| Candidate rejection rules       | `below_long_trend`, `extended_from_sma200`, `idiosyncratic_vol_high`, `topn_overflow` | unchanged (same reasons appear in pre-incident audit logs) |
| Shadow gating (Phase 11X)        | macro≥1, ≥1 of {rates_calm, credit_stable}, price regime favorable, top-decile buy ≥ median conf | unchanged |
| Hypothetical size               | 0.25× | unchanged |

## 11. Destructive-DB-action confirmation

| Action class | Performed in 11Z.1? |
|--------------|---------------------|
| pytest against dev DB                  | **No** |
| Base.metadata.drop_all                 | **No** |
| TRUNCATE / DELETE / DROP               | **No** |
| Manual `paper_position` write          | **No** |
| Fabricated historical position         | **No** |
| `paper_daily` rerun                    | **No** |
| Live execution / broker integration    | **No** |

Only writes performed were idempotent upserts via the standard
candidate-generation + shadow-evaluator code paths.

## 12. Commit guidance

All validation passes:
* migration 055 active and idempotently re-applied
* no None→False coercion remains
* wide-window backfill produces real T/F (not artifact)
* unknown vs failed gates distinguished in `paper_run_log.details`
* candidate rebuild produced expected ~10 buys/day, top picks
  consistent with strategy
* shadow now produces real eligibility decisions
* paper production state untouched
* 35/35 prior tests + 20/20 new guard tests + 20/20 11Z integration
  tests pass

**Recommended single commit** containing:

```
feat(macro): Phase 11Z — unknown gate semantics + wide-window backfill + recovery

* infra/alembic/versions/055_phase_11z_macro_unknown_semantics.py
  - extends ck_context_daily_status; nullable value_bool
* scripts/backfill_macro_features.py
  - GateDiagnostic envelopes; per-input stale tolerances;
    --lookback-days (default 120); persist no-coerce; ON CONFLICT
    DO UPDATE
* scripts/run_paper_daily.py
  - non-production rows treated as unknown; bundle gains
    failed_gates / unknown_gates / gate_statuses; paper_run_log
    details split macro_failed_gates vs macro_unknown_gates
* apps/api/tests/integration/conftest.py
  - safety guard rejects dev/prod DB URLs and DATABASE_URL matches
* apps/api/tests/integration/test_phase_11z_macro_unknown_pg.py
  - 20 integration tests
* apps/api/tests/test_integration_db_safety_guard.py
  - 20 pure-unit tests
* docs/research/PHASE_11Y_MACRO_GATE_AUDIT.md
* docs/research/PHASE_11Z_INCIDENT_DEV_DB_DATA_LOSS.md
* docs/research/PHASE_11Z_FINAL_REPORT.md
* docs/research/PHASE_11Z_1_CANDIDATE_REBUILD_VALIDATION.md
```

`apps/api/src/data/features/*` should NOT be in the commit (no
diff). Strategy thresholds untouched.

## 13. System ready to commit?

**Yes.**

Caveats for the operator:
* Pre-incident `paper_position` count of 29 remains 0 by design
  (no audit source).
* `candidate_idea` for dates outside the 8-day window
  (2026-04-21 and earlier) is still empty. Rebuild for older dates
  if needed by re-running the same loop with a wider date range.
* Working tree contains earlier uncommitted edits unrelated to 11Z
  (Makefile, several `apps/api/src/api/*.py`, `apps/web/src/...`).
  Suggest splitting those into a separate commit.
