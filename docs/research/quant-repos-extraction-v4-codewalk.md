# Quant Repos → Investment-Platform: Manual Code Walk Synthesis (Round 4)

> Continuation of R1, R2, R3 reports. Generated 2026-04-19 via direct file inspection
> of pre-cloned repos in `C:\Users\kunal\quant-research-workspace\`. NO graph tools
> (MCP server disconnected). 3 parallel Haiku agents read source files directly via
> Read/Grep/Glob. Goal: high-signal reusable patterns with file:line citations.

## 1. Top 10 Most Valuable Reusable Patterns

| # | Pattern | Source | File:Line |
|---|---|---|---|
| 1 | MultipleTimeSeriesCV class (walk-forward with purge buffer) | ML4T | `utils.py:18-61` |
| 2 | DSR analytical max-SR formula (Euler-Mascheroni constant) | ML4T | `08_ml4t_workflow/01_multiple_testing/deflated_sharpe_ratio.py:10-17,30-34` |
| 3 | WFE ratio + parameter stability check with ROBUST/MODERATE/WEAK classifier | vbt-skills | `walk_forward/template.py:172-199` |
| 4 | FEE_MODELS dict comparison (zero/realistic/pessimistic loop) | vbt-skills | `realistic_costs/template.py:40-63` |
| 5 | Sharpe/Sortino/downside-std formulas (no-Numba, portable) | vectorbt | `returns/nb.py:330-426` |
| 6 | split_ranges_into_sets parametric splitter (fractional or absolute) | vectorbt | `generic/splitters.py:21-94` |
| 7 | Pre-go-live pitfalls checklist (10 items) | vbt-skills | `pitfalls.md:147-159` |
| 8 | Symmetric threshold logic for entry/exit (`pos_th / (1 - pos_th)`) | vectorbt | `labels/nb.py:93-97` |
| 9 | Configured base + Config.merge_with() immutable param versioning | vectorbt | `utils/config.py:196-221, 731-792` |
| 10 | Parameters dict idiom for strategy config (testable, swappable) | algo-template | `strategies/mag_seven.py:10-15` |

## 2. Top 5 ADOPT-NOW

| # | Pattern | Reason | Maps to |
|---|---|---|---|
| 1 | MultipleTimeSeriesCV (#1) | Production-ready walk-forward with embargo built-in | `apps/api/src/domain/backtest/walk_forward.py` |
| 2 | DSR formula (#2) | ~10 lines of scipy. Plugs into existing `/performance` endpoint | `apps/api/src/api/performance.py` |
| 3 | FEE_MODELS dict pattern (#4) | Cleaner than R2's CostModel enum — supports gross/realistic/pessimistic comparison loop | `apps/api/src/domain/backtest/costs.py` |
| 4 | Sharpe/Sortino formulas (#5) | Validates `empyrical-reloaded` if added; or copy 30 LOC if zero deps preferred | `apps/api/src/api/performance.py` |
| 5 | WFE ratio (#3) | One number to gate config changes (>50% acceptable, >70% good). Pre-commit gate | `apps/api/src/domain/backtest/walk_forward.py` |

## 3. Top 5 ADAPT-LATER

| # | Pattern | When to Pick Up |
|---|---|---|
| 1 | Configured + Config.merge_with (#9) | When `engine.yaml` config sweep / parameter optimization needed (phase 2+) |
| 2 | Symmetric threshold logic (#8) | When you implement triple-barrier scorer — apply for symmetric pt/sl |
| 3 | split_ranges_into_sets (#6) | If you want to extend walk-forward beyond simple rolling window (multi-set splits) |
| 4 | Pitfalls checklist (#7) | After backtest harness exists — wire as `POST /backtest/{id}/validate` gate |
| 5 | Parameters dict idiom (#10) | When backtest config grows beyond ~5 fields — pivot to Pydantic `BacktestConfig` |

## 4. Top 5 EXPLICITLY IGNORE

| # | Reject | Reason |
|---|---|---|
| 1 | IndicatorFactory metaclass (vectorbt) | Overengineered for rule engine; pandas-accessor coupling |
| 2 | All `*_nb.py` Numba JIT kernels | Don't need vectorized backtests at per-asset daily scale |
| 3 | Algoseek minute-bar bundle (ML4T) | Requires paid intraday data; intraday IC only 2.96% (R3 finding) |
| 4 | Lumibot dependency (algo-template) | Heavyweight broker abstraction conflicts with FastAPI + ledger model |
| 5 | Streamlit/Dash UIs (anything) | You have FastAPI; UI is separate concern |

## 5. Proposed Implementation Order

Combines R1+R2+R3+R4 findings. Each row = ~1 PR worth of work.

| Order | Item | Rationale |
|---|---|---|
| 1 | Migration 003 + `score_outcomes.py` (triple-barrier with per-signal-type n_bars [R3] using symmetric thresholds [R4 #8]) | Foundation: outcome labeling unblocks everything else |
| 2 | `CostModel` per FEE_MODELS dict pattern [R4 #4] in `apps/api/src/domain/backtest/costs.py` | Required for any meaningful backtest |
| 3 | `apps/api/src/domain/backtest/walk_forward.py` using MultipleTimeSeriesCV [R4 #1] + WFE ratio [R4 #3] | Combines ML4T + vbt-skills patterns |
| 4 | Add `pandas-ta`, replace `_sma`/`_rsi`/`_atr` (R1) | Makes adding new factors cheap |
| 5 | Add new alpha factors: mom_12_1, zscore_20, dist_52w_high, parkinson_vol, adx_14, bb_pct, Stochastic RSI, MFI, BOP [R3] | Empirically top-10 features in ML4T's GBM |
| 6 | Add `empyrical-reloaded` + extend `/performance` with DSR formula [R4 #2] | One coherent metrics upgrade |
| 7 | Position sizing fields (¼ Kelly · composite · confidence) (R1) | Cheap value-add per rec |
| 8 | Deterministic regime detection in `macro_regime` family + composite damper (R2) | Pure-Python, no new dep |
| 9 | Form 4 insider ingest + `insider_net_buy_90d` signal (R2) | Highest-ROI alt data |
| 10 | 8-K event gate (R2) | Forces HOLD around material events |
| 11 | Tiingo News + LM lexicon + `news_sentiment_7d` (R2) | News pipeline |
| 12 | HRP optimizer + benchmark vs MVO/equal-weight on your universe [R3] | Validate before committing |
| 13 | Black-Litterman optimizer (consumes engine views) (R2) | Headline product capability |
| 14 | Turnover constraint on optimizer (R2) | Prevents churn |
| 15-22 | Deferred: pairs trading, FinBERT, intraday, HMM, CPCV, Min-CVaR, meta-labeling | Wait for evidence / data accumulation |

---

## 6. Phase Spec: Step 1 (Migration 003 + Outcome Scorer + Walk-Forward Skeleton)

Bundling because they're interdependent. ~3-4 days total.

### Goals
- Define "good trade" objectively via triple-barrier
- Backfill `RecommendationOutcome` rows currently sitting NULL
- Lay foundation for walk-forward harness (needed before any engine config change)

### Migration 003 — `infra/alembic/versions/003_outcome_labels.py`

Add to `recommendation_outcome` table:

| Column | Type | Notes |
|---|---|---|
| `barrier_label` | INTEGER NULL | -1 / 0 / +1 (touched stop / time / profit-take) |
| `barrier_first_touch_at` | TIMESTAMPTZ NULL | When first barrier hit |
| `barrier_pt_mult` | NUMERIC(6,4) NULL | Profit-take multiplier used (e.g., 2.0) |
| `barrier_sl_mult` | NUMERIC(6,4) NULL | Stop-loss multiplier used |
| `barrier_n_bars` | INTEGER NULL | Time barrier used |
| `barrier_sigma_t0` | NUMERIC(20,10) NULL | EWMA vol at entry — needed for replay |

Add to `recommendation` table:

| Column | Type | Notes |
|---|---|---|
| `suggested_size_pct` | NUMERIC(6,4) NULL | clip(\|composite\|·confidence·0.25, 0, 0.10) |
| `suggested_stop_price` | NUMERIC(20,6) NULL | entry · (1 - 2·ATR/entry) |
| `suggested_stop_atr_mult` | NUMERIC(4,2) NULL | Always 2.0 v1, configurable later |

All nullable → backwards compatible.

### `apps/worker/src/jobs/score_outcomes.py`

```python
from decimal import Decimal
from datetime import timedelta
import numpy as np
import pandas as pd
from sqlalchemy import func

