# Phase 11X.2 — Controlled paper-only pilot execution

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase 11Z commit `9a25ff8`
**Scope:** add a tightly-constrained paper-only execution path that
opens **at most 1** 0.25× sized paper trade per day, gated by the
existing `safe_gate_evolution_shadow` diagnostic. Default OFF.

---

## 1. Files changed

| File | Type | Change |
|------|------|--------|
| `apps/api/src/config/__init__.py` | edit | + 5 settings (flag + 4 knobs) |
| `apps/api/src/data/strategy/safe_gate_evolution_pilot.py` | NEW | eligibility check + paper-only writer |
| `scripts/run_safe_gate_evolution_pilot.py` | NEW | CLI runner (dry-run default; `--execute` + flag both required to write) |
| `apps/api/tests/integration/test_safe_gate_evolution_pilot_pg.py` | NEW | 12 integration tests covering every gating condition |
| `docs/research/PHASE_11X_2_PILOT_EXECUTION.md` | NEW | this doc |

NOT changed:
- `apps/api/src/data/features/*` — zero diff (macro thresholds unchanged)
- `apps/api/src/domain/stock_engine/*` — zero diff (candidate scoring unchanged)
- `scripts/run_paper_daily.py` — zero diff in this turn (Phase 11Z changes already committed)
- selector / engine A / engine B / `paper_run_log.py` — zero diff

## 2. Feature flags + config

```python
SAFE_GATE_EVOLUTION_PILOT_EXECUTION: bool = False             # default OFF
SAFE_GATE_EVOLUTION_PILOT_MAX_TRADES_PER_DAY: int = 1
SAFE_GATE_EVOLUTION_PILOT_SIZE_MULTIPLIER: float = 0.25
SAFE_GATE_EVOLUTION_PILOT_MIN_MACRO_FAVORABLE: int = 1
SAFE_GATE_EVOLUTION_PILOT_NOTIONAL_USD: float = 1000.0        # × 0.25 = $250 per trade
```

Rollback: `SAFE_GATE_EVOLUTION_PILOT_EXECUTION=false` and restart.

## 3. Execution conditions (all required)

```
1. flag_enabled = SAFE_GATE_EVOLUTION_PILOT_EXECUTION (or flag_override)
2. safe_gate_evolution_shadow row exists for run_date AND would_trade=True
3. macro_favorable_count >= SAFE_GATE_EVOLUTION_PILOT_MIN_MACRO_FAVORABLE  (default ≥1)
4. unknown_count == 0  (no insufficient_data/missing_data/stale_data gates)
5. price_regime_favorable from shadow row
   (market_trend=uptrend AND vol_regime in {low,normal} AND sma50_above_sma200)
6. NO production paper trade already opened for run_date
   (paper_trade_log entry_date OR paper_trade.fill_ts::date with non-pilot reason)
7. NO pilot trade already opened for run_date  (idempotency)
8. shadow row supplies symbol AND that symbol resolves to an asset row
9. Latest price_bar close ≤ run_date exists for symbol
```

If all 9 hold → INSERT one paper_trade with:
* `side='buy'`
* `quantity = (NOTIONAL_USD × SIZE_MULTIPLIER) / fill_price`
* `reason = 'safe_gate_evolution_pilot:size_mult=0.25:macro_fav={N}:shadow_score={S}:shadow_conf={C}'`
* `recommendation_id=NULL`, `slippage_bps=NULL`, `realized_pnl=NULL` (paper-only fields, no broker / live)

## 4. Tests run safely

| Suite | Count | Result | DB |
|-------|-------|--------|-----|
| `test_safe_gate_evolution_pilot_pg.py` | 12 | 12 passed | isolated test DB (`pg-11v-test` container, db=`test`) |

Test DB chosen because the Phase 11Z safety guard refuses to drop_all
against the dev DB. Integration ran against
`postgresql+psycopg://test:test@pg-11v-test:5432/test`.

Test coverage:
1. flag off → no pilot trade
2. flag on + eligible → exactly 1 paper_trade row
3. paper_trade row tagged correctly (`safe_gate_evolution_pilot…`,
   recommendation_id NULL, slippage_bps NULL, realized_pnl NULL)
