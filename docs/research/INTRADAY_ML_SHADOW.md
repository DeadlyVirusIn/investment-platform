# Intraday ML Shadow Layer — Architecture Proposal

> **Phase 1 (architecture-only).** Proposes a shadow ML layer that
> observes 15-min delayed Polygon data and produces display-only
> confidence / risk / urgency deltas. Extends the existing EOD shadow
> infrastructure at `apps/api/src/ml/shadow/`. NOT yet implemented;
> requires operator approval + per-phase validation gates.
>
> **Hard rules carried forward from the operator's brief:**
> - No paper-trade execution cadence change
> - No intraday trades; no same-bar execution; `find_next_open()` untouched
> - No mutation of the `recommendation` table
> - No retraining of the production EOD model
> - Paper-only enforced
> - Sufficient historical intraday data MUST exist before model training;
>   no synthetic data, no fabricated samples

---

## Existing pipeline anchors (audit findings)

The audit confirmed a fully-formed EOD shadow infrastructure already
exists. **The intraday shadow inherits this pattern wholesale rather
than rebuilding.** Key file:line references:

| Anchor | Location | Behavior |
|---|---|---|
| EOD model training entry | `apps/api/src/ml/shadow/trainer.py:89` `train_shadow_models()` | Walk-forward trains; nightly when enabled |
| Shadow orchestrator | `apps/api/src/ml/shadow/orchestrator.py` | Owns training + scoring + promotion checks |
| Shadow scorer table | `ml_shadow_prediction` (ml_score, ml_confidence, ml_action, ml_reason_codes, baseline_action, evaluation JSONB) | Display-only; **never** affects trades |
| Hybrid policy | `apps/api/src/ml/shadow/hybrid_policy.py` | Computes size multiplier, gated by `ML_HYBRID_ENABLED` |
| Promotion guard | `apps/api/src/governance/promotion_engine.py:18-29` | Thresholds (labeled outcomes, advice count, ECE, Sharpe delta, operator approval) |
| Model registry | `apps/api/src/ml/model_registry.py:24-26` | File-based `models/model_registry.json`; append-only |
| Walk-forward splits | `apps/api/src/ml/splits.py:64-150` `walk_forward_splits()` | Purge 5d + embargo 2d per AFML Ch.7 |
| Feature whitelist | `apps/api/src/ml/features.py:1-11` `FEATURE_COLUMNS` + `TRAINING_FEATURE_WHITELIST` | Pre-decision-time only (anti-lookahead) |
| Label generator | `apps/api/src/ml/labels.py:61-141` `attach_labels()` | Forward returns (1/3/5/10d) + MAE/MFE + triple-barrier (PC-4) |
| Outcome scoring runner | `apps/worker/src/jobs/score_outcomes.py:1-31` | Writes RecommendationOutcome (barrier_label, regimes) |
| Conviction computation | `apps/api/src/domain/recommendations/recommendation_engine.py:152-199` `_compute_confidence()` | Signal-agreement % × 100, penalized for stale/missing |
| Idempotency | `Recommendation` UNIQUE (asset_id, model_version, snapshot_hash) | Inherited pattern for the intraday sidecar |
| Production-off flags | `config/__init__.py:19,68,164` `ENABLE_ML_SIZING`, `ML_CAN_AFFECT_TRADES`, `ML_HYBRID_ENABLED` (all default False) | Same pattern for the intraday shadow flag |

**Critical gap:** intraday bars are **not currently ingested**. `PriceBar.timeframe` accepts `'15m'` / `'1m'` but only `'1d'` rows exist. The intraday shadow's Phase 2 (data collection) is therefore the **load-bearing first step** — without months of stored intraday data, the shadow model has nothing to train on.

---

## 1. Intraday feature schema

Per the operator's brief. Each feature is computed per
`(recommendation_id, observed_at_15min)` row. **All features are
observational; none modify the EOD recommendation's feature vector.**

