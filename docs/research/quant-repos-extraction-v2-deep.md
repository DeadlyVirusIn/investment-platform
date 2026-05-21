# Quant Repos → Investment-Platform: Deep Domain Coverage (Round 2)

> Continuation of `quant-repos-extraction.md`. Generated 2026-04-19 via
> `/octo:research` Option 3 (6 parallel domain agents). Covers gaps not addressed
> in Round 1: pairs trading, regime detection, transaction costs, alt data,
> portfolio optimization, intraday/microstructure.

## Verdict Matrix

| Domain | Verdict | Headline Idea | Effort |
|---|---|---|---|
| Pairs / cointegration | nice-to-have | Engle-Granger + Johansen scan, Kalman β, OU half-life | ~1-2 wk subsystem |
| Regime detection (deterministic) | worth-it | Trend + vol + drawdown labels as `macro_regime` family + composite damper | ~2-3 days |
| HMM regime detection | nice-to-have | Adds `hmmlearn` dep + non-determinism without obvious lift over rule-based | defer |
| Transaction costs | worth-it (mandatory) | `CostModel` dataclass, gross+net dual reporting, next-bar-open exec | ~1 day |
| Alt data: Form 4 insider | worth-it | Free, high signal/noise, no NLP | ~3 days |
| Alt data: 8-K event gate | worth-it | Force HOLD 2d after filing | ~1-2 days |
| Alt data: Tiingo News + LM lexicon | worth-it | Already paid, deterministic | ~3 days |
| Alt data: FinBERT / earnings transcripts | defer | Wait for lexicon baseline measured | phase 4 |
| Portfolio: HRP | worth-it (ship first) | Robust, no view inputs needed | ~3 days |
| Portfolio: Black-Litterman | worth-it (headline feature) | Consumes engine `composite_score` + `confidence` directly | ~1 wk |
| Portfolio: Min-CVaR / Riskfolio | nice-to-have | Tail-risk-aware sizing | defer |
| Intraday strategies | skip phase-1 | `realized_vol_5min` as single daily feature in phase-2 | defer |

---

## 1. Pairs Trading & Cointegration (ML4T Ch.9)

**Status:** nice-to-have. Adds short-side dependency the current engine lacks.

### Pipeline (3-tier funnel)
1. Drop highly correlated (>0.99) duplicates; ADF-drop already-stationary series
2. Cheap heuristics (vectorized, ~600× faster than coint suite):
   - SSD on normalized prices
   - Correlation pre-filter on returns
3. Top-K cointegration: EG + Johansen on candidates with low drift + high spread variance
   - Best practice: require **both** EG and Johansen significant

### Tests
- **Engle-Granger** (bivariate): `from statsmodels.tsa.stattools import coint`. Run both directions, take min p; p<0.05 → cointegrated
- **Johansen** (multi-asset): `coint_johansen(df, det_order=0, k_ar_diff=order)`. Trace stat λ_trace(r) = -T·Σ log(1-λ_i)

### Spread + entry/exit
- **Static OLS β**: `spread_t = y_t - β·x_t`. Constant β.
- **Kalman β** (preferred): `pykalman.KalmanFilter(n_dim_obs=1, n_dim_state=2, transition_covariance=δ/(1-δ)·I, δ=1e-3)` — adapts online
- **Z-score**: `z = (spread - rolling_mean) / rolling_std`, window = `min(2*half_life, max_lookback)`
- **Entry**: `|z| > 2`. **Exit**: `|z| < 0.5` or `|z| > 3.5` (stop)
- **Half-life via OU**: `half_life = -log(2) / φ` where φ from `Δspread_t = α + φ·spread_{t-1} + ε`. Reject if <1d (noise) or >252d (too slow)

### Risks specific to pairs
- Cointegration breakdown (mitigation: rolling re-test quarterly + hard `|z|>3.5` stop)
- Beta drift (Kalman addresses)
- Leg imbalance (borrow rate spikes, corp action on one leg)
- Multiple-testing bias (Bonferroni: `p < 0.05/n_tests`)
- Liquidity asymmetry (require min ADV on both legs)

### Mapping to existing system
**Option A (lighter):** new family `pair_meanrev` on existing recommendation table; stuff `(s1, s2, β, z, half_life)` into JSON payload. Reuses dedup, scheduling, alerts.

