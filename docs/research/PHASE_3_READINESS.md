# Phase 3 Readiness — Collection + Observation Phase

> **Status (2026-05-12):** Phase 2 collection ACTIVE. Phase 3
> trainer / scorer / promotion logic NOT built. This document is the
> only Phase 3-related deliverable until calendar gate trips
> (~2026-07-28). It defines what "dataset is healthy" means in
> measurable terms so the operator + future trainer don't act on
> assumptions.
>
> **Hard rules (still enforced):**
> - No trainer / scorer / promotion logic
> - No intraday recommendation refresh
> - No intraday trades
> - No confidence mutations
> - No sizing changes
> - No additional overlay UI
> - No realtime notifications
> - No hidden notebooks, side trainers, or "just testing" XGBoost runs

---

## 1. Phase 3 readiness checklist (master gate review)

The four hard gates from `docs/research/INTRADAY_ML_SHADOW.md` §3,
restated as actionable check-list items. Phase 3 trainer code does
NOT land until **all** gates pass + each section's probe verifies clean.

| # | Gate | Threshold | Probe | Owner |
|---|---|---|---|---|
| G1 | Calendar coverage | ≥ 60 trading days | §4 dataset-quality | calendar-bound |
| G2 | Labeled rows | ≥ 5,000 | §4 dataset-quality | data-bound |
| G3 | Distinct symbols with ≥ 30 days coverage | ≥ 20 | §5 symbol-distribution | data-bound |
| G4 | `adverse_threshold_breached` positive class share | ≥ 5% | §7 class-imbalance | data-bound |
| G5 | Walk-forward purge+embargo audit | 0 overlapping timestamps | §3 walk-forward | enforced at trainer-time |

**Soft gates (audited; warnings, not blockers):**

| # | Soft gate | Threshold | Action on miss |
|---|---|---|---|
| S1 | No single symbol > 15% of training rows | enforce in trainer | downsample at fold construction |
| S2 | Each `time_of_day_bucket` ≥ 200 rows | document | warn in eval report |
| S3 | Hold-action share ≤ 50% post-downsample | enforce in trainer | downsample to 50% |
| S4 | Per-regime row count ≥ 100 each | document | per-regime breakdown only |

**Decision points:**

- All hard gates pass → Phase 3 architecture review begins (separate doc, not this one)
- Any hard gate misses → stay in collection phase; revisit weekly
- Soft-gate misses → Phase 3 trainer ships with mitigation per the table above

---

## 2. Leakage audit checklist

Per arch doc §5. **Each rule has an active probe operator can run
during collection.** Failing any probe = halt before Phase 3 trainer.

### Hard rules (programmatic enforcement at trainer-time)

| # | Rule | Probe (read-only SQL) | Pass criterion |
|---|---|---|---|
| L1 | Observation timestamp gate | `SELECT COUNT(*) FROM intraday_observation WHERE quote_ts > observed_at_15min;` | **0** rows |
| L2 | EOD label timestamp gate | When labels join lands: `SELECT COUNT(*) FROM intraday_observation o JOIN price_bar p ON p.asset_id = (SELECT asset_id FROM recommendation WHERE id=o.recommendation_id) WHERE p.timeframe='1d' AND p.ts <= DATE_TRUNC('day', o.observed_at_15min) + INTERVAL '1 day';` | **0** EOD-bar joins occurring on the same trading day as the observation |
| L3 | Outcome join gate | Future `RecommendationOutcome` joins MUST filter `outcome.created_at > observed_at_15min + label_horizon_days` | trainer responsibility — assert in fold builder |
| L4 | Walk-forward purge | 5-day purge between train + val, 2-day embargo | trainer responsibility — assert per-fold |
| L5 | No future feature engineering | `atr_60d_pct` / `vol_60d_pct` MUST use bars where `ts < DATE_TRUNC('day', observed_at_15min)` | trainer responsibility — log feature-input window per fold |

### Soft rules (audited; warnings)

| # | Rule | Probe | Threshold |
|---|---|---|---|
| L6 | Symbol imbalance | `SELECT symbol, COUNT(*) AS n FROM intraday_observation GROUP BY symbol ORDER BY n DESC LIMIT 5;` | top symbol < 15% of total |
| L7 | Time-of-day balance | `SELECT time_of_day_bucket, COUNT(*) FROM intraday_observation GROUP BY 1;` | each bucket ≥ 200 |
| L8 | Action-type balance | `SELECT action_type, COUNT(*) FROM intraday_observation GROUP BY 1;` | hold ≤ 50% post-downsample |

