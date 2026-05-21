# V2 ML Advisory Layer — Design (Phase 10C.1)

**Date:** 2026-04-26
**Status:** DESIGN ONLY — implementation strictly prohibited until design
review passes AND a separate explicit operator approval is granted.
**Scope:** Pure research advisory layer. ML predictions are display-only
information. **`ML_CAN_AFFECT_TRADES = false` remains enforced
indefinitely.** ML output never reaches execution, governance gates,
state machine, approval workflow, or routing.

---

## TL;DR

A new **isolated** research subdirectory `apps/api/src/research/ml_advisory/`
that produces ML predictions over the same shadow-comparison data the
governance layer already consumes. Outputs are **display-only**: surfaced
on a clearly-labeled UI card and a read-only API endpoint, with the
fixed text **"ML advisory — not used in decisions"**. The module
imports exactly zero governance / execution code. The governance layer
imports exactly zero ML code. Bidirectional grep enforcement.

If at any point during implementation a developer needs ML output to
flow back into a gate, the state machine, or any execution surface, the
implementation MUST stop and re-enter design review. There is no soft
path.

---

## Hard constraints (mirrored from Phase 10C instructions)

| Constraint | Enforcement |
|---|---|
| `ML_CAN_AFFECT_TRADES = false` permanent | Settings flag remains; no code path reads it as a "promote ML" gate |
| No integration with `v2_promotion_gates` | Bidirectional grep — ML files do not import gates; gates do not import ML |
| No integration with `v2_promotion_state` | Same |
| No integration with `v2_promotion_snapshot` worker job | Same; snapshot job does NOT read ML outputs |
| No integration with approval endpoints | API module does not import or call ML inference |
| No integration with execution / routing / sizing | Strict |
| No implicit coupling via shared utilities | ML module duplicates any pure helpers it needs (e.g. ISO-week formatters); no shared mutable state |
| No reading ML outputs inside governance code | grep enforced; CI gate documented |
| Walk-forward only — no random shuffle | Sklearn's default cross-val is BANNED in this module |

Verified post-implementation by:
```bash
# 1. ML never imports governance / execution
git grep -E "v2_promotion_gates|v2_promotion_state|v2_promotion_snapshot|engine_b|shadow_strategy|paper_trade_log|decision_log|execute|order|sizing|routing" apps/api/src/research/ml_advisory/

# 2. Governance never imports ML
git grep -E "ml_advisory|ml_inference|ml_model|ml_predict" \
    apps/api/src/research/v2_promotion_gates.py \
    apps/api/src/research/v2_promotion_state.py \
    apps/api/src/research/b2_v2_comparison.py \
    apps/api/src/api/v2_promotion.py \
    apps/api/src/api/b2_v2_comparison.py \
    apps/worker/src/jobs/v2_promotion_snapshot.py

# 3. ML CAN AFFECT TRADES still false (settings.py)
git grep "ML_CAN_AFFECT_TRADES" apps/api/src/config/__init__.py

# 4. ML module uses no random shuffle / k-fold cross-val
git grep -E "KFold|train_test_split|StratifiedKFold|shuffle=True|random_split" \
    apps/api/src/research/ml_advisory/

# 5. ML feature builders never read execution tables
git grep -E "paper_trade|decision_log|position_snapshot|order_log" \
    apps/api/src/research/ml_advisory/features.py
```

All five greps must return **zero substantive matches**.

---

## 1. Module structure

```
apps/api/src/research/ml_advisory/
├── __init__.py                  # exports: predict_for_snapshot
├── features.py                  # feature engineering, pure functions
├── models.py                    # model classes (logistic / elastic net / RF / GBM)
├── inference.py                 # build_features → score model → output dict
├── evaluation.py                # walk-forward CV, calibration, metrics
├── targets.py                   # target-label construction (separate from features)
└── README.md                    # mirrors §1–§9 of this design

apps/api/tests/unit/test_ml_advisory_features.py
apps/api/tests/unit/test_ml_advisory_models.py
apps/api/tests/unit/test_ml_advisory_evaluation.py
apps/api/tests/unit/test_ml_advisory_isolation.py    # boundary enforcement
apps/api/tests/integration/test_ml_advisory_smoke.py # tiny end-to-end
```

**Strict file boundaries:**
- `features.py` is allowed to read raw market data + snapshot history. No write capability.
- `models.py` defines model classes. No I/O.
- `inference.py` orchestrates feature build → model load → score → JSON output. No DB writes.
- `evaluation.py` is **research-only**; never invoked by production paths.
- `targets.py` constructs labels from historical fwd_return data. No look-ahead.
- `__init__.py` deliberately exports a single function `predict_for_snapshot(snapshot_id)`. Nothing else.