**Option B (cleaner):**
- New entity `AssetPair(id, s1_asset_id, s2_asset_id, formation_start, formation_end, hedge_ratio, half_life, eg_pvalue, johansen_trace0, johansen_trace1, is_active)` — formation artifacts, refreshed quarterly
- New entity `PairRecommendation(id, pair_id, ts, z_score, action [ENTRY_LONG_S1 / ENTRY_SHORT_S1 / EXIT / STOP], spread_value)` — generated each bar
- Pair-formation job runs quarterly; per-bar z-score scoring runs on existing recommendation cron

**Deps**: `statsmodels` (mandatory); `pykalman` (only if Kalman β).

**Skip if**: product won't surface short legs to users — without short leg, half the alpha disappears.

---

## 2. Regime Detection

**Status:** worth-it (deterministic version only). Skip HMM in v1.

### Regime types
- **Trend**: bull / bear / sideways (SMA200 slope + price-vs-SMA200)
- **Volatility**: low / high (rolling std vs long-run median)
- **Drawdown**: in-bear / out-of-bear (>20% drawdown)
- **VIX** (if available): >25 fear, <15 complacent

### Deterministic implementation (preferred — fits codebase ethos)
```python
# Vol regime
vol_regime = "high" if rolling_std_20 > rolling_std_252.median() else "low"

# Trend regime
sma200 = close.rolling(200).mean()
sma200_slope = sma200.iloc[-1] - sma200.iloc[-21]
trend_regime = "bull" if (close[-1] > sma200[-1]) and sma200_slope > 0 else \
               "bear" if (close[-1] < sma200[-1]) and sma200_slope < 0 else "sideways"

# Drawdown regime
peak = close.cummax()
dd = (close - peak) / peak
bear = dd.iloc[-1] <= -0.20
```

Pure Decimal math. Snapshot-hashable. Deterministic.

### HMM alternative (defer)
```python
from hmmlearn.hmm import GaussianHMM
returns = np.diff(np.log(close_prices)).reshape(-1, 1)
model = GaussianHMM(n_components=2, covariance_type="full", n_iter=1000)
model.fit(returns)
states = model.predict(returns)
bull_state = int(np.argmax(model.means_.flatten()))
```
Cons: arbitrary state labels, often degenerates to "calm vs crisis", non-stationarity, breaks determinism guarantee.

### Mapping to existing system
`engine.yaml` already declares `macro_regime` family (weight 0.15) with FRED-series signals. Two integration patterns:

**(a) New signals inside existing `macro_regime` family** (recommended)
- Add `trend_regime` and `vol_regime` signals under `macro_regime:`
- Implement `compute_macro_regime()` in `feature_engine.py`
- Composite picks it up automatically

**(b) Regime modifier wrapper** (post-composite damping)
```python
regime_label = detect_regime(series)
if regime_label == "bear" and composite > 0:
    composite *= Decimal("0.5")  # damp BUYs in bear
    tags.append("regime-damped")
if regime_label == "high_vol":
    confidence *= Decimal("0.7")
```
- Add `regime_label: str | None = None` to `RecommendationResult`
- Surface in `thesis` and `rationale`
- Include in `snapshot_inputs` so hash flips with regime

**Combine (a) + (b).** Skip regime-keyed config (`family_weights_by_regime`) for v1.

---

## 3. Transaction Cost Modeling

**Status:** worth-it. **Mandatory** for the walk-forward harness from Round 1.

### Models — verdict per

| Model | Verdict |
|---|---|
| % notional fee (bps) | worth-it (primary) |
| Constant-bps slippage | worth-it (default) |
| Next-bar-open execution | mandatory (lookahead guard) |
| Square-root market impact | nice-to-have (only if AUM grows) |
| Bid-ask spread/2 | skip (no quote data) |
| Borrow cost | skip v1 (no shorts), stub field |
| Maker/taker split | skip (assume taker) |
| Indian multi-tier | skip (port if/when adding IN) |
| ML-learned slippage | skip (opaque, brittle) |
| Dividend cash injection | worth-it (already have data) |
| Gross-vs-net dual reporting | mandatory (the deliverable) |

### Defaults (from QuantStart / LuxAlgo / vectorbt conventions)

| Asset class | Fee bps | Slippage bps |
|---|---|---|
| US equity | 2.0 | 5.0 |
| US ETF | 1.0 | 3.0 |
| Crypto | 25.0 | 15.0 |
| Futures | 1.0 | 2.0 |