4. size multiplier applied (qty = notional × mult / price)
5. `macro_favorable_count=0` blocks
6. `unknown_count > 0` blocks
7. price regime unfavorable (vol=high) blocks
8. shadow `would_trade=False` blocks
9. production trade already opened blocks
10. pilot already opened blocks (idempotency)
11. max 1/day enforced (3 calls → 1 row)
12. paper_position never directly mutated

## 5. Controlled simulation — dev DB, 4-22 → 5-01

### Flag OFF (dry-run + execute with `--flag-override off`)
```
8 dates evaluated, 0 pilot trades opened, paper_trade=0
```

### Flag ON (`--execute --flag-override on`)
```
8 dates evaluated, 5 pilot trades opened
```

| run_date | eligible | opened | symbol | fill_price | qty | notional | reason |
|----------|----------|--------|--------|------------|-----|----------|--------|
| 2026-04-22 | F | F | — | — | — | — | `shadow_blocked:price_regime_unfavorable` (vol=high) |
| 2026-04-23 | F | F | — | — | — | — | `shadow_blocked:price_regime_unfavorable` |
| 2026-04-24 | F | F | — | — | — | — | `shadow_blocked:price_regime_unfavorable` |
| 2026-04-27 | T | **T** | UNH | 354.69 | 0.7048 | $250 | shadow_score=0.477, conf=73.87 |
| 2026-04-28 | T | **T** | UNH | 366.77 | 0.6816 | $250 | shadow_score=0.528, conf=76.41 |
| 2026-04-29 | T | **T** | UNH | 370.74 | 0.6743 | $250 | shadow_score=0.535, conf=76.75 |
| 2026-04-30 | T | **T** | UNH | 370.48 | 0.6748 | $250 | shadow_score=0.513, conf=75.66 |
| 2026-05-01 | T | **T** | UNH | 369.54 | 0.6765 | $250 | shadow_score=0.513, conf=75.64 |

Idempotent rerun: dates_evaluated=8, opened=0, all 5 dates report
`pilot_trade_already_opened`. paper_trade count remained at 5.

### Before / after row counts (dev DB)

| Table | Pre-pilot | Flag-OFF run | Flag-ON run | Idempotent rerun |
|-------|-----------|--------------|-------------|------------------|
| paper_trade        | 0 | 0 | 5 | 5 |
| paper_position     | 0 | 0 | 0 | 0 |
| paper_run_log      | 5 | 5 | 5 | 5 |
| decision_log       | 16 | 16 | 16 | 16 |
| paper_shadow_log   | 660 | 660 | 660 | 660 |
| paper_trade_log    | 301 | 301 | 301 | 301 |
| safe_gate_evolution_shadow | 8 | 8 | 8 | 8 |

`paper_position` never touched. Pilot does not invoke any
position-aggregation pipeline. Audit tables fully preserved.

## 6. Production strategy — proof unchanged

```
git diff apps/api/src/data/features/                → empty
git diff apps/api/src/domain/stock_engine/          → empty
git diff scripts/run_paper_daily.py (vs HEAD 9a25ff8) → empty
```

Macro thresholds (`d10y_5d<0`, `VRP > 6M median`, `HY OAS Δ20d ≤ 0`,
`NetLiq Δ20d > 0`), candidate scoring, selector logic, engine A,
engine B — all untouched.

The pilot module reads existing `context_daily` /
`safe_gate_evolution_shadow` / `paper_portfolio` / `asset` /
`price_bar` rows and writes only `paper_trade`. No new joins into
the strict-engine path.

## 7. No live / broker / options / ML changes

- ❌ No broker integration (no `Robinhood`, `Alpaca`, `IBKR` etc. imports)
- ❌ No `live_*` table writes
- ❌ No options table writes (`options_paper_trade`, `options_chain_snapshot`, etc.)
- ❌ No ML inference, calibration, or shadow-prediction writes
- ❌ No research_ro writes
- ✅ Only `paper_trade` INSERT under `flag_on AND all_conditions_met`
- ✅ `ML_CAN_AFFECT_TRADES`, `OPTIONS_ML_CAN_AFFECT_TRADES` unchanged (still False)

