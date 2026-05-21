# Quant Repos → Investment-Platform Reusable Concepts

> Research output from `/octo:research` (deep, 2026-04-19). Repos analyzed:
> vectorbt, machine-learning-for-trading (Stefan Jansen), vectorbt-backtesting-skills,
> algo-trading-template, pytrade.org. Goal: extract reusable concepts only — NOT
> framework adoption. Maps to existing Phase-1 ledger system on branch `phase-1/ledger`.

## 1. Executive Summary

Five repos analyzed. `feature_engine.py` + `recommendation_engine.py` are well-structured
but have three concrete gaps the quant ecosystem fills cleanly without architectural change:

- (a) No labeling logic to score recommendation outcomes — `RecommendationOutcome.realized_30d_return` columns sit NULL.
- (b) No backtesting/walk-forward harness — can't yet answer "did this engine version beat last quarter's".
- (c) Feature catalog is shallow (5 indicators) vs. ~100+ canonical alpha factors readily portable.

Recommended adoption: copy ~6 algorithms + add 2 small dependencies (`empyrical-reloaded`,
`pandas-ta`). Skip vectorbt, Zipline, mlfinlab as dependencies (license/weight wrong).

---

## 2. Key Themes

### Theme A — Labeling: Triple-Barrier as Outcome Scorer

`RecommendationOutcome` table already has `price_at_recommendation`, `price_after_30d`,
`realized_30d_return` columns (migration 002, lines 35–67). Currently NULL. The
**triple-barrier method** [Lopez de Prado AFML Ch.3] turns these stubs into a proper label:

```python
# pseudocode — drop into apps/worker/src/jobs/score_outcomes.py
def triple_barrier_label(close_series, entry_ts, sigma_t0, pt=2.0, sl=2.0, n_bars=63):
    p0 = close_series.loc[entry_ts]
    horizon = close_series.loc[entry_ts : entry_ts + n_bars]
    path = horizon / p0 - 1
    up_hit = path[path > pt * sigma_t0].index.min()
    dn_hit = path[path < -sl * sigma_t0].index.min()
    first = min(filter(pd.notna, [up_hit, dn_hit, horizon.index[-1]]))
    if first == up_hit: return +1   # "good buy"
    if first == dn_hit: return -1   # "bad buy / good sell"
    return int(np.sign(path.iloc[-1]))  # vertical
```

Adds two columns: `barrier_label ∈ {-1,0,+1}` and `barrier_first_touch_at`. Defines
"good trade" objectively without ML. Sources: hudsonthames.org triple-barrier;
mlfinlab `apply_pt_sl_on_t1`.

### Theme B — Feature Engineering: Steal Formulas, Not Frameworks

ML4T's `24_alpha_factor_library` catalogs ~100 alpha factors as plain pandas formulas.
Categories worth porting into `feature_engine.py`:

| Family | Add Signal | Formula |
|--------|-----------|---------|
| Momentum (skip-month) | `mom_12_1` | `price[t-21]/price[t-252] - 1` |
| Mean-reversion | `zscore_20` | `(price - SMA20) / std20` |
| Distance-to-high | `dist_52w_high` | `price / rolling_max(252) - 1` |
| Realized vol (Parkinson) | `parkinson_vol` | `sqrt((1/(4·ln2·N)) · Σ ln(H/L)²)` |
| Trend quality | `adx_14` | TA-Lib ADX |
| BB position | `bb_pct` | `(price - lower) / (upper - lower)` |

These slot into existing `FamilyOut` / `SignalOut` system — each is a new `SignalOut`
under `trend_momentum` or a new `mean_reversion` family in `engine.yaml`.
Source: github.com/stefan-jansen/machine-learning-for-trading/24_alpha_factor_library.

### Theme C — Evaluation Metrics: Use empyrical-reloaded

Don't hand-code Sharpe/Sortino/Calmar/MaxDD-Duration — `empyrical-reloaded` (Apache-2.0,
~50KB) ships canonical implementations. Vectorbt's `returns/nb.py` confirms standard formulas:

- Sharpe: `mean(r-rf) / std(r-rf) · √ann_factor`
- Sortino: `mean(r-target) · ann / downside_std`
- Calmar: `ann_return / |max_dd|`
- Profit factor: `Σ wins / |Σ losses|`
- Expectancy: `p_win·avg_win - p_loss·avg_loss`
- **Probabilistic Sharpe Ratio (PSR)**: corrects for skew/kurtosis — important when sample is small

Add a new endpoint `GET /performance/metrics?window=30d` aggregating `RecommendationOutcome`
rows. Source: github.com/stefan-jansen/empyrical-reloaded.

### Theme D — Backtesting: Walk-Forward Without a Framework

You don't need vectorbt or backtesting.py. Add `apps/api/src/domain/backtest/walk_forward.py`:

```python
def walk_forward(start, end, train_window=365, test_window=63, step=63):
    cursor = start + train_window
    while cursor + test_window <= end:
        train = (cursor - train_window, cursor)
        test  = (cursor, cursor + test_window)
        yield train, test
        cursor += step
```

For each `(train, test)` window: snapshot `engine.yaml` config, generate recs at every
test bar, score with triple-barrier, compute Sharpe/hit-rate. Output **Walk-Forward
Efficiency** = `OOS_return / IS_return` — accept config change only if WFE > 0.5.
Source: vectorbt-backtesting-skills `walk_forward/template.py`.

If ML added later, also adopt **Purged K-Fold + Embargo** (drop train labels whose `t1`
overlaps test window + skip 1-2% of bars after each fold). Source: AFML Ch.7.

```python
def purged_kfold(t1, n_splits=5, embargo_pct=0.01):
    indices = np.arange(len(t1))
    embargo = int(len(t1) * embargo_pct)
    for test_idx in np.array_split(indices, n_splits):
        t0, t1_end = test_idx[0], test_idx[-1]
        train_mask = (t1.values < t0) | (indices > t1_end + embargo)
        yield indices[train_mask], test_idx
```

### Theme E — Risk / Sizing: Signal-Weighted Position Sizes

Engine emits `composite_score ∈ [-1,+1]` and `confidence ∈ [0,1]`. Currently action is just
bucketed (Buy/Hold/Trim/Sell). Two cheap upgrades for `recommendation_engine.py`:

1. **Suggested position size**: `size_pct = clip(|composite_score| · confidence · kelly_fraction, 0, max_pos)` where `kelly_fraction = 0.25`. Add column to `Recommendation` table.
2. **ATR-based stop**: `stop_price = entry · (1 - 2·ATR/entry)` for longs. ATR already computed in feature_engine line ~321. Surface in `thesis` field.

Kelly formulas:
- Binary: `f* = (p·b - (1-p)) / b` using `win_rate` and `avg_win/avg_loss` from outcomes
- Continuous Gaussian: `f* = μ/σ²`
- Always use **fractional** (¼ Kelly) — full Kelly is too volatile

Source: ML4T Ch.5 `05_kelly_rule.ipynb`.

---

## 3. Key Takeaways

### High-Value Concepts to Adopt

1. **Triple-barrier outcome labeling** → fills `RecommendationOutcome` columns with meaningful `barrier_label`.
2. **~10 new alpha factor formulas** → copy from ML4T appendix into `feature_engine.py`.
3. **`empyrical-reloaded` dependency** → Sharpe/Sortino/Calmar/PSR/MaxDD-Duration without rolling your own.
4. **`pandas-ta` dependency** → batch indicator computation; replace hand-coded `_sma`, `_rsi`, `_atr` (keep Decimal precision wrapper).
5. **Walk-forward harness** (~80 lines) → regression test for engine.yaml config changes; produces WFE ratio.
6. **Signal-weighted position sizing** → `size_pct = composite·confidence·¼Kelly`, capped at `max_pos`.
7. **ATR-based stop suggestion** in `thesis` text.
8. **Probabilistic Sharpe Ratio** → guards against small-sample false positives in `/performance` endpoint.
9. **Meta-labeling overlay** (later, when ≥6 months of outcomes) → train binary "act / skip" classifier on top of rule output. Improves precision without touching rule layer.

### What to Ignore