---

## 2. Data inputs (read-only)

| Source | What's read | Why |
|---|---|---|
| `paper_shadow_log` | `as_of_date`, `signal`, `fwd_return_1d`, `fwd_return_5d`, `regime_label`, `trend_score` per `(date, instrument, source_strategy)` | Per-day market-state inputs and labels |
| `v2_promotion_snapshot` | `comparison_bundle_json.metrics.*`, `metrics_by_regime`, `tail_by_regime`, `verdict.*` | Snapshot-derived divergence + edge features |
| Settings `ENGINE_B_MODE` (read-only) | mode string only | Used to skip ML scoring during non-shadow modes (informational) |

**Forbidden inputs:**
- `paper_trade_log` — execution-side; not ML's concern
- `decision_log` — production routing; not ML's concern
- `position_snapshot`, `order_log`, anything in `apps/api/src/domain/execution/`
- Anything from `apps/worker/src/jobs/run_paper_trading.py`
- Real-time data feeds (Tiingo, Yahoo) — feature engineering uses what's already in `paper_shadow_log`

---

## 3. Feature list

### Market features (per `(as_of_date, instrument)` row)

| Feature | Formula | Window |
|---|---|---|
| `ret_1d` | `fwd_return_1d` (lagged so as-of date evidence only) | 1 day |
| `ret_5d` | sum of past 5 daily returns | 5 days |
| `ret_20d` | sum of past 20 daily returns | 20 days |
| `ret_60d` | sum of past 60 daily returns | 60 days |
| `vol_20d` | std(returns over past 20 days) × √252 | 20 days |
| `vol_60d` | std(returns over past 60 days) × √252 | 60 days |
| `vol_ratio_20_60` | `vol_20d / vol_60d` (regime-shift proxy) | mixed |
| `drawdown_252d` | `1 − close / max(close, last 252)` | 252 days |
| `ma_50` | mean(close, last 50) | 50 days |
| `ma_200` | mean(close, last 200) | 200 days |
| `ma_distance_50_200` | `(ma_50 − ma_200) / ma_200` | derived |
| `close_above_ma_200_persist_3` | binary; matches V2 stress logic | 3-day |
| `realized_skew_60d` | sample skewness of last 60 daily returns | 60 days |
| `realized_kurt_60d` | excess kurtosis of last 60 daily returns | 60 days |

### Divergence features (per `(as_of_date, instrument)`)

| Feature | Source |
|---|---|
| `b2_signal` | from snapshot / paper_shadow_log |
| `v2_signal` | same |
| `divergence_class` | B2_FLAT_V2_LONG / B2_LONG_V2_FLAT / NONE (when agree) |
| `b2_regime` | regime label under v1 logic |
| `v2_regime` | regime label under persist3 logic |
| `regime_disagreement` | binary; b2_regime != v2_regime |
| `trend_score_60d` | from snapshot.b2_trend |

### Snapshot-derived features (per snapshot row)

| Feature | Source |
|---|---|
| `edge_bps_lag1` | previous snapshot's `metrics.avg_return_diff_1d_bps` |
| `impact_weighted_edge_lag1` | previous snapshot's value |
| `verdict_streak_lag1` | previous snapshot's `verdict_streak` |
| `state_at_snapshot` | previous snapshot's stored state (categorical, one-hot) |
| `confidence_lag1` | previous snapshot's `promotion_confidence` |

**Lag handling:** every snapshot-derived feature is taken from the
**immediately prior** snapshot row. The current snapshot is the target
period; using its own values would be feature/target leakage.

### Categorical encoding

- One-hot: `b2_signal`, `v2_signal`, `divergence_class`, `b2_regime`,
  `v2_regime`, `state_at_snapshot`
- All numeric features standardized per training fold (no global mean/std
  → would leak future statistics into past folds)

### Out-of-scope features (v1)

- Cross-asset features (correlations, sector momentum, etc.)
- Macro / rates / credit / options-implied features (mentioned in
  context but require external data sources not in this scope)
- News / sentiment features
- Transformer-style sequence embeddings
- Anything requiring real-time tick data

---

## 4. Targets

| Target name | Definition | Use case |
|---|---|---|
| `next_day_edge_positive` | `1 if (V2_long_return_t+1 − B2_long_return_t+1) > 0 else 0` | Binary — is V2's next-day call better than B2's? |
| `divergence_win` | `1 if delta_t+1 > 0 else 0`, conditioned on `divergence_class != NONE` | Binary — did this divergence event resolve in V2's favor? |
| `tail_event_t+5` | `1 if min(fwd_return_1d, ..., fwd_return_t+5) < -0.02 else 0` (i.e. ≥ 2% drawdown in next 5 days) | Binary — is a tail event imminent? |
| `regime_t+5` | `argmax({STRESS, DIRECTIONAL, NEUTRAL}_t+5)` derived from regime_label series | Multinomial — what regime in 5 days? |