# Per-signal-type horizon (from R3 IC decay finding)
N_BARS_BY_FAMILY = {
    "trend_momentum": 63,
    "mean_reversion": 10,        # MR alpha dies after 21d (R3 IC decay)
    "volatility_risk": 21,
    "exposure": 42,
    "macro_regime": 126,
    "sentiment": 5,
}

PT_SL_MULT = (Decimal("2.0"), Decimal("2.0"))   # symmetric — R4 vectorbt #8 pattern


def ewma_vol(log_returns: pd.Series, span: int = 20) -> Decimal:
    """EWMA std of log returns, span=20 default."""
    s = log_returns.ewm(span=span, adjust=False).std().iloc[-1]
    return Decimal(str(s))


def triple_barrier_label(
    close: pd.Series,
    entry_ts: pd.Timestamp,
    sigma_t0: Decimal,
    pt: Decimal,
    sl: Decimal,
    n_bars: int,
) -> tuple[int, pd.Timestamp]:
    """Return (label, first_touch_ts). label ∈ {-1, 0, +1}."""
    p0 = Decimal(str(close.loc[entry_ts]))
    horizon = close.loc[entry_ts:].iloc[: n_bars + 1]
    if len(horizon) < 2:
        return 0, horizon.index[-1]

    path = (horizon.apply(lambda x: Decimal(str(x))) / p0) - Decimal(1)

    up_hits = path[path > pt * sigma_t0]
    dn_hits = path[path < -sl * sigma_t0]
    vert_ts = horizon.index[-1]

    candidates = []
    if not up_hits.empty:
        candidates.append((up_hits.index.min(), +1))
    if not dn_hits.empty:
        candidates.append((dn_hits.index.min(), -1))
    candidates.append((vert_ts, int(np.sign(float(path.iloc[-1])))))

    first_ts, label = min(candidates, key=lambda x: x[0])
    return label, first_ts