- **vectorbt as a dependency** — Apache-2.0 but ~30MB + Numba JIT toolchain; don't need vectorized backtesting at per-asset daily scale. Steal labeling formulas from `vectorbt/labels/nb.py`, leave the framework.
- **Zipline / pyfolio / alphalens as deps** — heavyweight, opinionated event-loop conflicts with FastAPI service shape.
- **mlfinlab as a dep** — AGPL/commercial; license-poisons proprietary code. Copy the algorithm only.
- **backtesting.py** — AGPL, same reason.
- **Numba JIT, custom dtypes, IndicatorFactory metaclass, pandas accessors** (vectorbt internals) — solving problems you don't have.
- **Deep learning, RL, GAN, NLP chapters** of ML4T — Phase 3+ at earliest.
- **Fractional Differentiation** — only useful with ML; rule engine doesn't need it.
- **CPCV (combinatorial purged CV)** — overkill until you have a model selection problem.
- **Lumibot / algo-trading-template** — single example, no risk overlays. Skip.
- **vectorbt-backtesting-skills as a skill pack** — useful pattern reference for *if you ever ship Claude skills*, not for the engine itself.

### Mapping to Current Files

| Concept | Target File | Insertion Point |
|---|---|---|
| Triple-barrier scorer | new: `apps/worker/src/jobs/score_outcomes.py` | called daily after `tiingo_backfill_eod`; writes `recommendation_outcome.barrier_label` |
| New alpha factors | `apps/api/src/domain/features/feature_engine.py` lines 160–449 | add `_zscore_20`, `_dist_52w_high`, `_mom_12_1`, `_parkinson_vol`, `_adx_14`, `_bb_pct` as additional `SignalOut` entries |
| New `mean_reversion` family | `engine.yaml` + `recommendation_engine.py` lines 73–86 | add to `family_weights`; e.g. `trend_momentum=0.25, mean_reversion=0.10, volatility_risk=0.20, exposure=0.10` |
| empyrical metrics | `apps/api/src/api/performance.py` (currently 88 lines) | extend `GET /performance` with `sharpe`, `sortino`, `calmar`, `psr`, `max_dd`, `max_dd_duration`, `profit_factor`, `expectancy` |
| Walk-forward harness | new: `apps/api/src/domain/backtest/walk_forward.py` + CLI runner | iterate engine.yaml configs against historic price_bar data; emit WFE per config |
| Position sizing | `recommendation_engine.py` `RecommendationResult` dataclass (lines 94–110) | add fields `suggested_size_pct`, `suggested_stop_price`, `suggested_stop_atr_mult` |
| ATR stop | `recommendation_engine.py` thesis composer | use already-computed `ATR(14)` from feature_engine |
| Outcome migration | new: `infra/alembic/versions/003_outcome_labels.py` | add `barrier_label INT NULL`, `barrier_first_touch_at TIMESTAMPTZ NULL`, `suggested_size_pct NUMERIC(6,4) NULL`, `suggested_stop_price NUMERIC(20,6) NULL` |

### Concrete Implementation Suggestions (priority order)

1. **Migration 003** — schema first. Add 4 nullable columns above. Backwards compatible. [~30 min]
2. **`apps/worker/src/jobs/score_outcomes.py`** — new daily job. For every `Recommendation` older than 30d with `realized_30d_return IS NULL`: load `price_bar` window `[generated_at, generated_at + 90d]`, compute triple-barrier label using EWMA(20) vol of log-returns as `sigma_t0`, write `barrier_label` + `realized_30d_return` + `realized_90d_return` + `barrier_first_touch_at`. Register in `apps/worker/src/jobs/registry.py` after `run_recommendations_for_all_accounts`. [~1 day]
3. **Add `pandas-ta`** to `apps/api/pyproject.toml`. Wrap each call so output converts to `Decimal` types at boundary. Replace `_sma`, `_rsi`, `_atr` bodies; tests in `test_confidence_and_rsi.py` should still pass byte-for-byte. [~half day]
4. **Add 6 new signals** to `feature_engine.py` as listed above. New family `mean_reversion` in `engine.yaml`; rebalance `family_weights` to sum to 1.0; gate behind `engine_version` bump so existing recs deduplicate cleanly via existing `snapshot_hash` mechanism. [~1 day]
5. **Add `empyrical-reloaded`**; extend `apps/api/src/api/performance.py` to compute Sharpe/Sortino/Calmar/PSR/MaxDD/MaxDD-Duration/profit-factor/expectancy from `barrier_label` + `realized_Xd_return`. New response shape additive — keep existing `wins/losses/win_rate` for backwards compat. [~half day]
6. **`apps/api/src/domain/backtest/walk_forward.py`** — pure-Python harness (~80 lines). CLI: `python -m apps.api.backtest.walk_forward --config engine.yaml --start 2020-01-01 --end 2025-12-31 --train-days 365 --test-days 63`. Emits per-window Sharpe + WFE. Don't wire into API yet — run manually before each `engine.yaml` change. [~2 days]
7. **Position sizing fields** in `RecommendationResult`. Compute `suggested_size_pct = clip(|composite_score| * confidence * 0.25, 0, 0.10)`; `suggested_stop_price = current_price * (1 - 2 * ATR / current_price)` for buys; symmetric for sells. Surface in `GET /recommendations` response. [~half day]
8. **Meta-labeling** — defer to Phase 2; needs ≥6 months of `barrier_label` data first.