### Re-validation cadence

- Every Sunday during collection: operator runs §2 probes; results recorded in `docs/research/observation_log/` with date stamp.
- On every 1,000-row milestone: §4 probes auto-checkable via `/api/intraday-shadow/health` Phase 3 progress block.

---

## 3. Walk-forward validation plan

**Inherits proven config from `apps/api/src/ml/splits.py:64-150`.**
The intraday shadow trainer reuses `walk_forward_splits()` UNCHANGED
when Phase 3 lands. This section documents the chosen parameters so
the operator + future trainer share assumptions.

### Window configuration

| Parameter | Value | Rationale |
|---|---|---|
| Train window | 30 trading days | One regime month |
| Validation window | 5 trading days | Tight model selection signal |
| Test window | 5 trading days (held out) | Promotion gate score |
| **Purge** | 5 trading days | Same as EOD model; AFML Ch.7 default |
| **Embargo** | 2 trading days | Same as EOD model |
| Refit cadence | non-rolling, one fit per fold | Computational tractability + EOD parity |
| Min folds | 4 | At 60-day total dataset: floor of (60−40)/5 + 1 = 5 folds |

### Per-fold assertions (trainer must enforce)

1. `train.observed_at_15min.max() < val.observed_at_15min.min() − 5 trading days` (purge)
2. `val.observed_at_15min.max() < test.observed_at_15min.min() − 2 trading days` (embargo)
3. No `recommendation_id` appears in both train AND val/test of the same fold (cross-fold leakage check)
4. No symbol's last train observation > 15 minutes after symbol's first val observation (intra-symbol time leak)
5. Each fold's train set must have ≥ 1,000 rows AND val ≥ 200 rows AND test ≥ 200 rows

### Walk-forward dry-run probe (run pre-trainer)

When the 60-day gate trips, the operator runs ONE pre-trainer SQL probe to confirm split feasibility:

```sql
WITH bounds AS (
  SELECT
    MIN(observed_at_15min) AS min_ts,
    MAX(observed_at_15min) AS max_ts,
    COUNT(DISTINCT DATE(observed_at_15min)) AS n_days
  FROM intraday_observation
)
SELECT
  min_ts, max_ts, n_days,
  FLOOR((n_days - 40) / 5.0) + 1 AS expected_n_folds
FROM bounds;
```

Pass criterion: `expected_n_folds >= 4`.

### Validation metrics (per arch doc §4)

| Metric | Threshold | How computed |
|---|---|---|
| AUC vs EOD baseline | ≥ +0.02 | held-out test fold ROC AUC, compared to `RecommendationOutcome.barrier_label` baseline alone |
| ECE (Expected Calibration Error) | ≤ 0.10 | 10-bin reliability diagram |
| Sharpe delta on shadow-suggested portfolio | ≥ 0.0 | back-test over test window using shadow's confidence_delta as a sizing hint vs the held-out baseline |
| False-stress rate | ≤ 0.30 | (count(label=stress AND outcome=neutral)) / (count(label=stress)) |
| Min labeled outcomes per regime bucket | ≥ 100 | join to `RecommendationOutcome.{trend,volatility,drawdown}_regime` |

---

## 4. Dataset quality metrics

Quantitative health of the collection layer. **Probe weekly during
collection; results recorded in observation log.**

### Core counts

```sql
-- Lifetime + today + last-7d snapshot
SELECT
  COUNT(*)                                                     AS lifetime_rows,
  COUNT(DISTINCT symbol)                                       AS distinct_symbols,
  COUNT(DISTINCT recommendation_id)                            AS distinct_recs,
  COUNT(DISTINCT DATE(observed_at_15min))                      AS distinct_days,
  MIN(observed_at_15min)                                       AS first_obs,
  MAX(observed_at_15min)                                       AS last_obs,
  COUNT(*) FILTER (WHERE observed_at_15min > NOW() - INTERVAL '7 days')  AS rows_last_7d,
  COUNT(*) FILTER (WHERE observed_at_15min > NOW() - INTERVAL '1 day')   AS rows_last_24h
FROM intraday_observation;
```