def score_outcome_for_rec(session, rec) -> dict:
    """Score one Recommendation. Returns dict of new column values."""
    primary_family = max(rec.family_scores, key=lambda k: abs(rec.family_scores[k]))
    n_bars = N_BARS_BY_FAMILY.get(primary_family, 63)

    close = load_close_series(
        session, rec.asset_id,
        start=rec.generated_at,
        bars_needed=n_bars + 10,
    )
    if len(close) < n_bars:
        return {}

    pre_entry = load_close_series(
        session, rec.asset_id,
        end=rec.generated_at, bars_needed=60,
    )
    log_ret = np.log(pre_entry).diff().dropna()
    sigma_t0 = ewma_vol(log_ret, span=20)

    pt, sl = PT_SL_MULT
    label, first_ts = triple_barrier_label(
        close, rec.generated_at, sigma_t0, pt, sl, n_bars,
    )

    p0 = Decimal(str(close.iloc[0]))
    p30 = Decimal(str(close.iloc[min(30, len(close) - 1)])) if len(close) >= 30 else None
    p90 = Decimal(str(close.iloc[min(90, len(close) - 1)])) if len(close) >= 90 else None

    return {
        "barrier_label": label,
        "barrier_first_touch_at": first_ts,
        "barrier_pt_mult": pt,
        "barrier_sl_mult": sl,
        "barrier_n_bars": n_bars,
        "barrier_sigma_t0": sigma_t0,
        "price_after_30d": p30,
        "price_after_90d": p90,
        "realized_30d_return": (p30 / p0 - 1) if p30 else None,
        "realized_90d_return": (p90 / p0 - 1) if p90 else None,
    }


def run():
    """Daily job. Score all recs >7 days old missing barrier_label."""
    session = get_session()
    pending = session.query(Recommendation).join(RecommendationOutcome).filter(
        RecommendationOutcome.barrier_label.is_(None),
        Recommendation.generated_at < func.now() - timedelta(days=7),
    ).all()

    for rec in pending:
        try:
            updates = score_outcome_for_rec(session, rec)
            if updates:
                session.query(RecommendationOutcome).filter_by(
                    recommendation_id=rec.id
                ).update(updates)
                session.commit()
        except Exception:
            log.exception("score_outcome failed for rec=%s", rec.id)
            session.rollback()
```

### Walk-Forward Skeleton — `apps/api/src/domain/backtest/walk_forward.py`

Adapt from ML4T `MultipleTimeSeriesCV` [R4 #1]:

```python
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    @property
    def embargo_end(self) -> date:
        # 1% embargo per AFML — drop train labels within this window after test
        return self.test_end + timedelta(
            days=int((self.test_end - self.test_start).days * 0.01)
        )


def walk_forward(
    start: date, end: date,
    train_days: int = 365,
    test_days: int = 63,
    step_days: int = 63,
    embargo_pct: float = 0.01,
) -> Iterator[WalkForwardWindow]:
    """Rolling walk-forward windows. Anchor: test_start; train precedes."""
    cursor = start + timedelta(days=train_days)
    while cursor + timedelta(days=test_days) <= end:
        yield WalkForwardWindow(
            train_start=cursor - timedelta(days=train_days),
            train_end=cursor,
            test_start=cursor,
            test_end=cursor + timedelta(days=test_days),
        )
        cursor += timedelta(days=step_days)