| Feature | Type | Computation | Source |
|---|---|---|---|
| `intraday_change_pct` | float | `(price - prev_close) / prev_close * 100` | Polygon tape snapshot |
| `vs_open_pct` | float\|null | `(price - day.o) / day.o * 100` (null pre-market) | Polygon tape snapshot |
| `vs_recommendation_entry_pct` | float | `(price - entry_ref) / entry_ref * 100` | Polygon snapshot + `Recommendation.generated_at` close |
| `vs_macro_drift_pct` | float\|null | `intraday_change_pct(symbol) - intraday_change_pct(SPY)` | Polygon tape |
| `intraday_range_pct` | float\|null | `(day.h - day.l) / day.o * 100` | Polygon tape snapshot (`day` block) |
| `spy_change_pct` | float | SPY's `intraday_change_pct` | Polygon tape |
| `qqq_change_pct` | float | QQQ's `intraday_change_pct` | Polygon tape |
| `dia_change_pct` | float | DIA's `intraday_change_pct` | Polygon tape |
| `time_of_day_bucket` | enum(7) | premarket / open30 / morning / midday / afternoon / close30 / afterhours | derived from observed_at_et |
| `prior_eod_conviction` | float | `Recommendation.conviction` at generation | DB join |
| `action_type` | enum(4) | buy / sell / trim / hold | DB join from latest rec |
| `position_state` | enum(3) | open_long / open_short / flat | `PaperPosition.is_open` join |
| `atr_60d_pct` | float | 60-day ATR / current price × 100 | Existing daily `price_bar` |
| `vol_60d_pct` | float | 60-day return σ × √252 × 100 | Existing daily `price_bar` |
| `sector_id` | str\|null | Asset.sector if present | DB |

**Symbol scope (v1):** macro tape (SPY/QQQ/DIA) + open paper positions + symbols on today's active recommendation list. Cap at 100 per
arch-doc §"Symbol allow-list" governance.

---

## 2. Label definitions

Labels are computed **at end of session** (after all relevant
intraday observations are written), joining the
`RecommendationOutcome` data once it lands at T+1 / T+30 / T+90 via
the existing `score_outcomes.py` cron. **No labels touch the
production training data — they live in a parallel table.**

| Label | Type | Definition | Source |
|---|---|---|---|
| `eod_favorable_today` | bool | Did the EOD recommendation remain favorable by today's close? (close return aligned with action sign) | `Recommendation.action` × today's close move |
| `adverse_threshold_breached` | bool | `vs_recommendation_entry_pct < -1.5σ` at any intraday point that day | rolling max over the day's intraday rows |
| `outcome_improved_t1` | int (-1/0/+1) | Did `RecommendationOutcome.realized_1d_return` improve / hold / degrade after this intraday observation? | `score_outcomes.py` output at T+1 |
| `stress_predicted_bad_followthrough` | bool | `context_label="stress"` at observed_at AND `outcome_improved_t1 == -1` | derived label-of-labels |
| `windfall_predicted_trim_opportunity` | bool | `context_label="windfall"` at observed_at AND realized_3d_return < observed_at's `vs_recommendation_entry_pct` | derived |
| `confidence_delta_realized` | float | `RecommendationOutcome.realized_1d_return - prior_eod_conviction_implied_return` | derived |

The labels are intentionally redundant — `eod_favorable_today` is the
primary regression target; the booleans are secondary classification
heads for diagnostics + label-quality QA.

---

## 3. Training window proposal

**Cannot begin Phase 3 (training) until Phase 2 (collection) has
accumulated sufficient labeled data.** Quantitative gates:

| Gate | Threshold | Rationale |
|---|---|---|
| Calendar days of intraday coverage | **≥ 60 trading days** | One regime quarter; covers a holiday distribution |
| Labeled `eod_favorable_today` rows | **≥ 5,000** | At ~25 rows/symbol/day × 30 symbols × 60 days = ~45k rows; 5k is the floor where 10-fold walk-forward becomes meaningful |
| Distinct symbols with ≥ 30 days coverage | **≥ 20** | Prevents overfitting to 3-symbol macro tape |
| `adverse_threshold_breached` positive class share | **≥ 5%** | Avoid class-imbalance collapse |
| Audit: zero overlapping training/eval timestamps | **0** | Walk-forward purge+embargo must show clean separation |

**Walk-forward configuration (inherits from `splits.py:64-150`):**
- Train window: 30 trading days
- Validation window: 5 days
- Test window: 5 days (held-out, scored only)
- **Purge: 5 trading days** (same as EOD)
- **Embargo: 2 trading days** (same as EOD)
- Non-rolling refit (one fit per fold)

Reuses `walk_forward_splits()` unchanged.

---

## 4. Validation metrics

Per the existing promotion engine pattern at
`governance/promotion_engine.py:18-29`. The intraday shadow promotes
to Phase 4 (UI display) **only** when all five gates pass on the
held-out test folds:

| Metric | Threshold | Why |
|---|---|---|
| **AUC vs EOD baseline** | ≥ +0.02 | Must add discrimination over EOD alone |
| **ECE (Expected Calibration Error)** | ≤ 0.10 | Display-confidence deltas must be calibrated |
| **Sharpe delta on shadow-suggested portfolio** | ≥ 0.0 | Don't promote a model that would have hurt |
| **False-stress rate** | ≤ 0.30 | "Stress" alerts that didn't predict bad outcomes |
| **Min labeled outcomes per regime bucket** | ≥ 100 | Prevents pathological regime-conditional bias |
| **Operator approval flag** | required | Inherits `ML_PROMOTION_REQUIRE_OPERATOR_APPROVAL` pattern |

Additional diagnostics (logged, not gates):
- Per-`time_of_day_bucket` performance (catches intraday seasonality)
- Per-`action_type` breakdown
- Per-`position_state` breakdown
- Feature importance (top 10)
- Calibration plot (reliability diagram, 10 bins)

---

## 5. Leakage risks + no-lookahead rules

Inherits the EOD anti-lookahead patterns (`stock_factor_engine.py:4-6`,
`features.py:1-11`) and adds intraday-specific guards.

### Hard rules

1. **Observation timestamp gate.** Every feature row carries
   `observed_at_15min` (delayed quote_ts from Polygon — never wall
   clock). The label computation MUST use only data with
   `data_ts > observed_at_15min + 15 minutes` (the delay floor). This
   prevents a future tick from leaking into a same-bar feature.
2. **EOD label timestamp gate.** `eod_favorable_today` uses
   `today's close_price`; that close lands in `price_bar` at the
   22:00 ET ingest. Training joins MUST filter `price_bar.ts > today_close_ts`.
3. **`RecommendationOutcome` join gate.** Outcome rows arrive at T+1
   / T+30 / T+90 via `score_outcomes.py`. Training joins MUST filter
   `outcome.created_at > observed_at_15min + label_horizon_days`.
4. **Walk-forward purge.** 5-day purge + 2-day embargo prevents the
   final intraday observation in a train fold from sitting next to
   the first feature in the val/test fold.
5. **No feature engineering on future data.** The 60-day ATR and σ
   features are computed from daily bars **up to and including
   yesterday** — never today's bar. Same pattern as the EOD model.

### Soft rules (audited per fold)

6. **Symbol-imbalance check.** No single symbol may contribute > 15%
   of training rows. Cap; warning if hit.
7. **Time-of-day balance check.** Each `time_of_day_bucket` must have
   ≥ 200 training rows. Warning if not.
8. **Action-type balance check.** Hold rows (the dominant class)
   must be downsampled to ≤ 50% of training set during
   classification heads. Warning if not.

### Re-validation cadence