### Code skeleton — `apps/api/src/domain/backtest/costs.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssetClass(str, Enum):
    US_EQUITY = "us_equity"
    US_ETF = "us_etf"
    CRYPTO = "crypto"
    FUTURES = "futures"


DEFAULT_FEES_BPS = {
    AssetClass.US_EQUITY: 2.0,
    AssetClass.US_ETF:    1.0,
    AssetClass.CRYPTO:   25.0,
    AssetClass.FUTURES:   1.0,
}
DEFAULT_SLIP_BPS = {
    AssetClass.US_EQUITY: 5.0,
    AssetClass.US_ETF:    3.0,
    AssetClass.CRYPTO:   15.0,
    AssetClass.FUTURES:   2.0,
}


@dataclass(frozen=True)
class CostModel:
    """One-side cost model. Round-trip = 2 * (fee + slip)."""
    fee_bps: float = 5.0
    slip_bps: float = 5.0
    fixed_fee_ccy: float = 0.0
    borrow_bps_annual: float = 0.0
    exec_lag_bars: int = 1
    sqrt_impact_alpha: Optional[float] = None
    adv_lookup: Optional[dict] = field(default=None, repr=False)

    @classmethod
    def for_asset_class(cls, ac: AssetClass) -> "CostModel":
        return cls(fee_bps=DEFAULT_FEES_BPS[ac], slip_bps=DEFAULT_SLIP_BPS[ac])

    def one_side_cost_bps(self, notional, order_size_shares=0.0,
                          adv_shares=0.0, daily_vol=0.0):
        bps = self.fee_bps + self.slip_bps
        if self.sqrt_impact_alpha and adv_shares > 0:
            participation = order_size_shares / adv_shares
            bps += self.sqrt_impact_alpha * (daily_vol * 1e4) * (participation ** 0.5)
        return bps

    def apply(self, notional, **kw):
        bps = self.one_side_cost_bps(notional, **kw)
        return notional * bps / 1e4 + self.fixed_fee_ccy

    def daily_borrow(self, short_value):
        return short_value * self.borrow_bps_annual / 1e4 / 252
```

### Mapping
- New file: `apps/api/src/domain/backtest/costs.py`
- Walk-forward harness consumes `CostModel`, fills at `open[t+exec_lag_bars]`, emits both `gross_*` and `net_*` Sharpe + `cost_drag_bps`
- `engine.yaml`: add `costs:` block per asset class
- Live `/recommendations` response: inject `expected_execution_cost_bps` per rec so user sees breakeven hurdle
- May need to add `asset_class` enum column to `Asset` model (verify schema)

### Cost-drag rule of thumb
Live drawdown typically 1.5-2× backtested. If gross_sharpe collapses below 0.5 after costs → strategy doesn't survive.

---

## 4. Alt Data + Sentiment

**Status:** worth-it, phased. Form 4 first, then news, defer transformers.

### Source verdicts

| Source | Cost | Verdict |
|---|---|---|
| SEC EDGAR (10-K, 10-Q, 8-K) | Free | worth-it |
| Form 4 insider txns | Free | **worth-it FIRST** |
| Tiingo News | Already paid | worth-it |
| FINRA short interest | Free, bi-weekly | nice-to-have |
| FinBERT/transformers | Free model + GPU | defer |
| Earnings call transcripts | Paid | defer |
| Twitter/Reddit/WSB | API decaying | skip-for-now |
| Google Trends | Free, noisy | skip-for-now |
| Satellite / cc data | Institutional | skip |
| Analyst estimates | Paid | skip-for-now |

### Sentiment scoring — pick one
- **Loughran-McDonald financial dict** — best ROI for filings + news. Free CSV (~4k terms tagged Pos/Neg/Litigious/Uncertainty). Pure Python, no GPU.
- **VADER** — better for social/headlines, worse for filings
- **FinBERT** — defer to phase 3
- **LLM-as-classifier** — useful for 8-K event-type tagging

### Concrete signals → SignalOut additions

| factor_key | Source | Logic | Direction |
|---|---|---|---|
| `insider_net_buy_90d` | Form 4 | (buys-sells)/shares_out, z-scored | bullish if >0 |
| `insider_cluster_buy` | Form 4 | ≥3 distinct insiders buying in 30d | strong bullish flag |
| `news_sentiment_7d` | Tiingo + LM | EMA of (pos-neg)/(pos+neg) | momentum |
| `news_volume_zscore` | Tiingo | Article count vs 90d mean | attention spike → suppress recs |
| `event_8k_recent` | EDGAR | Boolean: 8-K in last 2 trading days | **gate: force HOLD + tag** |
| `earnings_surprise_pct` | (later) | (actual-consensus)/abs(consensus) | bullish if >0 |
| `short_interest_change_30d` | FINRA | Δ short_interest_ratio | contrarian |

### Schema additions

New table `asset_event` (alembic `infra/alembic/versions/003_asset_events.py`):
```
id PK | asset_id FK | ts | event_type ENUM(news|filing_8k|filing_10q|filing_10k|insider_buy|insider_sell|earnings|short_interest)
| source TEXT | sentiment_score NUMERIC(6,4) NULL | magnitude NUMERIC | raw_text_url TEXT | payload JSONB | ingested_at
```
Indexes: `(asset_id, ts DESC)`, `(event_type, ts DESC)`. Add to `apps/api/src/db/models.py`.

### Engine config additions

```yaml
sentiment:
  weight: 0.05  # start small, raise after backtest
  signals:
    insider_net_buy_90d: { weight: 0.45 }
    news_sentiment_7d:   { weight: 0.30 }
    short_interest_change_30d: { weight: 0.25 }
