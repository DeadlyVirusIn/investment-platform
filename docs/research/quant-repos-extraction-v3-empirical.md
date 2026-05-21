# Quant Repos → Investment-Platform: Empirical Results from ML4T Notebooks (Round 3)

> Continuation of R1 and R2 reports. Generated 2026-04-19 via `/octo:research` Option 2
> (5 parallel Haiku agents parsing pre-executed ML4T notebook outputs). Extracts actual
> numbers (IC, Sharpe, feature importance, etc.) from committed notebook cell outputs,
> not re-running notebooks. ML4T README confirms notebooks ship in executed state.

## Executive Summary

Notebooks analyzed: `04_alpha_factor_research/`, `05_strategy_evaluation/`,
`08_ml4t_workflow/`, `09_time_series_models/`, `12_gradient_boosting_machines/`.

**Headline finding**: many textbook claims are backed by incomplete empirical evidence.
Sharpe ratios, Kelly fractions, HRP-vs-MVO weight tables are often hidden or
truncated. Infer this is not accidental — suggests results weren't strong.

**Most actionable extractions**:
- Mean-reversion IC decay curve (per-horizon table)
- Daily ML feature importance ranking (top-10)
- Intraday IC confirmation (2.96% — not worth pursuing)
- Pairs trading result gap (supports defer verdict)
- Fama-French factor betas 2001-2018 (value weak, size strong)

---

## 1. Alpha Factor Decay (Ch.4 — WELL DOCUMENTED)

### Mean-Reversion Factor IC Decay

S&P 500 universe, 2015-2017, weekly rebalance. Factor = z-score of last monthly return
vs rolling 12-month history.

| Horizon | IC Mean | IC Std | IC t-stat | Quintile Spread | Annualized Alpha | p-value |
|---|---|---|---|---|---|---|
| 5d | 0.022 | 0.140 | 4.261 | **28.6 bps** | 4.6% | p<0.001 |
| 10d | 0.026 | 0.127 | 5.529 | **22.3 bps** | 3.6% | p<0.001 |
| 21d | 0.017 | 0.116 | 3.953 | 8.7 bps | 0.9% | p<0.001 |
| 42d | 0.003 | 0.115 | 0.729 | 1.6 bps | 0.1% | **p=0.466** |