**Target construction lives in `targets.py`, separate from features.**
Cross-validation embargo: between each train and test fold, drop
`embargo_days = max(target_horizon, 5)` rows so labels and features
don't overlap across the IS/OOS boundary.

---

## 5. Models (v1 only)

| Model | Use | Library | Why |
|---|---|---|---|
| `LogisticRegression` (with L2) | Baseline binary classifier | `sklearn.linear_model` | Interpretable; calibration baseline |
| `ElasticNet` (logistic) | Sparse-feature baseline | `sklearn.linear_model` | Handles correlated market features |
| `RandomForestClassifier` | Non-linear baseline | `sklearn.ensemble` | Robust to feature scaling; handles regime interactions |
| `GradientBoostingClassifier` | Strongest baseline candidate | `sklearn.ensemble` (scikit's GBM, not lightgbm) | Per Gu/Kelly/Xiu (2020) findings on tree ensembles |
| `IsotonicRegression` (calibration wrapper) | Probability calibration | `sklearn.isotonic` | Required output is calibrated probability, not raw score |

**Explicitly excluded:**
- Deep learning (CNN, LSTM, Transformer, RNN, MLP > 1 hidden layer)
- Reinforcement learning (any policy or value learner)
- xgboost / lightgbm / catboost (pinned to scikit-learn for v1 — fewer
  dependencies, no native compile chain)
- Online / streaming learners (overcomplicated for weekly snapshots)
- Ensemble-of-ensembles / stacking (after baseline established only)

### Model-class API contract

```python
class AdvisoryModel(Protocol):
    name: str

    def fit(
        self,
        X: np.ndarray,    # (n_samples, n_features)
        y: np.ndarray,    # (n_samples,)
        *,
        sample_weight: np.ndarray | None = None,
    ) -> "AdvisoryModel": ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...

    def feature_importance(self) -> dict[str, float]: ...
```

Calibration is wrapped via `CalibratedClassifierCV(method='isotonic',
cv=PrequentialFolds)` so all model outputs are **calibrated
probabilities**, not raw scores.

---

## 6. Validation

### Walk-forward only

```
Train fold:  [t_0, t_n]
Embargo:     (t_n, t_n + 5d]    ← dropped, no labels available
Test fold:   (t_n + 5d, t_n + 5d + window]
Slide forward; refit; repeat.
```

Implementation in `evaluation.py`:

```python
def prequential_folds(
    *,
    timestamps: np.ndarray,    # sorted ascending
    train_window_days: int = 252,
    test_window_days: int = 30,
    embargo_days: int = 5,
    min_train_size: int = 60,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yields (train_idx, test_idx) per fold. Sorted timestamps required;
    raises if any train_idx[max] >= test_idx[min] (overlap guard)."""
```

### Banned validation patterns

- `sklearn.model_selection.train_test_split` (random shuffle by default)
- `KFold` (no temporal awareness)
- `StratifiedKFold` (same)
- `cross_val_score` without an explicit `cv=PrequentialFolds(...)`
- Any function with `shuffle=True` parameter

**Test (`test_ml_advisory_isolation.py`):**

```python
def test_no_random_shuffle_in_validation():
    """grep evaluation.py for banned patterns; must be zero."""
    src = (Path("apps/api/src/research/ml_advisory/evaluation.py")
           .read_text(encoding="utf-8"))
    for pattern in ("KFold", "train_test_split", "StratifiedKFold",
                     "shuffle=True", "random_split"):
        assert pattern not in src
```

### Metrics

Per fold + aggregated:
- `roc_auc` (skipped for multinomial regime target; replaced by
  `macro_avg_one_vs_rest_auc`)
- `precision_at_top_decile`, `recall_at_top_decile`
- `brier_score` (probability calibration quality)
- `calibration_curve` (10-bin reliability diagram, returned as JSON)
- `incremental_value_vs_baseline`: `auc_model − auc_baseline`, where
  baseline is "always predict majority class" (binary) or "always predict
  most-recent regime" (multinomial)

### Acceptance for promotion to "shadow-display" status (v2 design — out of scope here)

Per Phase 10C instruction §8, ML can be considered for ANY further
promotion only if **all** of:

1. ≥ 6 months out-of-sample stability (rolling AUC ≥ 0.65 sustained)
2. PBO < 0.2 from CSCV (Phase 10A.2 module)
3. Deflated Sharpe Ratio significant on the model's own paper-traded
   "what if we had followed ML" return series
4. Incremental value vs non-ML baseline ≥ 5% AUC and ≥ 0.05 Brier
5. Calibration error < 5% (Brier) on out-of-sample fold
6. Operator approval explicitly noting "ML promotion to shadow display"
7. **`ML_CAN_AFFECT_TRADES` flag remains false even after promotion to
   shadow display** — the flag is only a kill-switch; the design
   doctrine prohibits the flag ever being set to `true`

---

## 7. Output format

### Per-snapshot prediction (returned by `inference.predict_for_snapshot`)

```json
{
  "ml_schema_version": 1,
  "model_name": "gradient_boosting_v1",
  "prediction_date": "2026-05-18",
  "snapshot_id": 42,
  "ml_signal": 0.62,
  "confidence": 0.78,
  "regime_prediction": "DIRECTIONAL",
  "regime_probabilities": {
    "STRESS": 0.10, "DIRECTIONAL": 0.70, "NEUTRAL": 0.20
  },
  "tail_risk_probability": 0.18,
  "explanation": "Top features: trend_score_60d (+0.34), vol_ratio_20_60 (-0.21), impact_weighted_edge_lag1 (+0.17), drawdown_252d (-0.12)",
  "calibration_quality": "GOOD",
  "advisory_only": true,
  "is_used_in_decisions": false,
  "warning": "ML advisory — not used in decisions"
}
```

**Required fields, every prediction:**
- `advisory_only: true` — hard-coded literal
- `is_used_in_decisions: false` — hard-coded literal
- `warning: "ML advisory — not used in decisions"` — hard-coded literal

Tests verify these three fields are byte-equal to the constants in every
output (no template substitution allowed).

### Validation report (returned by `evaluation.run_walk_forward`)

```json
{
  "model_name": "gradient_boosting_v1",
  "target_name": "divergence_win",
  "n_folds": 12,
  "fold_summary": {
    "auc_mean": 0.61, "auc_std": 0.06,
    "brier_mean": 0.21, "brier_std": 0.03,
    "incremental_auc_vs_baseline": 0.04
  },
  "calibration_curve": [
    {"bin_lower": 0.0, "bin_upper": 0.1, "mean_predicted": 0.05, "fraction_positive": 0.07, "count": 145},
    ...
  ],
  "feature_importance": {"trend_score_60d": 0.34, ...},
  "advisory_only": true,
  "promotion_eligible": false,
  "promotion_eligibility_reasons": [
    "auc_mean 0.61 < 0.65 threshold",
    "incremental_auc 0.04 < 0.05 threshold"
  ]
}
```

`promotion_eligible: false` is the v1 default. Even when all numeric
criteria pass, the field remains `false` until an operator explicitly
flips it via a separate process (out of scope for v1).

---

## 8. UI / exposure

### API endpoint (read-only, separate from `/api/v2-promotion/*`)

```
GET /api/ml-advisory/prediction/latest
GET /api/ml-advisory/prediction/{snapshot_id}
GET /api/ml-advisory/validation-report/{model_name}
```

Mounted under `/api/ml-advisory/*` to keep the URL boundary obvious.
Route file: `apps/api/src/api/ml_advisory.py` — separate from
`v2_promotion.py`. Not registered in any other router.

**Tests will verify the gate-evaluation code path and approval API never
call any ML route or import any ML module.**

### UI panel

New file `apps/web/src/components/ops/MLAdvisoryCard.tsx`. Mounted on
the Ops page **below** `V2PromotionTriggerCard`. Visual treatment:

```
┌─── ML Advisory ──────────────────────────────  [ADVISORY ONLY] ─┐
│                                                                  │
│  ⚠ ML advisory — not used in decisions                           │
│                                                                  │
│  Model: gradient_boosting_v1   Prediction date: 2026-05-18       │
│  ml_signal:           0.62  ━━━━━━━━━━░░░░░░  (confidence 0.78)  │
│  regime_prediction:   DIRECTIONAL                                 │
│  tail_risk_prob:      0.18  ━━━░░░░░░░░░░░░░                     │
│                                                                  │
│  Top features:                                                   │
│    trend_score_60d         +0.34                                 │
│    vol_ratio_20_60         −0.21                                 │
│    impact_weighted_edge    +0.17                                 │
│                                                                  │
│  Calibration: GOOD       Promotion eligible: NO                  │
└──────────────────────────────────────────────────────────────────┘
```

Hard rules for the UI:
- The amber `[ADVISORY ONLY]` chip is non-removable
- The line `⚠ ML advisory — not used in decisions` is non-removable
- No buttons, no actions, no inputs — pure read display
- No promotion suggestion, no "approve ML" button
- No mixing with V2 promotion-trigger UI panel
- Card refresh interval ≥ 60s (not real-time)

---

## 9. Future promotion criteria (DESIGN ONLY — DO NOT IMPLEMENT)

If, after months of stable shadow operation, an operator wishes to
"promote" ML output to a higher-visibility advisory status (e.g.
inclusion in OOS monitoring report), the following pre-registered
criteria must hold:

| # | Criterion | Threshold |
|---|---|---|
| 1 | OOS stability — rolling 26-week AUC | mean ≥ 0.65, std ≤ 0.08 |
| 2 | PBO via CSCV (Phase 10A.2 module) | < 0.20 |
| 3 | Deflated Sharpe Ratio on hypothetical ML-followed series | `is_significant = True` |
| 4 | Incremental AUC vs majority-class baseline | ≥ 0.05 |
| 5 | Brier calibration error | < 0.05 |
| 6 | Operator approval row in a DEDICATED `ml_promotion_approval` table | required |
| 7 | `ML_CAN_AFFECT_TRADES` flag | **stays false** — promotion to display is NOT promotion to execution |

**Even after meeting all 7, ML never enters execution.** "Promotion" in
this framework means: ML output appears in the OOS monitoring report's
informational sidebar. It still has zero effect on gates, state, or
approval. The kill-switch flag remains false.

The criteria are pre-registered here so that future operator approval
cannot move the goalposts. Any change requires a documented design-doc
revision.

---

## 10. Boundaries verification — grep + behavioral

### Grep matrix (post-implementation enforcement)

| # | Direction | Pattern | Files | Expected |
|---:|---|---|---|:---:|
| 1 | ML → governance | `v2_promotion_gates|v2_promotion_state|v2_promotion_snapshot|v2_promotion\.py|approve|rescind|RESUME_FROM_SUSPENDED` | `apps/api/src/research/ml_advisory/**.py` | 0 |
| 2 | ML → execution | `engine_b|shadow_strategy|paper_trade_log|decision_log|paper_trade|order_log|position_snapshot|execute|order|sizing|routing` | `apps/api/src/research/ml_advisory/**.py` | 0 |
| 3 | Governance → ML | `ml_advisory|ml_inference|ml_model|ml_predict|MLAdvisory` | `apps/api/src/research/v2_promotion_gates.py`, `v2_promotion_state.py`, `b2_v2_comparison.py`, `v2_oos_monitoring.py`, `v2_stat_validation.py`, `apps/api/src/api/v2_promotion.py`, `apps/api/src/api/b2_v2_comparison.py`, `apps/worker/src/jobs/v2_promotion_snapshot.py` | 0 |
| 4 | Execution → ML | `ml_advisory` | `apps/api/src/domain/execution/**`, `apps/worker/src/jobs/run_paper_trading.py`, `apps/api/src/api/operator.py` | 0 |
| 5 | Banned validation idioms | `KFold|train_test_split|StratifiedKFold|shuffle=True|random_split|cross_val_score(?!.*PrequentialFolds)` | `apps/api/src/research/ml_advisory/evaluation.py` | 0 |
| 6 | Kill-switch flag preserved | `ML_CAN_AFFECT_TRADES\s*=\s*True` | entire repo | 0 |
| 7 | Required output disclaimer constants | `"ML advisory — not used in decisions"` | `apps/api/src/research/ml_advisory/inference.py` | ≥ 1 |
| 8 | UI label preserved | `ADVISORY ONLY|advisory_only|not used in decisions` | `apps/web/src/components/ops/MLAdvisoryCard.tsx` | ≥ 3 |

### Behavioral isolation tests

Implemented in `apps/api/tests/unit/test_ml_advisory_isolation.py`:

```python
def test_governance_modules_do_not_import_ml():
    """Inverse of grep #3 — actual import-graph walk."""
    import importlib, sys
    # Snapshot sys.modules
    before = set(sys.modules)
    importlib.import_module("src.research.v2_promotion_gates")
    importlib.import_module("src.research.v2_promotion_state")
    importlib.import_module("src.research.v2_oos_monitoring")
    after = set(sys.modules)
    new_modules = after - before
    assert not any("ml_advisory" in m for m in new_modules)


def test_ml_module_does_not_import_governance():
    import importlib, sys
    before = set(sys.modules)
    importlib.import_module("src.research.ml_advisory")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = ("v2_promotion_gates", "v2_promotion_state",
                  "v2_promotion_snapshot", "engine_b", "shadow_strategy")
    for f in forbidden:
        assert not any(f in m for m in new_modules), \
            f"forbidden module {f} imported via ml_advisory"


def test_advisory_only_disclaimer_in_every_prediction():
    """Schema-level invariant — every prediction dict carries the literal."""
    from src.research.ml_advisory import predict_for_snapshot
    out = predict_for_snapshot(snapshot_id=DUMMY_SNAPSHOT_ID)
    assert out["advisory_only"] is True
    assert out["is_used_in_decisions"] is False
    assert out["warning"] == "ML advisory — not used in decisions"


def test_ml_can_affect_trades_remains_false():
    from src.config import settings
    assert settings.ML_CAN_AFFECT_TRADES is False
```

### "What would break isolation" — explicit failure modes

Documented so any future contributor recognizes them as red lines:

1. **Importing `predict_for_snapshot` inside `v2_promotion_gates.py`** — would couple ML to gate evaluation. Test #3 grep catches this.
2. **Adding `ml_signal` to `comparison_bundle_json`** via `compute_all` → snapshot job persists ML data → governance reads it. **Forbidden.** ML output lives in its own response payload, never inside snapshot JSON.
3. **Adding an `ML_OVERRIDE` decision type to `v2_promotion_approval`** — would let ML "approve" via a side-channel. The decision CHECK constraint is locked at `(APPROVE, RESCIND, RESUME_FROM_SUSPENDED)`; any extension requires a migration + design-doc revision.
4. **Setting `ML_CAN_AFFECT_TRADES = true` in settings** — single-flag kill switch. Test #6 + test #4 enforce it stays `false`.
5. **Reading ML output from inside the snapshot job** — would make ML data persist in `comparison_bundle_json`. The snapshot job's `fetch_comparison_bundle` is locked to read from `paper_shadow_log` only.
6. **Modifying `MLAdvisoryCard.tsx` to remove the "ADVISORY ONLY" chip** — UI label is part of the contract. Test #8 enforces.
7. **Allowing `predict_for_snapshot` to write to ANY DB table** — module is read-only; even if a future cache layer is added, it goes in a separate `ml_advisory_cache` table never read by governance.
8. **Letting ML run during APPROVED state and have its output displayed alongside the approval card** — could create the visual implication "ML supports this approval." UI design forbids co-location with promotion-trigger card; ML card always sits in a separate panel further down the page.

---

## 11. Data flow diagram

```
                            (read-only inputs)
                                   │
            ┌──────────────────────┼─────────────────────┐
            ▼                      ▼                     ▼
   paper_shadow_log     v2_promotion_snapshot       settings.ENGINE_B_MODE
            │                      │                     │
            ├─────────────┬────────┘                     │
            ▼             ▼                              │
   features.py      targets.py                           │
            │             │                              │
            └──────┬──────┘                              │
                   ▼                                     │
            X, y matrices                                │
                   │                                     │
                   ▼                                     │
         ┌──── inference.py ────┐                        │
         │  load model_*.pkl    │ ◄─ models.py (offline-trained)
         │  predict_proba       │                        │
         │  build output dict   │                        │
         └──────────┬───────────┘                        │
                    ▼                                    │
         { ml_signal, ..., advisory_only: true,          │
           warning: "ML advisory — not used in           │
           decisions" }                                  │
                    │                                    │
                    ▼                                    │
         ┌─────────────────────────────────┐             │
         │ /api/ml-advisory/prediction/... │ ◄───────────┘ (informational)
         └─────────────┬───────────────────┘
                       ▼
         ┌─────────────────────────┐
         │ MLAdvisoryCard.tsx (UI) │
         │ "ADVISORY ONLY" chip    │
         └─────────────────────────┘

                    ✗ NEVER FLOWS BACK ✗

                  ╔══════════════════════════╗
                  ║     GOVERNANCE LAYER     ║
                  ║  v2_promotion_gates.py   ║
                  ║  v2_promotion_state.py   ║
                  ║  v2_promotion_snapshot   ║
                  ║  v2_promotion (API)      ║
                  ║                          ║
                  ║  reads ZERO from ML      ║
                  ║  imports ZERO ML code    ║
                  ╚══════════════════════════╝

                  ╔══════════════════════════╗
                  ║     EXECUTION LAYER      ║
                  ║  engine_b_router         ║
                  ║  paper_trade_log         ║
                  ║  decision_log            ║
                  ║                          ║
                  ║  reads ZERO from ML      ║
                  ║  ML_CAN_AFFECT_TRADES =  ║
                  ║    false  (locked)       ║
                  ╚══════════════════════════╝

                  ╔══════════════════════════╗
                  ║     OOS MONITORING       ║
                  ║  v2_oos_monitoring       ║
                  ║                          ║
                  ║  reads ZERO from ML in   ║
                  ║  v1; future v2 may       ║
                  ║  surface ML calibration  ║
                  ║  metrics in a side panel ║
                  ║  ONLY if ML hits all     ║
                  ║  promotion criteria § 9. ║
                  ╚══════════════════════════╝
```

---

## 12. Model selection rationale

| Choice | Rationale |
|---|---|
| Logistic regression first | Establishes interpretable baseline; calibration sanity check. Linear coefficients double as feature-importance proxy. |
| Elastic net second | Handles correlated features (vol_20d / vol_60d / vol_ratio_20_60 are nearly collinear). L1 component prunes redundant inputs without manual feature selection. |
| Random forest third | Captures interactions (e.g. regime × trend_score) that logistic models miss. Robust to feature scaling — useful sanity baseline for tree-based models before tuning GBM. |
| Gradient boosting fourth | Gu/Kelly/Xiu (2020) finding: tree ensembles materially outperform linear models for asset-return prediction across multiple targets. Use as the primary v1 production-shadow model. |
| Isotonic calibration always | Raw model scores are not probabilities. Isotonic regression converts them into calibrated probabilities suitable for the `ml_signal ∈ [0, 1]` output contract. Brier score measures quality. |
| **No deep learning** | Insufficient data (we have months of OOS, not years), interpretability requirement (operator must read top features), and unjustified complexity for a binary/multinomial task. |
| **No xgboost / lightgbm** | scikit-learn ships with `GradientBoostingClassifier`. Cuts deployment dependencies; no native compile chain. v2 may evaluate xgboost only if scikit's GBM proves materially weaker after walk-forward CV. |
| **No RL** | Reinforcement learning requires either a reward simulator (we don't have one) or live trading (forbidden). Out of scope indefinitely. |

---

## 13. Validation methodology — full detail

1. **Sort by `as_of_date`** ascending. No randomization at any step.
2. **Define `train_window_days = 252`** (1 year), `test_window_days = 30`,
   `embargo_days = 5` (matches longest target horizon).
3. **Generate folds** via `prequential_folds(...)`. Verify with an
   assertion that `max(train_idx_dates) + embargo_days ≤ min(test_idx_dates)`
   for every fold.
4. **Per fold:**
   a. Standardize numeric features using train-fold mean/std only
   (no global statistics — would leak).
   b. Fit calibration wrapper: `CalibratedClassifierCV(base_estimator,
   method='isotonic', cv=PrequentialFolds(n_inner=5))`.
   c. Predict on test fold.
   d. Record AUC, Brier, calibration curve.
5. **Aggregate** across folds: mean ± std for every metric.
6. **Compute** incremental value vs majority-class baseline.
7. **Run PBO** on the family of variants tried (logistic / elastic net /
   RF / GBM × hyperparameter grid). Use Phase 10A.2's `compute_pbo`.
   PBO ≥ 0.20 → flag overfit risk in validation report.
8. **Run DSR** on the model's per-fold returns (if treating ML as a
   hypothetical strategy). DSR < significance threshold → flag.
9. **Output** `validation-report` JSON per §7.

**No hyperparameter search using random shuffle CV.** All hyperparameter
selection happens inside the prequential framework. Even
`GridSearchCV` is allowed only with `cv=PrequentialFolds`.

---

## 14. Leakage-prevention rules (codified for future contributors)

1. **No global statistics.** Any feature normalization uses train-fold
   statistics only; never `df.mean()` on the full dataset.
2. **No future labels in features.** Snapshot-derived features always
   come from `t-1` (immediately prior snapshot). The current-period
   snapshot is the target context, never the feature source.
3. **No look-ahead in target construction.** `targets.py` only reads
   `fwd_return_1d`, `fwd_return_5d` for periods STRICTLY AFTER the
   current `as_of_date`. Verified by unit test against synthetic data.
4. **Embargo gap.** Train and test folds always separated by ≥ 5 days
   (the longest target horizon).
5. **No data inheritance from future folds.** Each fold's preprocessing
   pipeline (scaler, encoder) fit ONLY on that fold's train slice.
6. **Calibration on its own holdout.** `CalibratedClassifierCV` uses an
   inner prequential split; calibration data never touches the test
   fold.
7. **Snapshot lag enforcement.** `features.py` raises if asked to build
   features for a snapshot whose `as_of_date` is also among the
   `prior_snapshots` list.
8. **No cross-asset, cross-strategy peek.** v1 builds features per
   `(as_of_date, instrument)`; multi-instrument features deferred to v2
   when properly designed.
9. **No reading `verdict` field as a feature.** The verdict is partially
   computed from `metrics.avg_return_diff_1d_bps`, which is itself a
   target candidate. Including it would be label leakage. **Forbidden.**

---

## 15. Files to be added (Phase 10C.2 implementation — separate explicit approval required)

| File | Type | Lines (est.) |
|---|---|---:|
| `apps/api/src/research/ml_advisory/__init__.py` | NEW | ~15 |
| `apps/api/src/research/ml_advisory/features.py` | NEW | ~400 |
| `apps/api/src/research/ml_advisory/targets.py` | NEW | ~150 |
| `apps/api/src/research/ml_advisory/models.py` | NEW | ~250 |
| `apps/api/src/research/ml_advisory/evaluation.py` | NEW | ~350 |
| `apps/api/src/research/ml_advisory/inference.py` | NEW | ~250 |
| `apps/api/src/research/ml_advisory/README.md` | NEW | ~150 |
| `apps/api/src/api/ml_advisory.py` | NEW | ~150 |
| `apps/api/src/main.py` | EDIT (add 1 router) | +2 lines |
| `apps/api/tests/unit/test_ml_advisory_features.py` | NEW | ~400 |
| `apps/api/tests/unit/test_ml_advisory_models.py` | NEW | ~250 |
| `apps/api/tests/unit/test_ml_advisory_evaluation.py` | NEW | ~400 |
| `apps/api/tests/unit/test_ml_advisory_isolation.py` | NEW | ~200 |
| `apps/api/tests/integration/test_ml_advisory_smoke.py` | NEW | ~150 |
| `apps/web/src/lib/mlAdvisory/hooks.ts` | NEW | ~80 |
| `apps/web/src/components/ops/MLAdvisoryCard.tsx` | NEW | ~250 |
| `apps/web/src/pages/Ops.tsx` | EDIT (mount card) | +2 lines |
| `pyproject.toml` | EDIT (add `scikit-learn`) | +1 line |

**Files NOT modified in Phase 10C.2:**
- `v2_promotion_gates.py`, `v2_promotion_state.py`, `b2_v2_comparison.py`
- `v2_promotion.py` (API), `b2_v2_comparison.py` (API)
- `v2_promotion_snapshot.py` (worker job)
- `v2_oos_monitoring.py`, `v2_stat_validation.py`
- All execution / routing / risk modules
- All migrations
- `settings.ML_CAN_AFFECT_TRADES` (stays false)

---

## 16. Acceptance criteria (Phase 10C.2 implementation)

When code finally lands (separate explicit approval required):

1. All 8 grep boundary checks return zero substantive matches (or, for #7+#8, ≥ N expected matches as documented).
2. All 4 behavioral isolation tests pass.
3. `pytest -p no:randomly` produces identical predictions across runs (model load is deterministic).
4. `import_graph` walk confirms no ML modules pulled in via governance imports, and vice versa.
5. Walk-forward validation runs without raising; embargo overlap test passes.
6. Output dict carries `advisory_only: true`, `is_used_in_decisions: false`, and `warning: "ML advisory — not used in decisions"` byte-equal in every prediction.
7. UI card renders the amber "ADVISORY ONLY" chip + warning line; card sits below `V2PromotionTriggerCard` on Ops page; no buttons.
8. `ML_CAN_AFFECT_TRADES` remains `false` in `settings.py`; grep + runtime assertion both verify.
9. `compute_all` bundle is byte-identical (no `ml_signal` field added).
10. Snapshot job + approval API behavior unchanged.

---

## 17. What is explicitly out of scope for Phase 10C.2

- Deep learning of any kind
- xgboost / lightgbm / catboost / RL
- Real-time / streaming prediction
- ML-driven sizing or routing — **forbidden indefinitely**
- ML-driven gate evaluation — **forbidden indefinitely**
- ML appearing in the OOS monitoring report — gated on §9 promotion criteria
- ML appearing in the V2 promotion-trigger card — **forbidden indefinitely**
- Cross-instrument modeling — v2 design
- Online learning — v2 design

---

## 18. Final recommendation

`SAFE_TO_CONTINUE_OBSERVING` pending operator approval of this design.

After Phase 10C.2 ships and passes review, ML lives as a **completely
parallel research universe**. The governance machinery never knows it
exists. The execution machinery never knows it exists. The only
permitted contact surface is the read-only API endpoint and the
UI card, both labeled "ADVISORY ONLY — not used in decisions."

**Awaiting operator approval to implement Phase 10C.2.**