The shadow model re-trains weekly (Sunday 23:00 ET — outside the
weekday cron). Each refit produces a new `model_version` and the
above 5+3 checks rerun. Failures are logged + emailed; the prior
version remains in serving.

---

## 6. Cache / storage plan

Two new persistent tables (Phase 2 data collection requires
durability — the Phase 16 v1 ephemeral overlay pattern does NOT
apply here, because labels require history). Both tables sit
alongside `ml_shadow_prediction` to mirror the existing pattern.

### Table 1 — `intraday_observation` (Phase 2 onwards)

Captures one feature row per (recommendation, 15-min cycle). This is
the durable training input.

```sql
CREATE TABLE intraday_observation (
  id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id               VARCHAR(36) NOT NULL REFERENCES recommendation(id),
  symbol                          VARCHAR(16) NOT NULL,
  observed_at_15min               TIMESTAMPTZ NOT NULL,   -- truncated to 15-min slot

  -- Features (§1)
  intraday_change_pct             NUMERIC(10, 4),
  vs_open_pct                     NUMERIC(10, 4),
  vs_recommendation_entry_pct     NUMERIC(10, 4),
  vs_macro_drift_pct              NUMERIC(10, 4),
  intraday_range_pct              NUMERIC(10, 4),
  spy_change_pct                  NUMERIC(10, 4),
  qqq_change_pct                  NUMERIC(10, 4),
  dia_change_pct                  NUMERIC(10, 4),
  time_of_day_bucket              VARCHAR(16) NOT NULL,
  prior_eod_conviction            NUMERIC(10, 4),
  action_type                     VARCHAR(8) NOT NULL,
  position_state                  VARCHAR(16) NOT NULL,
  atr_60d_pct                     NUMERIC(10, 4),
  vol_60d_pct                     NUMERIC(10, 4),
  sector_id                       VARCHAR(64),

  -- Provenance
  source                          VARCHAR(16) NOT NULL,   -- "polygon"
  delay_minutes                   SMALLINT NOT NULL,      -- 15
  quote_ts                        TIMESTAMPTZ,
  feature_hash                    VARCHAR(32) NOT NULL,   -- SHA256(features)[:32]
  created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_intraday_obs UNIQUE (recommendation_id, observed_at_15min)
);
CREATE INDEX ix_intraday_obs_symbol_time
  ON intraday_observation (symbol, observed_at_15min DESC);
CREATE INDEX ix_intraday_obs_observed
  ON intraday_observation (observed_at_15min DESC);
```

**Retention:** 365 days. Daily prune cron at 22:00 ET piggybacks on
existing ingest job; no new cron row.

**Bounded size:** 100 symbols × 26 cycles/day × 252 days/yr ≈ 655k
rows/year. At ~200 B/row, ~130 MB/year. Postgres handles trivially.

### Table 2 — `intraday_shadow_prediction` (Phase 3 onwards)

Mirrors `ml_shadow_prediction` but indexed by intraday observation.
Display-only; **never** affects trades or recommendations.

```sql
CREATE TABLE intraday_shadow_prediction (
  id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  intraday_observation_id         UUID NOT NULL REFERENCES intraday_observation(id) ON DELETE CASCADE,
  model_version                   VARCHAR(64) NOT NULL,

  -- Outputs (display only)
  confidence_delta                NUMERIC(10, 4),   -- ±20 typical range
  risk_delta                      NUMERIC(10, 4),
  urgency_label                   VARCHAR(16),      -- low/normal/elevated/high
  shadow_action_advice            VARCHAR(8),       -- consistent_with / drift_from / contradict
  reason_codes                    JSONB,            -- top-3 feature contributions
  evaluation                      JSONB,            -- pred_proba, calibration bucket, etc.

  -- Provenance
  created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_intraday_shadow_pred UNIQUE (intraday_observation_id, model_version)
);
```

**Retention:** mirrors `intraday_observation` (365d, CASCADE delete).

### Why these are durable (vs Phase 16 ephemeral overlay)