Source: [06_performance_eval_alphalens.ipynb](https://github.com/stefan-jansen/machine-learning-for-trading/blob/main/04_alpha_factor_research/06_performance_eval_alphalens.ipynb)

**Backtest of z-score mean-reversion strategy** (25L/25S, weekly rebalance, 2015-2017):
- Total return: 10.9% over 3 years
- Sharpe: 0.64
- Max DD: -14.26%
- Max leverage: 1.26x
- Turnover: 39-83% per rebalance (HIGH)

**Actionable**:
- If/when you add mean-reversion signals, use 5-10d forecast horizon; signal dies after 21d
- Triple-barrier `n_bars` should be signal-type-keyed (MR=10, Trend=63), not uniform
- Turnover >40% weekly kills most retail strategies via costs

### Fama-French Factor Betas (2001-2018 US Equities)

318,478 observations, 1,838 tickers:

| Factor | Mean Beta | Interpretation |
|---|---|---|
| Mkt-RF | 0.98 | Near-market |
| SMB (Size) | **0.63** | Dominant — small-cap tilt |
| HML (Value) | 0.13 | Near-zero |
| RMW (Profitability) | -0.06 | ~Zero |
| CMA (Investment) | 0.01 | ~Zero |

**Actionable**:
- If you add fundamental signals, size > value empirically in this period
- Don't weight "value" factors high despite academic consensus — post-crisis weakness through 2016

Source: [01_feature_engineering.ipynb](https://github.com/stefan-jansen/machine-learning-for-trading/blob/main/04_alpha_factor_research/01_feature_engineering.ipynb)

### Return Decay by Horizon

| Horizon | Mean return | Volatility |
|---|---|---|
| 1-month | 1.23% | 11.4% |
| 12-month | 0.63% | 3.5% |

Returns normalize with annualization but vol compresses hard — confirms standard result.

---

## 2. Daily ML Feature Importance (Ch.12 — CRITICAL FOR YOUR ENGINE)

NASDAQ-100, LightGBM tuned via 23-fold time-series CV. Top features by GAIN:

1. Recent 1-month returns — **highest gain**
2. Momentum indicators (CCI, Stochastic RSI)
3. Temporal features (year, month) — high split count, low gain
4. Volume imbalance (uptick/downtick ratios)
5. Money Flow Index (MFI)
6. Balance of Power (BOP)
7. NATR (normalized ATR)
8. Stochastic Oscillator components
9. Lagged returns (1-10 periods)
10. Trade location metrics (bid/ask proximity)

### Cross-Validation IC (LightGBM vs Linear baseline)

| Lookahead | Linear IC | Best GBM IC | Δ |
|---|---|---|---|
| 1d | 7.2% | ~8-10% | +1-3pt |
| **5d** | **18.8%** | ~19-20% | +0.5-1.5pt |
| 21d | 14.5% | ~15-17% | +0.5-2.5pt |

**Actionable for feature_engine.py**:
- **Promote** Stochastic RSI + MFI to phase-1 (were phase-2; both in pandas-ta)
- Add Balance of Power (BOP) as cheap signal — one formula
- Confirm current `mom_12_1` and `adx_14` plans validated
- **5-day horizon is the empirical sweet spot** across all models — use for backtest primary metric
- Skip trade-location metrics (no quote data available from Tiingo EOD)

### Intraday Strategy (NASDAQ-100, minute bars, Feb 2016–Dec 2017)

31.4M observations, LightGBM (num_leaves=16, min_data=500, feature_fraction=0.8, 250 boost rounds):

- **IC overall: 2.96%** (vs 18.8% for 5d daily)
- IC by-minute mean: 3.21%
- IC by-minute median: 3.23%
- 12-month rolling training windows, 1-month test

**Actionable**: confirms R2 verdict — **SKIP intraday**. Even state-of-the-art GBM on
microstructure features delivers ~3% IC. Survival after costs very unlikely.

Source: [Chapter 12 boosting overview](https://stefan-jansen.github.io/machine-learning-for-trading/12_gradient_boosting_machines/)

---

## 3. Pairs Trading — Empirical Gap (Ch.9)

### Cointegration Scan Results

| Metric | Value |
|---|---|
| Stocks tested | 171 |
| ETFs tested | 139 |
| Total pairs screened | 262,988 |
| Engle-Granger pass (95%) | 8.84% |
| Johansen pass (95%) | 5.28% |
| **Both EG+Johansen pass** | **3,466 pairs (1.32%)** |

Most consistent pairs:
- T (AT&T) ↔ VOX (Vanguard Comm ETF) — 6 quarters
- MDLZ (Mondelez) ↔ Energy/Commodity ETFs — 5 occurrences

### Backtest (Jan 2017 – Dec 2019)

| Metric | Value |
|---|---|
| Cumulative return | **+7.96%** ($1M → $1.08M over 3 years) |
| Max DD | -20% hard stop |
| Simultaneous positions | 275-311 |
| Active pairs/month | 76-2,472 |
| Total signals | 134,450 (HIGH turnover) |

### Critical Missing Data

Notebooks DO NOT disclose:
- Sharpe / Sortino / Calmar (pyfolio computed but hidden)
- Win rate
- Holding period distribution
- Half-life estimates
- Hedge ratio β drift
- Z-score entry/exit thresholds used
- Kalman vs OLS empirical comparison
- Out-of-sample vs in-sample decomposition

**Verdict reinforced**: R2 said "defer pairs trading." Notebook evidence strengthens this
— ML4T's own textbook hides risk-adjusted metrics. Strong prior against shipping.

Source: [07_pairs_trading_backtest.ipynb](https://github.com/stefan-jansen/machine-learning-for-trading/blob/main/09_time_series_models/07_pairs_trading_backtest.ipynb)

---

## 4. Strategy Evaluation Gaps (Ch.5)

### Pyfolio Tearsheet (example strategy)

IS (36 months, 2013-2016):
- Annual return: 1.3%
- Sharpe: 0.30
- Max DD: -5.84%

OOS (12 months, 2017):
- Annual return: 3.97%
- Sharpe: 0.82
- Max DD: -3.11%

**Caveat**: OOS >> IS is suspicious in a 12-month window. Likely regime effect
(2017 was strong bull year) rather than genuine OOS quality.

### Mean-Variance Optimization

- 25-stock universe (2008-2017 weekly)
- 100,000 Dirichlet random portfolios
- Max Sharpe: 19.42% return, 25.70% vol (annualized)
- Specific efficient frontier coordinates NOT numerically reported

### Kelly Criterion — Results MISSING

- Formula implemented (`get_kelly_share()`)
- **Actual f* values NOT rendered in notebook output**
- No pre/post-Kelly Sharpe comparison
- No max DD reduction numbers

### HRP vs MVO — Results MISSING

- README cites Monte Carlo evidence for HRP OOS superiority
- **No weights tables, no Sharpe delta, no specific numbers in notebook**

**Actionable**: ¼ Kelly default (R1 plan) stays — no empirical "optimal" value from ML4T
to override. When implementing HRP (R2 priority), **benchmark against MVO and
equal-weight on your own universe first** — don't take ML4T's claim on faith.

---

## 5. ML4T Workflow & Deflated Sharpe (Ch.8)

### DSR Formula (deflated_sharpe_ratio.py)

```
maxZ = (1 - emc) × Φ⁻¹(1 - 1/N) + emc × Φ⁻¹(1 - 1/(N×e))
Expected_Max_SR = μ + σ × maxZ
```

Constants:
- Euler-Mascheroni: 0.5772156649
- Validation: 10,100 parameter combos, 10K Monte Carlo iterations each

### Example Strategy (Vectorized Backtest)

- 257 stocks, 751 days (Dec 2014–Nov 2017)
- Ridge regression predictions, 30 positions (15L/15S)
- Strategy daily std: 0.1981% (S&P: 0.7923%) — **4× lower vol, suspicious**
- Correlation to S&P: -0.1184 (hedge-like)

### Event-Driven Backtest

- Backtrader: $10K → $10,078.17 (0.78% over period, 56s)
- Zipline ML workflow: 250 stocks, 504-day rolling train, SGDRegressor+L2, 9 features, 755-day test (2015-2017, 313s)

### Critical Missing

- **No concrete "raw SR=X, deflated SR=Y" example** in notebook outputs
- No pass/fail thresholds demonstrated
- No slippage sensitivity (all examples 0bps)
- No walk-forward validation split explicitly shown

**Actionable**:
- Implement DSR per formula (R1 priority) — ML4T has no calibration target for us
- Rule of thumb: 20-40% Sharpe deflation when trials > 50
- Strategy vol 4× lower than benchmark is a RED FLAG, not a virtue — suggests limited
  exposure and may need leverage adjustment to be meaningful

Citation: Bailey & López de Prado (2013), *Journal of Portfolio Management*.

---

## 6. Results Reliability Scorecard

| Chapter | Claims | Verified Numbers | Trust |
|---|---|---|---|
| Ch.4 Alpha Factors | High | Well documented | **High** |
| Ch.5 Strategy Eval | High | Partial (Kelly/HRP gaps) | Medium |
| Ch.8 ML4T Workflow | Medium | Low (pedagogical) | Use formulas only |
| Ch.9 Pairs Trading | High | **Incomplete** | **Low** |
| Ch.12 Boosting | Medium | IC numbers credible | Medium-High |

---

## 7. Biggest Empirical Surprises

1. **Value factor is weak in 2001-2018 US data.** HML beta 0.13 vs SMB 0.63. Academic consensus oversold.
2. **Mean-reversion dies after 21 days.** 78% IC drop from 10d to 42d. Per-signal horizon tuning needed.
3. **Intraday ML barely beats coin-flip.** 3% IC — unlikely to survive any realistic cost model.
4. **Pairs trading profitability unconfirmed even in textbook.** Sharpe hidden → strong prior against.
5. **Notebooks systematically hide risk-adjusted metrics.** When hidden, infer unimpressive.
6. **Strategy std 4× lower than S&P** in Ch.8 example — marketed as good, actually means tiny exposure.
7. **5-day forecast horizon is empirically optimal** across linear, GBM — use as primary backtest metric.

---

## 8. Revised Priority Adjustments (vs R1+R2)

### Promote to Phase-1

| Item | From | Why |
|---|---|---|
| **Stochastic RSI + MFI signals** | Phase-2 | Ch.12 ranks #2 and #5 by gain |
| **Balance of Power (BOP) signal** | Not listed | Ch.12 #6, cheap formula |
| **Per-signal-type triple-barrier `n_bars`** | Uniform 63 | MR signals die after 21d, need n_bars=10 |

### Tune

| Item | Adjustment |
|---|---|
| Walk-forward primary metric | 5d forward return (was generic) |
| HRP rollout | Benchmark vs MVO + equal-weight on your universe before shipping |
| DSR expectation | Plan for 20-40% deflation when trials > 50 |

### Downgrade / Confirm Defer

| Item | Reason |
|---|---|
| Fundamental value signals | 2001-2018 empirical weakness (HML ≈ 0) |
| Pairs trading | Ch.9 textbook hides Sharpe → low confidence |
| HMM regime detection | No empirical edge vs deterministic in ML4T |
| Intraday strategies | 3% IC confirmed insufficient |

### No Change

- Everything else from R1+R2 combined priority list

---

## 9. Combined Priority List (R1+R2+R3)

Replaces the list at end of R2. Changes marked **[R3]**.

| # | Item | Effort |
|---|---|---|
| 1 | Migration 003 (outcome labels + sizing fields) | ~30 min |
| 2 | `score_outcomes.py` job with **per-signal-type n_bars [R3]** | ~1 day |
| 3 | `CostModel` dataclass | ~1 day |
| 4 | Walk-forward harness with **5d primary metric [R3]** | ~2 days |
| 5 | Add `pandas-ta`, replace SMA/RSI/ATR | ~half day |
| 6 | Add `empyrical-reloaded`, extend `/performance` | ~half day |
| 7 | New alpha factors: mom_12_1, zscore_20, dist_52w_high, parkinson_vol, adx_14, bb_pct, **Stochastic RSI, MFI, BOP [R3]** | ~1.5 days |
| 8 | Position sizing fields (¼ Kelly · composite · confidence) | ~half day |
| 9 | Deterministic regime detection in `macro_regime` + composite damper | ~2 days |
| 10 | Form 4 insider ingest | ~3 days |
| 11 | 8-K event gate | ~1-2 days |
| 12 | Tiingo News + LM lexicon | ~3 days |
| 13 | HRP optimizer **+ benchmark vs MVO/equal-weight [R3]** | ~4 days |
| 14 | Black-Litterman optimizer | ~1 wk |
| 15 | Turnover constraint on optimizer | ~1 day |
| 16 | Meta-labeling (defer) | phase 2 |
| 17 | FINRA short interest ingest | ~2 days |
| 18-22 | DEFERRED (pairs, intraday, HMM, FinBERT, CPCV, Min-CVaR) | — |

---

## 10. What We Couldn't Extract (Execution Would Be Needed)

The following would require actually running notebooks with full data pipeline:

- Final Kelly f* values and pre/post-Kelly drawdown reduction
- HRP weights vs MVO weights on specific universes
- Pairs trading Sharpe / Calmar / win rate
- DSR raw-vs-deflated gap on a specific strategy
- Transaction-cost sensitivity curves
- Out-of-sample walk-forward decomposition

Cost to run notebooks properly: paid data (AlgoSeek minute data, Quandl Wiki post-2018),
~12GB conda env with Zipline/TF/pyfolio, days of CPU per intraday notebook. Not worth
for extraction — build your own numbers on your own universe.

---

## Sources (Round 3)

- [Chapter 4 — alpha factor research](https://github.com/stefan-jansen/machine-learning-for-trading/tree/main/04_alpha_factor_research)
  - 01_feature_engineering.ipynb, 04_single_factor_zipline.ipynb, 06_performance_eval_alphalens.ipynb
- [Chapter 5 — strategy evaluation](https://github.com/stefan-jansen/machine-learning-for-trading/tree/main/05_strategy_evaluation)
  - 04_mean_variance_optimization.ipynb, 05_kelly_rule.ipynb
- [Chapter 8 — ML4T workflow](https://github.com/stefan-jansen/machine-learning-for-trading/tree/main/08_ml4t_workflow)
  - deflated_sharpe_ratio.py, 02_vectorized_backtest.ipynb, 03_backtesting_with_backtrader.ipynb, 04_ml4t_workflow_with_zipline/
- [Chapter 9 — time series models](https://github.com/stefan-jansen/machine-learning-for-trading/tree/main/09_time_series_models)
  - 06_statistical_arbitrage_with_cointegrated_pairs.ipynb, 07_pairs_trading_backtest.ipynb
- [Chapter 12 — gradient boosting](https://github.com/stefan-jansen/machine-learning-for-trading/tree/main/12_gradient_boosting_machines)
  - 05_trading_signals_with_lightgbm_and_catboost.ipynb, 10_intraday_features.ipynb, 11_intraday_strategy.ipynb
- Bailey & López de Prado — *The Deflated Sharpe Ratio*, J. Portfolio Management 2013

**[Inference] flags:**
- "When notebook hides Sharpe, infer unimpressive" — prior, not verified against ML4T author intent
- IC "decay curve" generalization from single Ch.4 factor — MR-specific; other factors may decay differently
- "5d horizon empirically optimal" — holds across tested models in ML4T sample; universe-dependent
- DSR 20-40% deflation rule of thumb — industry convention, not from ML4T