---

## 4. Sources & Attribution

**Verified-from-code:**

- vectorbt `labels/nb.py`, `returns/nb.py`, `signals/factory.py`, `generic/splitters.py` — github.com/polakowo/vectorbt
- ML4T `24_alpha_factor_library`, `05_strategy_evaluation/05_kelly_rule.ipynb`, `08_ml4t_workflow` — github.com/stefan-jansen/machine-learning-for-trading
- vectorbt-backtesting-skills `rules/{stop-loss,position-sizing,walk_forward,indian-market-costs,pitfalls}.md` — github.com/marketcalls/vectorbt-backtesting-skills
- algo-trading-template `strategies/mag_seven.py` — github.com/cbrincoveanu/algo-trading-template
- pytrade.org curated index — github.com/PFund-Software-Ltd/pytrade.org

**Authoritative external:**

- hudsonthames.org — triple-barrier, meta-labeling, fractional differentiation
- DeepWiki mlfinlab `6.3-triple-barrier-method`
- Wikipedia — Purged Cross-Validation, Meta-Labeling
- AFML (Lopez de Prado) Ch.3, Ch.5, Ch.7, Ch.12 [referenced, not directly fetched]
- empyrical-reloaded — github.com/stefan-jansen/empyrical-reloaded

**[Inference] flags:**

- Mapping triple-barrier onto existing `RecommendationOutcome` table (your schema, not theirs)
- Recommended dependency vs. copy decisions (license/maintenance reasoning, not benchmarked)
- 6-month threshold for meta-labeling viability (rule of thumb, not measured)
- ¼ Kelly default (industry convention)

**Codebase recon** — verified directly from `apps/api/src/domain/features/feature_engine.py:160-449`,
`recommendation_engine.py:73-497`, `db/models.py:48-374`,
`infra/alembic/versions/002_recommendation_hardening.py:24-67`,
`apps/worker/src/jobs/registry.py:50-195`, `tests/integration/test_hardening_pg.py`,
`tests/unit/test_confidence_and_rsi.py`.

---

## 5. Methodology

**Providers used:** Codex + Gemini via `orchestrate.sh discover` (failed mid-run after 2/6
agents — fell back to direct Agent dispatch). 5 parallel research agents (general-purpose
subtype) covering: vectorbt internals, ML4T internals, vectorbt-skills + algo-template,
pytrade.org ecosystem, Lopez de Prado AFML primitives. 1 Explore agent for local codebase recon.

**Coverage gaps:**

- Did not verify ML4T notebook URLs end-to-end (some 404s on `02_factors_from_solution.ipynb` path — repo restructured); factor formulas verified against canonical sources.
- AFML book itself not fetched directly — formulas cross-referenced against mlfinlab + hudsonthames secondary sources.
- vectorbt-backtesting-skills and algo-trading-template are smaller / less-documented; coverage thinner.
- Did not benchmark `pandas-ta` vs hand-coded indicators — only verified API surface.

**Cross-references:** Sharpe/Sortino formulas matched between vectorbt `returns/nb.py` and
ML4T notebooks. Triple-barrier matched between mlfinlab source, hudsonthames blog, and
DeepWiki — consistent. Position-sizing formulas matched between ML4T Kelly notebook and
vectorbt-skills RSI-accumulation pattern.