The Phase 16 overlay was ephemeral because it produced only
display-tone hints — no model behind it, no validation downstream.
The ML shadow MUST persist because:
- Training requires N months of labeled history
- Walk-forward purge+embargo requires explicit timestamps stored
- Phase 4+ promotion decisions are auditable against historical predictions
- Per-regime backtests require the raw observation row to exist

These tables are write-mostly + bulk-read (during training); no hot
request-path queries. Acceptable schema cost.

### Polygon ingest changes

To populate `intraday_observation`, two providers must yield 15-min bars:

1. **Live path** — the existing `apps/api/src/api/market.py` poller
   already fetches snapshots every 90s. New code writes ONE row per
   symbol per 15-min slot (de-dupe via `observed_at_15min` unique
   constraint). No new poller, no cron change.
2. **Historical backfill** — new one-off script
   `scripts/backfill_intraday_observations.py` walks
   `/v2/aggs/ticker/{sym}/range/15/minute/{from}/{to}` for the
   active symbol allow-list and synthesizes observation rows for
   the past N days **once** at Phase 2 start. Polygon Stocks Starter
   gives ≥ 2 years of intraday history; we backfill 60–120 days
   initially.

---

## 7. UX changes

**Phase 1–3: no UX change at all.** The shadow runs offline.

**Phase 4 — display deltas (operator-gated):**

The existing `IntradayContextLine` (committed `5be86a9`) is extended
to optionally render a second clause when the shadow model is
serving + has produced a non-null delta:

```
Today aligned · NVDA -0.3% vs morning thesis · context adjusts confidence -4
Today under stress · TSLA -2.4% vs entry · risk elevated vs morning thesis
```

All three deltas (confidence_delta, risk_delta, urgency_label) are
**display only**. The recommendation's stored `conviction` is
unchanged. Hover tooltip discloses:

> Confidence delta is the intraday ML shadow's view based on 15-min
> delayed market data + your position's current move. Does not
> affect sizing or execution.

Feature flag `INTRADAY_ML_SHADOW_UI_ENABLED` gates the second clause
independently of `INTRADAY_ML_SHADOW_ENABLED` (which gates the
serving layer). Operator can enable serving (Phase 3) without
exposing UI (Phase 4) — useful for offline validation.

---

## 8. Governance rules

Hard locks for the entire shadow layer:

1. **Zero writes to `recommendation` table.** Same `persist()`
   sole-writer rule holds (`recommendation_engine.py:380-462`).
2. **Zero writes to `paper_trade` / `paper_position`.** The shadow
   has no path into execution. Audited.
3. **Zero writes to the existing `ml_shadow_prediction` table.** New
   table is `intraday_shadow_prediction`; the EOD shadow's table is
   untouched.
4. **Zero changes to the EOD model.** The recommendation model
   training (`shadow/trainer.py:89`) ingests the same features it
   does today.
5. **`INTRADAY_ML_SHADOW_ENABLED` defaults False.** Same shape as
   `ML_HYBRID_ENABLED`, `ML_CAN_AFFECT_TRADES`, `ENABLE_ML_SIZING`
   (audited at `config/__init__.py:19,68,164`).
6. **Promotion gate per §4.** All 5+ metrics must pass test folds
   AND operator approves before Phase 4 ships.
7. **Symbol allow-list cap.** 100 symbols max — same as Phase 16.
8. **Audit: snapshot_hash equivalent.** `intraday_observation` uses
   the `feature_hash` column (SHA256 of feature dict, 32 chars) so
   duplicate cycles upsert idempotently. Mirrors
   `Recommendation.snapshot_hash`.
9. **No retraining on production cadence.** The intraday shadow's
   weekly Sunday refit runs OUTSIDE the existing weekday EOD cron.
   `score_outcomes` and `run_recommendations` are not touched.
10. **Re-audit of leakage rules per refit.** §5 hard rules 1–5 are
    asserted programmatically before the trainer accepts a fold.