## 8. Rollback instructions

### Disable execution (instant)
```
# Either set in env / .env, then restart api + worker:
SAFE_GATE_EVOLUTION_PILOT_EXECUTION=false
```
Once disabled, every call to `evaluate_and_execute_pilot` returns
`opened=False, reason='pilot_flag_off'`. No new pilot rows.

### Reverse the 5 simulation trades (optional)
```sql
DELETE FROM paper_trade
WHERE COALESCE(reason,'') LIKE 'safe_gate_evolution_pilot%';
```
The pilot tag in `reason` makes pilot trades trivially identifiable.
`paper_position` was never mutated by the pilot, so no aggregation
unwind is needed.

### Full code rollback
```
git revert <pilot commit hash>
```
removes the new module, runner script, tests, and config knobs in
one go. The flag stays default-False even before revert, so a
runtime rollback is sufficient for most scenarios.

## 9. Commands run (this turn)

```bash
# read-only inspection
cat apps/api/src/config/__init__.py | head -80
docker exec compose-db-1 psql ... \d paper_trade
docker exec compose-db-1 psql ... \d paper_position

# create files
write apps/api/src/data/strategy/safe_gate_evolution_pilot.py
write scripts/run_safe_gate_evolution_pilot.py
write apps/api/tests/integration/test_safe_gate_evolution_pilot_pg.py
edit  apps/api/src/config/__init__.py    # +5 settings

# tests against ISOLATED test DB (pg-11v-test, db=test)
docker network connect compose_backend pg-11v-test
docker exec ... TEST_DATABASE_URL=postgresql+psycopg://test:test@pg-11v-test:5432/test \
  pytest apps/api/tests/integration/test_safe_gate_evolution_pilot_pg.py
# → 12 passed

# refresh stale shadow rows for 4-29..5-01 (UPDATE in place,
# not DELETE — shadow row schema treats inserts as DO NOTHING)
docker exec ... python -c "evaluate(s, d) + UPDATE shadow ..."

# dry-run flag off
docker exec ... python -m scripts.run_safe_gate_evolution_pilot \
  --start 2026-04-22 --end 2026-05-01
# → 8 dates, 0 trades

# execute flag off (--flag-override off)
docker exec ... python -m scripts.run_safe_gate_evolution_pilot \
  --start 2026-04-22 --end 2026-05-01 --execute --flag-override off
# → 8 dates, 0 trades, paper_trade=0

# execute flag on (--flag-override on)
docker exec ... python -m scripts.run_safe_gate_evolution_pilot \
  --start 2026-04-22 --end 2026-05-01 --execute --flag-override on
# → 8 dates, 5 trades opened (4-27..5-01 each)

# idempotent rerun
docker exec ... python -m scripts.run_safe_gate_evolution_pilot \
  --start 2026-04-22 --end 2026-05-01 --execute --flag-override on
# → 8 dates, 0 new trades, paper_trade still 5
```

## 10. Bottom line

* Tightly-scoped paper-only path. 5 settings, 1 module, 1 runner,
  12 tests, 1 doc.
* No strategy threshold changed. No selector / engine /
  candidate-scoring code edited.
* No broker, no live, no options, no ML, no research-layer changes.
* Flag default False — system behaves exactly as before this commit
  unless an operator explicitly turns it on.
* Idempotent on `(run_date, pilot_reason)`. Max 1 trade/day enforced
  by the precheck plus the explicit `MAX_TRADES_PER_DAY=1` config.
* Rollback = single env flag toggle plus optional 1-line DELETE
  filter (`reason LIKE 'safe_gate_evolution_pilot%'`).
* Auditable: every pilot row carries the size multiplier, macro
  count, shadow score, and shadow confidence in its `reason`
  column.
* Safe: `paper_position` never directly mutated; production audit
  tables (`paper_run_log`, `decision_log`, `paper_shadow_log`,
  `paper_trade_log`) fully preserved.
* Verified end-to-end: 5 simulated UNH trades opened across
  2026-04-27..2026-05-01 under flag-on, blocked correctly on
  4-22..4-24 due to `vol_regime=high`.