event_gates:
  filing_8k_window_days: 2
  earnings_blackout_days: 1
```

### Worker jobs (apps/worker/src/jobs/)
- **Phase 1**: `sec_edgar_form4_ingest.py` (daily 02:00 UTC), `sec_edgar_8k_ingest.py` (hourly during US market)
- **Phase 2**: `tiingo_news_ingest.py` (every 30 min, watchlist tickers, LM-dict score in-process)
- **Phase 3**: `finra_short_interest_ingest.py` (bi-weekly cron)
- **Phase 4 (defer)**: FinBERT, earnings transcripts

### Tiingo News specifics
- `GET https://api.tiingo.com/tiingo/news?tickers=AAPL`
- Fields: `id`, `title`, `description`, `publishedDate`, `crawlDate`, `source`, `url`, `tags[]`, `tickers[]` (multi-ticker → dedupe by `id`)
- Coverage: ~50 sources, US equities + major crypto. No Bloomberg/Reuters/FT
- Rate: free 50 req/hr; Power $30/mo 1000/hr (required for backfill)
- Pagination: `startDate`, `endDate`, `limit` (max 1000), `offset`

### Strict separation
Ingest jobs write events. Engine reads from `asset_event` at scoring time. NO external API calls during scoring → preserves determinism + snapshot reproducibility.

---

## 5. Portfolio Optimization

**Status:** worth-it. **Biggest architectural leap**: per-asset recs → portfolio recs.

### Library survey

| Library | License | Verdict |
|---|---|---|
| PyPortfolioOpt | MIT | **worth-it** primary |
| Riskfolio-Lib | BSD-3 | nice-to-have for tail-risk |
| skfolio | BSD-3 | skip (overlap, less mature) |

### Techniques

**1. Mean-Variance (Markowitz)** — `w* = (1/λ) Σ⁻¹ μ`. Σ⁻¹ amplifies estimation noise. **Skip as primary**, expose as comparison baseline.

**2. Hierarchical Risk Parity (HRP)** — Lopez de Prado 2016. No matrix inversion → robust.
- Distance: `d_ij = √(½(1−ρ_ij))`
- Hierarchical clustering (single linkage)
- Quasi-diagonalize Σ by cluster order
- Recursive bisection: split cluster, assign inverse-variance weights
- API: `pypfopt.HRPOpt(returns).optimize()`
- **WORTH-IT, ship first.** Zero view inputs needed, deterministic.

**3. Risk Parity (ERC)** — `w_i · (Σw)_i = w_j · (Σw)_j` ∀ i,j. HRP approximates this with no solver. **Nice-to-have.**

**4. Black-Litterman** — *the natural fit*.
- Prior: `π = δ Σ w_mkt` (market-implied returns from cap weights)
- Posterior: `μ_BL = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ [(τΣ)⁻¹π + P'Ω⁻¹Q]`
- **Mapping to your engine**:
  - `Q[i] = composite_score[i] × scaling`
  - `P` = identity rows for assets with active recs
  - `Ω = diag(1/confidence_i²)` — directly consumes confidence field
  - `τ ≈ 0.05`
- API: `pypfopt.BlackLittermanModel(cov, pi, P, Q, omega).bl_returns()` → feed to MV
- **WORTH-IT, ship second.** Headline feature — only optimizer that meaningfully uses your existing engine.