### Daily ingestion rate (sanity)

```sql
SELECT
  DATE(observed_at_15min) AS day,
  COUNT(*) AS rows,
  COUNT(DISTINCT symbol) AS symbols,
  COUNT(DISTINCT observed_at_15min) AS slots
FROM intraday_observation
GROUP BY 1
ORDER BY 1 DESC
LIMIT 14;
```

**Healthy pattern:** RTH days show ~6,000–10,000 rows × 100 symbols × ~64 slots. Days with materially less = upstream gap.

### Schema integrity

- Every row has `recommendation_id`, `symbol`, `observed_at_15min`, `feature_hash`, `source`, `delay_minutes` (all NOT NULL by schema; verify zero rows have empty string)
- `feature_hash` cardinality should equal row count (each cycle's hash differs because price moves)

### Phase 3 progress (auto-tracked by `/api/intraday-shadow/health`)

| Metric | Current | Target | % |
|---|---|---|---|
| `lifetime_rows` | (live) | 5,000 | (live) |
| `lifetime_distinct_symbols` | (live) | 20 | (live) |
| `distinct_dates` | (live) | 60 | (live) |

Operator polls `GET /api/intraday-shadow/health` for live values; the response's `phase_3_progress` block carries the same fields.

---

## 5. Symbol-distribution metrics

Catches three failure modes:
- **Concentration risk** — single symbol > 15% of training rows (model overfits to one regime)
- **Long-tail starvation** — sparse symbols accumulate too few rows for cross-validation
- **Symbol churn** — frequent membership rotation in the resolver's ACTIVE_RECS pool

### Per-symbol coverage

```sql
SELECT
  symbol,
  COUNT(*)                                            AS rows,
  COUNT(DISTINCT DATE(observed_at_15min))             AS days_covered,
  MIN(observed_at_15min)                              AS first_seen,
  MAX(observed_at_15min)                              AS last_seen,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total
FROM intraday_observation
GROUP BY symbol
ORDER BY rows DESC;
```

**Pass criteria for Phase 3:**
- Top symbol's `pct_of_total` ≤ 15.0
- ≥ 20 symbols have `days_covered ≥ 30`
- No symbol with `last_seen > NOW() - INTERVAL '14 days'` AND `rows < 5` (starved active rec — drops out before contributing)

### Symbol turnover audit

```sql
-- How many distinct symbols entered/exited the active set per day
WITH per_day AS (
  SELECT
    DATE(observed_at_15min) AS day,
    array_agg(DISTINCT symbol ORDER BY symbol) AS syms
  FROM intraday_observation
  WHERE observed_at_15min > NOW() - INTERVAL '14 days'
  GROUP BY 1
)
SELECT day, array_length(syms, 1) AS distinct_today
FROM per_day ORDER BY day DESC;
```

**Healthy:** distinct count stable around the 100-symbol cap. Wild swings = resolver churn.

---

## 6. Regime-balance metrics

Phase 3 evaluation is gated on `min ≥ 100 labeled outcomes per regime bucket` (§4). During collection we cannot compute outcome-regime joins (they depend on `RecommendationOutcome` rows that arrive at T+1/T+30/T+90), but we CAN audit the **input regime distribution** from the recommendation side.

### Input-regime breakdown (from recommendation_outcome where available)

```sql
-- Joins observations to their rec's outcome regimes when scored.
SELECT
  ro.trend_regime,
  ro.volatility_regime,
  ro.drawdown_regime,
  COUNT(*) AS observations
FROM intraday_observation o
JOIN recommendation r       ON r.id = o.recommendation_id
LEFT JOIN recommendation_outcome ro ON ro.recommendation_id = r.id
GROUP BY 1, 2, 3
ORDER BY 4 DESC;
```

**Healthy pattern (Phase 3 ready):** every (trend × volatility × drawdown) bucket appearing in production should have ≥ 100 observation rows in the dataset. Buckets with < 100 → trainer must either down-weight the loss for that bucket or warn that conclusions don't generalize there.

### Time-of-day distribution (proxy for intraday regime)

```sql
SELECT
  time_of_day_bucket,
  COUNT(*) AS rows,
  COUNT(DISTINCT symbol) AS symbols,
  COUNT(DISTINCT DATE(observed_at_15min)) AS days
FROM intraday_observation
GROUP BY 1
ORDER BY rows DESC;
```

**Pass criterion:** every bucket (`premarket`, `open30`, `morning`, `midday`, `afternoon`, `close30`, `afterhours`) has ≥ 200 rows. `off` (weekend / overnight) is exempt.

---

## 7. Class-imbalance monitoring

The training labels (per arch doc §2) are computed at trainer-time
from joined `RecommendationOutcome` data. Pre-Phase-3, we can audit
the **input action-type balance** which drives the eventual label
distribution.

### Action-type distribution (rolling)

```sql
SELECT
  action_type,
  COUNT(*) AS rows,
  COUNT(DISTINCT symbol) AS distinct_symbols,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM intraday_observation
GROUP BY 1
ORDER BY rows DESC;
```

**Healthy at Phase 3 entry:**
- `hold` rows ≤ 50% (downsample to this in trainer if higher)
- `buy` rows ≥ 20%
- `trim` rows ≥ 15%
- `sell` rows present (currently zero — recommendation engine emits no sells; document the gap)

### Position-state distribution

```sql
SELECT
  position_state,
  COUNT(*) AS rows,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM intraday_observation
GROUP BY 1
ORDER BY rows DESC;
```

**Expected:** `open_long` dominant (since resolver favors holdings), `flat` non-trivial (active recs without holdings), `open_short` zero (system is long-only).

### Forward-projection: post-label class share

When `RecommendationOutcome` is joined at trainer-time, the actual labels we'll have:

| Label | Estimated positive class share | Source |
|---|---|---|
| `eod_favorable_today` | ~50–60% (binary; depends on market direction) | EOD return sign |
| `adverse_threshold_breached` | **target ≥ 5%** | rolling daily max |
| `outcome_improved_t1` (3-class) | ~33% each ideally | T+1 outcome diff |
| `stress_predicted_bad_followthrough` | ~5–10% | conditional |
| `windfall_predicted_trim_opportunity` | ~5–10% | conditional |

**Phase 3 hard gate G4:** `adverse_threshold_breached` positive share ≥ 5%. Below 5% → labels too rare to learn.

---

## 8. Missing-data / sparsity monitoring

Catches:
- Polygon outage windows (rows with NULL `intraday_change_pct`)
- Symbols pre-market only / post-market only (limited bucket coverage)
- `vs_macro_drift_pct` NULL when SPY missing for that slot
- Backfill gaps if backfill is re-run with different cuts

### Per-feature null counts

```sql
SELECT
  COUNT(*) FILTER (WHERE intraday_change_pct IS NULL)         AS null_intraday_change,
  COUNT(*) FILTER (WHERE vs_open_pct IS NULL)                 AS null_vs_open,
  COUNT(*) FILTER (WHERE vs_recommendation_entry_pct IS NULL) AS null_vs_entry,
  COUNT(*) FILTER (WHERE vs_macro_drift_pct IS NULL)          AS null_vs_macro,
  COUNT(*) FILTER (WHERE intraday_range_pct IS NULL)          AS null_range,
  COUNT(*) FILTER (WHERE atr_60d_pct IS NULL)                 AS null_atr,
  COUNT(*) FILTER (WHERE vol_60d_pct IS NULL)                 AS null_vol,
  COUNT(*) FILTER (WHERE sector_id IS NULL)                   AS null_sector,
  COUNT(*) AS total_rows
FROM intraday_observation;
```

**Expected at Phase 2 v1 (current scope):**
- `null_atr / null_vol / null_sector = total_rows` (deferred to Phase 3 prep — current writer hard-codes NULL)
- `null_intraday_change` ≤ 1% (only when `prev_close` missing)
- `null_vs_macro` ≤ 5% (when SPY missing for the slot)

### Sparse-day flag

```sql
-- Days where total row count is < 30% of the median (likely upstream gap)
WITH per_day AS (
  SELECT DATE(observed_at_15min) AS day, COUNT(*) AS rows
  FROM intraday_observation GROUP BY 1
),
median AS (
  SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY rows) AS med
  FROM per_day
)
SELECT pd.day, pd.rows, m.med
FROM per_day pd, median m
WHERE pd.rows < 0.3 * m.med
ORDER BY pd.day;
```

**Pass criterion:** zero sparse days inside the Phase 3 training window. Sparse days inside backfill = exclude from training.

### Symbol coverage matrix (heatmap-equivalent SQL)

```sql
-- One row per (symbol, day): how many slots got an observation
SELECT
  symbol,
  DATE(observed_at_15min) AS day,
  COUNT(DISTINCT observed_at_15min) AS slots_filled
FROM intraday_observation
WHERE observed_at_15min > NOW() - INTERVAL '14 days'
GROUP BY 1, 2
ORDER BY 1, 2;
```

**Healthy:** RTH days show ~26 slots filled per active symbol (16h × 4 slots/h × ~40% upstream-availability = ~26). Days with < 10 slots filled = drop from training.

### Backfill-vs-live coverage gap

```sql
-- For each symbol, identify whether coverage is "backfill" or "live"
-- (live = observed within 90s of slot boundary; backfill = older than 90s)
SELECT
  symbol,
  COUNT(*) FILTER (WHERE created_at - observed_at_15min < INTERVAL '5 minutes') AS live_rows,
  COUNT(*) FILTER (WHERE created_at - observed_at_15min > INTERVAL '5 minutes') AS backfill_rows,
  COUNT(*) AS total
FROM intraday_observation
GROUP BY symbol
ORDER BY total DESC;
```

**Healthy:** every symbol has BOTH live + backfill rows (live indicates active resolver; backfill indicates historical context). All-backfill = symbol fell out of resolver. All-live = recently added; lacks history.

---

## 9. Feature-drift monitoring proposal

Catches:
- Distributional shift between backfill window + live window
- Sudden regime change (vol spike, sector rotation) that invalidates model assumptions
- Schema/data-source drift (Polygon endpoint format changes silently)

Phase 3 trainer will compute these per fold; for now (collection
phase) we monitor weekly.

### Feature-distribution snapshot

```sql
-- Quartile spread of each numeric feature, for rows in the last 7 days
-- vs rows older than 7 days (drift signal = quartile divergence)
WITH recent AS (
  SELECT * FROM intraday_observation
  WHERE observed_at_15min > NOW() - INTERVAL '7 days'
),
old AS (
  SELECT * FROM intraday_observation
  WHERE observed_at_15min <= NOW() - INTERVAL '7 days'
)
SELECT
  'intraday_change_pct' AS feat,
  (SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY intraday_change_pct) FROM recent) AS q1_recent,
  (SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY intraday_change_pct) FROM recent) AS q3_recent,
  (SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY intraday_change_pct) FROM old)    AS q1_old,
  (SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY intraday_change_pct) FROM old)    AS q3_old
UNION ALL
SELECT
  'vs_macro_drift_pct',
  (SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY vs_macro_drift_pct) FROM recent),
  (SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY vs_macro_drift_pct) FROM recent),
  (SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY vs_macro_drift_pct) FROM old),
  (SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY vs_macro_drift_pct) FROM old);
```

**Drift signal:** `|q1_recent - q1_old| / |q1_old| > 0.5` (50% quartile shift) → regime change worth noting in observation log.

### Schema-drift sentinel

Each cycle's `feature_hash` is computed from the full feature dict.
If Polygon ever changes its response shape (e.g. adds a field, drops
a field), the derived features stay numerically identical (same
`(price, prev_close, ...)` inputs) → hash distribution unchanged.

```sql
-- Hash collision audit (expected = 0; non-zero = derivation function bug)
SELECT feature_hash, COUNT(*) AS cnt
FROM intraday_observation
GROUP BY 1
HAVING COUNT(*) > 1
LIMIT 10;
```

**Pass criterion:** zero collisions. (Backfill + live for the same `(rec_id, slot)` collide via UPSERT, not via duplicate hash rows — the UNIQUE constraint catches the slot conflict.)

### Source-attribution audit

```sql
SELECT source, delay_minutes, COUNT(*) AS rows, MIN(created_at), MAX(created_at)
FROM intraday_observation
GROUP BY 1, 2
ORDER BY rows DESC;
```

**Expected:** every row has `source='polygon'` and `delay_minutes=15`. Any other value = misconfiguration or accidental fallback (HALT before Phase 3).

### Drift-monitoring cadence proposal

| Cadence | Action | Owner |
|---|---|---|
| Weekly (Sunday) | Run §9 quartile probe; record in `docs/research/observation_log/YYYY-MM-DD.md` | operator |
| On 1,000-row milestone | Auto-run via /api/intraday-shadow/health phase_3_progress | endpoint |
| On Polygon outage detected (`tape.last_error` non-null) | Spot-check next 24h of writes for nullness in §8 | operator |
| Pre-Phase-3 trainer | Re-run §9 + §8 + §6 in trainer notebook (when Phase 3 lands) | trainer |

---

## 10. Data freeze rule

When Phase 3 trainer experimentation begins, the dataset window
under experiment becomes **immutable for the duration of the
experiment**. This is a discipline rule, not a code mechanism;
violations invalidate the experiment.

### What "frozen" means

For the explicit (start_ts, end_ts) window an experiment trains on:

- **No retroactive resolver-rule changes inside the window.** If the
  resolver is updated mid-experiment (e.g. cap raised from 100 → 150,
  conviction threshold lowered from 60 → 55, ACTIVE_RECS window
  changed from 7d → 14d) the experiment must NOT pull rows written
  after the rule change. Either re-train against a fresh frozen
  window OR pin the experiment to rows whose `created_at < rule_change_ts`.
- **No silent backfill-rule changes.** If `LEAKAGE_CUT_DAYS` changes
  in `scripts/backfill_intraday_observations.py` and a backfill is
  rerun, the backfill-attributable rows in the frozen window are
  newly different. Treat as a rule change → bump version (§11).
- **No feature-definition drift without version bump.** If
  `derive_observation()` changes any computation (threshold, formula,
  field semantics), bump the feature schema version (§11) BEFORE
  applying the change. Old experiments stay valid against the old
  version; new experiments start clean.
- **No deletes inside the window.** Rows in `intraday_observation`
  inside (start_ts, end_ts) MUST NOT be deleted or rewritten. The
  365d retention prune (when it ships) MUST honor active-experiment
  freeze windows OR reject prune attempts that intersect them.

### Goal

Trainer experiments must be **reproducible**. Two trainer runs over
the same frozen window with the same configuration must produce
byte-identical training data + byte-identical eval scores. Failure
of this property = invalidate both runs.

### Enforcement (Phase 3 trainer responsibility)

- Trainer reads the resolver-config + feature-schema version
  metadata (§11) at the start of each run and persists it to the
  model registry alongside `model_version`.
- Trainer asserts the (start_ts, end_ts) window is fully covered by
  rows tagged with the SAME (resolver_version, feature_schema_version)
  and refuses to train across version boundaries.
- The model registry's append-only contract (`apps/api/src/ml/model_registry.py:24-26`)
  carries the freeze metadata; reproducibility is auditable per row.

---

## 11. Feature + collection versioning

Metadata schema for the future trainer + collection layer. **No code
yet — this section reserves the field shape so Phase 3 trainer can
read consistent metadata once it lands.**

### Required versioning fields (per trainer run)

Every Phase 3 trainer run MUST persist (alongside `model_version` in
the model registry) the following snapshot of how the dataset was
produced:

| Field | Source today | Example value | Notes |
|---|---|---|---|
| `resolver_config_version` | hash of `resolve_active_overlay_targets()` source + cap + conviction-threshold + recency-window constants | `"v1.2-cap100-conv60-7d"` | Bump on resolver code change |
| `feature_schema_version` | hash of `derive_observation()` signature + threshold constants + bucket boundary table | `"v1.0-15min-7buckets"` | Bump on derivation change |
| `leakage_rule_version` | combined version stamp for §2 hard rules + LEAKAGE_CUT_DAYS in backfill script | `"v1.0-purge5-embargo2-cut7"` | Bump on any §2 change |
| `collection_window_start_ts` | min observed_at_15min in training set | `"2026-05-12T08:00:00Z"` | UTC |
| `collection_window_end_ts` | max observed_at_15min in training set | `"2026-07-28T20:00:00Z"` | UTC; experiment freeze boundary |
| `polygon_source_assumptions` | dict snapshot of Polygon endpoint + tier + delay | `{"endpoint":"v2/snapshot","tier":"stocks_starter","delay_min":15}` | Detect tier upgrades / endpoint deprecations |
| `cap_config` | OVERLAY_SYMBOL_CAP value at training time | `100` | Bump if cap changes |
| `conviction_threshold` | `>= 60` floor used by ACTIVE_RECS resolver | `60` | Bump if threshold changes |

### Where this metadata lives

- **Today (collection phase):** the fields above are NOT persisted
  per row. Resolver/feature/leakage versions are derivable from
  `git log` of `apps/api/src/api/market.py`,
  `apps/api/src/ml/intraday/observation_writer.py`, and
  `scripts/backfill_intraday_observations.py`. Operator can hand-tag
  the observation log per weekly probe.
- **Phase 3 trainer:** loads the eight fields above and writes them
  into `models/model_registry.json` (append-only) alongside
  `model_version`. Each model artifact is then auditable for
  exactly which dataset definition produced it.
- **Schema-drift sentinel (§9):** `feature_hash` already gives
  per-row drift detection. Adding a `feature_schema_version` column
  to `intraday_observation` is a Phase 3-prep migration (NOT THIS
  PHASE) that would let the trainer query
  `WHERE feature_schema_version = ?` directly.

### Bump policy (forward declaration)

When ANY of these change, the relevant version string bumps and
new rows tag at the new version:

| Change | Version bumps |
|---|---|
| Resolver cap, conviction floor, recency window, source-set order | `resolver_config_version` |
| New feature, removed feature, threshold value, bucket boundary | `feature_schema_version` |
| `LEAKAGE_CUT_DAYS`, purge or embargo days, label horizon | `leakage_rule_version` |
| Polygon endpoint, tier, batch shape, delay assumption | `polygon_source_assumptions` |
| `OVERLAY_SYMBOL_CAP` | `cap_config` |
| Conviction threshold | `conviction_threshold` |

Trainer experiments crossing any version boundary must be re-run on
a single-version subset OR explicitly re-validated against the new
version's data with a fresh experiment framing.

### Pre-Phase-3 todo (NOT implemented yet)

- [ ] Add `feature_schema_version` + `resolver_config_version` columns
      to `intraday_observation` (Phase 3-prep migration)
- [ ] Persist current version constants in `apps/api/src/ml/intraday/`
      module-level for hash derivation
- [ ] Trainer reads + asserts version uniformity per fold
- [ ] Model registry stores all 8 fields per artifact

These are pre-trainer prep items, not Phase 3 trainer code itself.
None ship until the §1 hard gates trip.

---

## Appendix A — Observation log template

Place files at `docs/research/observation_log/YYYY-MM-DD.md`. One per
weekly probe run. Suggested template:

```markdown
# Observation log — YYYY-MM-DD

## Phase 3 progress
- lifetime_rows: __
- distinct_symbols: __
- distinct_dates: __

## Probes run this week
- §2 leakage L1–L8: pass / fail (notes)
- §4 dataset quality: pass / fail (notes)
- §5 symbol distribution: top symbol pct=__ ; sparse_n=__
- §6 regime balance: time-of-day buckets met=__/8
- §7 class imbalance: hold_pct=__ ; sell_pct=__
- §8 sparsity: null_intraday=__ ; null_macro=__ ; sparse_days=__
- §9 drift: q1_change_pct shift=__%

## Anomalies
- __
- __

## Decisions
- __
```

---

## Appendix B — What this document does NOT do

Explicit non-scope, to keep the discipline locks visible:

- ❌ Does NOT design the Phase 3 trainer
- ❌ Does NOT propose model architectures (XGBoost, MLP, etc.)
- ❌ Does NOT specify feature engineering beyond what already exists in `IntradayObservation` schema
- ❌ Does NOT define the promotion-gate verdict format (lives in
  `apps/api/src/governance/promotion_engine.py`)
- ❌ Does NOT touch the EOD model
- ❌ Does NOT add UI surfaces beyond the existing Ops badge
- ❌ Does NOT add new endpoints
- ❌ Does NOT add new cron jobs
- ❌ Does NOT add new Polygon calls

Phase 3 trainer architecture proposal is a SEPARATE document, gated
on this document's checklist passing. That document does not exist
yet and will not be written until the calendar gate trips.

---

*Document originated 2026-05-12 ~16:00 ET as Phase 16 collection-
+-observation phase deliverable. Collection continues at 100 symbols
× 90s cadence. No code lands from this document.*