---

## 9. Execution rules

Spelled out for record:

- Daily recommendation cron 22:30 ET — **unchanged**
- Paper-trade cron 23:30 ET — **unchanged**
- T+1 next-bar fill `find_next_open()` — **unchanged**
- Snapshot-hash dedup `_find_existing_by_snapshot()` — **unchanged**
- Lookahead guard `ts < as_of` — **unchanged**
- Intraday shadow runs **only after** the existing tape poller
  succeeds (Phase 2+); writes are observational
- The Phase 4 UI line is rendered only when the read endpoint
  returns a non-null delta AND `INTRADAY_ML_SHADOW_UI_ENABLED=true`

**If a future Phase 5 proposes intraday-driven recommendation
refresh**, it must restart governance review covering:
- Updated `recommendation` table write path (currently sole writer
  is the EOD engine)
- New same-bar fill rule (does not exist today; would require
  explicit weakening of `find_next_open()`)
- Updated walk-forward (currently EOD-only)
- Explicit paper-only flag analog (`OPTIONS_PAPER_ONLY=true` pattern)

This proposal does **not** ask for any of that.

---

## 10. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Insufficient training data at Phase 3.** Phase 2 may need ≥ 60 trading days before model has anything to learn | §3 quantitative gates; backfill 60–120 days from Polygon at Phase 2 start |
| 2 | **Backfill quality drift.** Polygon's intraday history may have gaps or splits affecting old bars | Feature-hash dedup + per-day row count audit + warning if any day shows < 60% of expected row count |
| 3 | **Leakage via outcome join.** `RecommendationOutcome` arriving "in the future" from the observation's perspective | §5 hard rule 3: outcome joins filter `outcome.created_at > observed_at + horizon` |
| 4 | **Class imbalance (hold dominates)** | §5 soft rule 8: downsample hold to ≤ 50% during training |
| 5 | **Macro proxy bias** — model learns "SPY down = pick bad" | Per-symbol-relative features (`vs_macro_drift_pct`) + per-regime evaluation in §4 |
| 6 | **Calibration drift between refits** | ECE gate at promotion + weekly refit + monitoring of confidence-delta distribution |
| 7 | **Operator surprise** when display deltas contradict EOD recommendation | Phase 4 hover tooltip + microcopy: "shadow view, not advice" |
| 8 | **Cost creep** as symbol allow-list grows | Hard 100-symbol cap with truncation log + alert when cap hit |
| 9 | **Pressure to enable Phase 5 (rec refresh)** prematurely | Phase 5 requires fresh governance review; this doc closes off the path |
| 10 | **Backtest stagnation** — model never improves enough to promote | Acceptable outcome. Stay on EOD model. Phase 4 simply never flips. Zero operational cost (table writes only) |

---

## 11. Rollout plan — 5 phases

Each phase gated on the previous phase's exit criteria.

### Phase 1 — Architecture (this doc)
**Exit:** operator approves §"Validation gates" below.

### Phase 2 — Data collection (~4 h dev)
- Migration `068_intraday_observation.sql`
- New module `apps/api/src/ml/intraday/observation_writer.py`
  - `derive_observation(recommendation, snapshot, ...)` pure fn
  - `write_observation(session, obs)` UPSERT
- Hook into the existing `api/market.py:_poll_once` AFTER the
  successful tape refresh + AFTER `_refresh_overlay_cache`. One
  new call site, gated on `INTRADAY_ML_SHADOW_ENABLED`.
- One-off script `scripts/backfill_intraday_observations.py` for
  initial 60–120 day backfill (run once after Phase 2 ships)
- Unit tests: derive_observation, write idempotency
- Verification: 7 days of continuous writes + no duplicates +
  per-day row count audit passes
- **Exit:** 60+ trading days of continuous writes AND total labeled
  rows ≥ 5,000 (per §3 gates)