**5. Min-CVaR / Min-EVaR** — `min CVaR_α(w'r)`. Riskfolio: `port.optimization(model='Classic', rm='CVaR', obj='MinRisk')`. **Nice-to-have.**

**6. Discrete Allocation** — `pypfopt.DiscreteAllocation(weights, latest_prices, total_portfolio_value).lp_portfolio()`. Integer LP for share counts. **WORTH-IT, mandatory** (retail can't buy 0.347 shares).

### Constraints to add
- Per-asset cap (already 15% in exposure family — reuse)
- Sector caps via `sector_mapper`
- Turnover penalty: `||w_new − w_old||₁ ≤ τ` (prevents churn)
- Tax-aware (phase-2): penalize selling lots with `holding_days > 365` differently — `Lot` model already tracks `acquired_at`

### Mapping

| Component | Path |
|---|---|
| New module | `apps/api/src/domain/portfolio/optimizer.py` |
| Strategy classes | `HRPStrategy`, `BlackLittermanStrategy`, `MeanVarianceStrategy` (baseline) |
| New endpoint | `POST /portfolio/optimize` in `apps/api/src/api/portfolio.py` |
| Request | `{account_id, strategy: "hrp"\|"bl", constraints: {...}, total_value?}` |
| Response | `{target_weights, discrete_shares, expected_return, expected_vol, trades: [{symbol, delta_shares, side}]}` |
| New table | `optimization_runs` (snapshot inputs + outputs for reproducibility) |
| Migration | `infra/alembic/versions/003_portfolio_optimizer.py` |
| Tests | `tests/unit/test_optimizer.py`, `tests/integration/test_optimize_endpoint_pg.py` |

### Shipping order
1. **HRP** — standalone, no rec-engine coupling, proves the pipeline
2. **Black-Litterman** — wires `composite_score` + `confidence` into `Q` and `Ω`
3. **Turnover constraint** — once optimization runs persisted, compare to last run
4. **Min-CVaR + sector caps** — on demand

### Caveats
- System stops being "12 BUY signals, you decide" → "12 trades to execute". UX/disclaimer implications
- Σ estimation needs ≥1y daily returns per asset; cold-start fallback for new assets
- Both libs are pure-Python (numpy/scipy/cvxpy) — cvxpy adds ~80MB to image
- Wrap optimizer calls in `run_in_threadpool` to keep FastAPI event loop clean

---

## 6. Intraday / Microstructure

**Status:** SKIP for phase-1/ledger.

### Bar types beyond time-bars
- Tick bars (every N trades)
- Volume bars (every V shares)
- **Dollar bars** (every $D notional) — most stationary, AFML default
- Imbalance bars (TIB/VIB/DIB) — adaptive

### Microstructure features (minute-or-finer only)
- VWAP deviation, order flow imbalance (needs L1 quotes), realized vol from minute returns, opening range breakout, first/last hour returns

### Daily features derivable from minute data
- **Realized variance** (Σ 5-min returns²) — superior vol estimator
- Realized skew/kurt
- Jump detection (BNS test)
- Intraday vs overnight return split

### Data infrastructure cost
- SP500 = 390 bars/day × 500 names ≈ **390× storage blowup**
- Tiingo IEX free: ~30 days history (insufficient for ML)
- Polygon.io: better history, ~$200/mo

### Verdict
- **SKIP** phase-1
- **Phase-2 best ROI**: add `realized_volatility_5min` as a single daily feature — captures most intraday signal at ~5% of cost
- **Phase-3**: full intraday strategy layer

`PriceBar.timeframe` enum already supports `1min`/`5min` — no schema change required when ready.

---

## Updated Implementation Priority (combining R1 + R2)

| Order | Item | Round | Effort |
|---|---|---|---|
| 1 | Migration 003 (outcome labels: `barrier_label`, `barrier_first_touch_at`, `suggested_size_pct`, `suggested_stop_price`) | R1 | ~30 min |
| 2 | `score_outcomes.py` job (triple-barrier scorer) | R1 | ~1 day |
| 3 | `CostModel` dataclass | R2 | ~1 day |
| 4 | Walk-forward harness consuming `CostModel` (gross+net) | R1+R2 | ~2 days |
| 5 | Add `pandas-ta` + replace SMA/RSI/ATR | R1 | ~half day |
| 6 | Add `empyrical-reloaded` + extend `/performance` | R1 | ~half day |
| 7 | New alpha factors (mom_12_1, zscore_20, dist_52w_high, parkinson_vol, adx_14, bb_pct) | R1 | ~1 day |
| 8 | Position sizing fields in `RecommendationResult` (¼ Kelly · composite · confidence) | R1 | ~half day |
| 9 | Deterministic regime detection in `macro_regime` family + composite damper | R2 | ~2 days |
| 10 | Form 4 insider ingest + `insider_net_buy_90d` signal | R2 | ~3 days |
| 11 | 8-K event gate | R2 | ~1-2 days |
| 12 | Tiingo News + LM lexicon + `news_sentiment_7d` signal | R2 | ~3 days |
| 13 | HRP portfolio optimizer (`POST /portfolio/optimize?strategy=hrp`) | R2 | ~3 days |
| 14 | **Black-Litterman optimizer consuming engine views** | R2 | ~1 wk |
| 15 | Turnover constraint on optimizer | R2 | ~1 day |
| 16 | Meta-labeling overlay (defer until ≥6mo of `barrier_label` data) | R1 | phase 2+ |
| 17 | FINRA short interest ingest | R2 | ~2 days |
| 18 | Pairs trading subsystem (only if shorts supported) | R2 | ~1-2 wk |
| 19 | Realized vol from 5-min bars (single daily feature) | R2 | phase 2 |
| 20 | Full intraday strategy layer | R2 | phase 3 |
| 21 | HMM regime detection | R2 | defer |
| 22 | FinBERT / earnings transcripts | R2 | defer |
| 23 | Min-CVaR optimizer | R2 | defer |
| 24 | CPCV cross-validation | R1 | defer (only if ML added) |

---

## Key Architectural Insight

Black-Litterman is the **single most leveraged integration** in this analysis. Your existing `recommendation_engine.py` produces exactly what BL needs as inputs (`composite_score` → views, `confidence` → view confidence). Shipping HRP + BL transforms the product from a recommendation feed into a portfolio construction service without touching the existing engine — the engine becomes the "view generator" component of a larger BL pipeline.

Everything else in this report is signal-quality improvement. BL is a product capability leap.

---

## Sources (Round 2)

- ML4T Ch.9 `09_time_series_models/{05_cointegration_tests, 06_pairs_trading_with_kalman_filter, 07_pairs_trading_strategy}.ipynb`
- ML4T Ch.13 `13_unsupervised_learning/` — HMM, regime detection
- ML4T Ch.5 `05_strategy_evaluation/04_mean_variance_optimization.ipynb`
- ML4T Ch.3 `03_alternative_data/`, Ch.14 `14_working_with_text_data/03_document_term_matrix.ipynb`, `04_news_text_classification.ipynb`
- ML4T Ch.16 `16_word_embeddings_for_earnings_calls/02_earnings_calls/`
- ML4T Ch.2 `02_market_and_fundamental_data/02_algoseek_intraday/`
- ML4T Ch.12 `12_gradient_boosting_machines/` — intraday LightGBM
- vectorbt-backtesting-skills `rules/indian-market-costs.md`
- statsmodels `coint`, `coint_johansen`, `MarkovRegression` docs
- hmmlearn — github.com/hmmlearn/hmmlearn
- PyPortfolioOpt — github.com/robertmartin8/PyPortfolioOpt
- Riskfolio-Lib — github.com/dcajasn/Riskfolio-Lib
- QuantStart — Backtesting Pt II (slippage/transaction costs)
- LuxAlgo — Backtesting Limitations: Slippage & Liquidity
- Almgren & Chriss — Optimal Execution of Portfolio Transactions (PDF)
- Almgren, Thum, Hauptmann — Direct Estimation of Equity Market Impact (PDF)
- Tiingo News API docs — tiingo.com/documentation/news
- Loughran-McDonald master dict — sraf.nd.edu/loughranmcdonald-master-dictionary/
- Lopez de Prado — Building Diversified Portfolios that Outperform Out-of-Sample (HRP, 2016)

**[Inference] flags:**
- BL `Q` scaling factor not specified — empirical tuning required
- Form 4 watchlist filter assumes you can pre-filter EDGAR Form 4 firehose by ticker (verify EDGAR feed structure)
- `asset_class` column may need adding to `Asset` model (not verified)
- "Live drawdown 1.5-2× backtested" — common rule of thumb, single-source citation
- ¼ Kelly default (industry convention)
- Pairs trading "skip if no shorts" — inferred from current Buy/Hold/Sell semantics