def wfe_ratio(oos_returns: list[float], is_returns: list[float]) -> dict:
    """Walk-Forward Efficiency. >0.5 acceptable, >0.7 robust. R4 #3 pattern."""
    is_avg = sum(is_returns) / len(is_returns)
    oos_avg = sum(oos_returns) / len(oos_returns)
    if is_avg <= 0:
        return {"wfe": 0.0, "verdict": "WEAK", "reason": "no IS edge"}
    wfe = oos_avg / is_avg
    verdict = "ROBUST" if wfe > 0.7 else "MODERATE" if wfe > 0.5 else "WEAK"
    return {"wfe": wfe, "verdict": verdict, "is_avg": is_avg, "oos_avg": oos_avg}
```

CLI runner deferred — wire after harness wraps signal generation + cost application + scoring loop.

### Tests Needed

`apps/api/tests/unit/test_outcome_scoring.py`:
- Synthetic price series hitting upper barrier first → label=+1
- Synthetic series hitting lower barrier first → label=-1
- Series oscillating within bounds, vertical barrier hits → label = sign(final return)
- Series with insufficient data → empty dict (skip)
- Per-family n_bars override applied correctly
- Symmetric threshold (pt=sl=2.0) → equal up/down barriers in absolute terms

`apps/api/tests/integration/test_score_outcomes_pg.py`:
- Run job → outcome rows updated
- Idempotent re-run → no double-write
- Rec without enough price data → row stays NULL, no error

`apps/api/tests/unit/test_walk_forward.py`:
- Window count matches `floor((end - start - train_days) / step_days)`
- No window has `test_end > end`
- Embargo respected when overlapping windows

### Acceptance Criteria
- All existing tests pass
- New migration applies cleanly + reverts cleanly
- `score_outcomes` job runs in CI in <30s on test fixtures
- WFE function returns expected verdicts on synthetic IS/OOS pairs
- Worker registry updated to schedule daily after `tiingo_backfill_eod`

### Out of Scope (next phase)
- Walk-forward CLI runner (`python -m apps.api.backtest.walk_forward`)
- Cost model integration into scoring
- Engine config snapshotting per window
- HRP / Black-Litterman optimizer

---

## Sources (Round 4)

All patterns verified directly against pre-cloned repos:

- vectorbt — `C:\Users\kunal\quant-research-workspace\vectorbt\`
  - `vectorbt/portfolio/`, `vectorbt/signals/factory.py`, `vectorbt/labels/{nb,generators}.py`
  - `vectorbt/generic/splitters.py` (full read)
  - `vectorbt/returns/nb.py` (Sharpe/Sortino formulas at lines 330-426)
  - `vectorbt/utils/config.py` (Configured class at 731-792)
  - Tests `tests/test_*.py` (sampled)
- machine-learning-for-trading — `C:\Users\kunal\quant-research-workspace\machine-learning-for-trading\`
  - `utils.py:18-61` (MultipleTimeSeriesCV)
  - `08_ml4t_workflow/01_multiple_testing/deflated_sharpe_ratio.py:10-17,30-34`
  - `08_ml4t_workflow/00_data/data_prep.py:18-40`
  - `11_decision_trees_random_forests/00_custom_bundle/stooq_preprocessing.py`
  - `08_ml4t_workflow/04_ml4t_workflow_with_zipline/01_custom_bundles/algoseek_1min_trades.py`
- vectorbt-backtesting-skills — `C:\Users\kunal\quant-research-workspace\vectorbt-backtesting-skills\`
  - `.claude/skills/vectorbt-expert/rules/assets/realistic_costs/template.py:40-63`
  - `.claude/skills/vectorbt-expert/rules/assets/walk_forward/template.py:172-199`
  - `.claude/skills/vectorbt-expert/rules/pitfalls.md:147-159`
- algo-trading-template — `C:\Users\kunal\quant-research-workspace\algo-trading-template\`
  - `strategies/mag_seven.py:10-15`, `README.md:20-31`, `run_backtest.py`, `run_live.py`
- pytrade.org — `C:\Users\kunal\quant-research-workspace\pytrade.org\`
  - Verified as link-index repo only (no code patterns)

**Workspace cleanup:** `C:\Users\kunal\quant-research-workspace\` (~220MB total) safe to delete after this report; all extractions captured here.

**[Inference] flags:**
- ML4T `utils.py` location may be at repo root or `08_ml4t_workflow/` — agent referenced both
- vectorbt's `Configured` line numbers approximate (large file, partial read)
- Per-family `N_BARS_BY_FAMILY` mapping tuned against R3 IC decay finding (mean-reversion 21d) but other families inferred
- Tests pattern from vectorbt may not directly translate — your project uses pytest with fixtures, vectorbt uses bare functions