### Phase 3 — Shadow model (offline only, ~6 h dev)
- Migration `069_intraday_shadow_prediction.sql`
- New module `apps/api/src/ml/intraday/trainer.py`
  - Reuses `splits.py:walk_forward_splits()`
  - Reuses `evaluation.py:evaluate_walk_forward()`
- New module `apps/api/src/ml/intraday/scorer.py`
  - Writes `intraday_shadow_prediction` rows post-inference
- New module `apps/api/src/ml/intraday/labels.py`
  - Implements §2 labels using `RecommendationOutcome` joins
- Weekly Sunday refit cron (NEW `JobSchedule` row; first
  scheduler-config touch in this proposal — Phase 3 specifically;
  Phase 2 has no cron change)
- Operator review of first eval report
- **Exit:** model passes §4 metrics on held-out test folds

### Phase 4 — UI display (~2 h dev)
- Extend `IntradayContextLine` to render shadow delta clause
- New endpoint `/api/recommendations/{id}/intraday-shadow` reading
  `intraday_shadow_prediction` latest row
- Hover tooltip with disclosure microcopy
- Mobile + light/dark parity
- Feature flag `INTRADAY_ML_SHADOW_UI_ENABLED` (independent of the
  serving flag)
- **Exit:** operator confirms UI tone + accuracy after 1 week of
  display

### Phase 5 — Recommendation refresh proposal (deferred, no code)
- Architecture doc only at first
- Restarts governance review per §9 final clause
- Requires shadow model to materially beat baseline AND operator
  approval AND a new same-bar execution review
- **NOT auto-enabled by any Phase 1–4 progress**

---

## 12. Minimal first implementation (Phase 2 only)

Ships the data collection layer **without** any model code, scoring,
UI, or cron change. The smallest defensible cut:

1. Migration `068_intraday_observation.sql`
2. Config flag `INTRADAY_ML_SHADOW_ENABLED: bool = False`
3. `apps/api/src/ml/intraday/observation_writer.py` — pure
   `derive_observation()` + `write_observation()` upsert
4. Hook into `api/market.py:_poll_once` (one new call site, flag-gated)
5. One-off `scripts/backfill_intraday_observations.py` (60-day backfill)
6. Unit tests (derive idempotency, hash stability, label-join gate)
7. Operator runs backfill + verifies 7 days of continuous writes
8. **NO** trainer, **NO** scorer, **NO** UI, **NO** cron change,
   **NO** retraining

Phase 2 dev: ~4 h. Data accumulates while Phase 3 design proceeds.

---

## Validation gates before approval

1. Operator approves the §"Existing pipeline anchors" inheritance
   (reuse over rebuild).
2. Operator approves the feature set + label set (§1, §2).
3. Operator approves the §3 quantitative gates AS HARD blockers on
   Phase 3 — no waivers.
4. Operator approves the §4 promotion metrics + thresholds.
5. Operator approves the §6 storage shape — particularly the
   non-ephemerality decision (vs Phase 16's in-memory choice).
6. Operator acknowledges the §10 "model never promotes" risk as
   acceptable outcome.

---

## Sources

- ML pipeline audit findings, this document §"Existing pipeline anchors" (2026-05-12)
- `docs/research/MARKET_QUOTE_PROVIDER_EVAL.md`
- `docs/research/INTRADAY_CONTEXT_OVERLAY.md`
- `apps/api/src/ml/shadow/` — existing EOD shadow infrastructure
- `apps/api/src/ml/splits.py` — walk-forward purge+embargo
- `apps/api/src/ml/labels.py` — existing label generation
- `apps/api/src/governance/promotion_engine.py` — promotion gates
- `apps/api/src/domain/recommendations/recommendation_engine.py` — conviction + persist

---

*Document originated 2026-05-12 ~10:30 ET as Phase 1 architecture
proposal for an intraday ML shadow layer. NOT yet implemented.
Requires operator approval + per-phase validation gates.*
