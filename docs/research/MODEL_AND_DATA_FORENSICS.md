# MODEL AND DATA FORENSICS — Sprint 1

**Scope:** exact documentation of the existing model, feature, scoring, provenance, and data-ingestion system in ArthOS as of branch `feature/elite-arthos-provable-ideas` @ `5cdb099`.
**Method:** every claim below is read from source in this worktree and cited as `path :: symbol (line)`. Where something does not exist, that is stated explicitly.
**Author role:** Quant Research Lead + Data Quality Engineer (read-only forensics; no code changed).

---

## Executive summary of gaps

1. **No persisted LightGBM model artifact.** Training (`apps/ml/training.py::train_and_evaluate`) never calls `booster.save_model()`/pickle — it writes only a metrics JSON (`artifacts/ml_training_result.json`). The runtime shadow scorer (`apps/api/src/domain/ml/shadow_scorer.py`) **retrains from the DB on first call and caches in process memory only** (`_CACHED_MODEL`, line 42). Restart = new model.
2. **Model registry exists but is empty.** `models/model_registry.json` contains literally `[]` (4 bytes). Registry code (`apps/api/src/ml/model_registry.py`) is joblib-pickle based, sha256-checksummed, append-only — and its `ALLOWED_MODEL_TYPES = ("logreg", "gbm", "rf")` (line 27) does **not** include LightGBM (its "gbm" is sklearn `GradientBoostingClassifier` per `apps/api/src/ml/models.py`).
3. **No frozen feature schema for the LightGBM path.** Feature ordering = `NUMERIC_FEATURES` + whatever one-hot columns `pd.get_dummies` emits for the categories *present in the loaded data* (`apps/ml/dataset.py::_one_hot_encode`, lines 76–83). Data-dependent, unversioned.
4. **Train/inference missing-value mismatch.** Training feeds LightGBM `np.nan` (native NaN handling, `dataset.py:69`); the inference path zero-fills NaN and absent one-hot columns (`apps/api/src/domain/ml/shadow_scorer.py:117–120`).
5. **The LightGBM inference entry point is unwired.** `predict_proba_for_candidates` (`apps/api/src/domain/ml/shadow_scorer.py:98`) has **zero callers** anywhere in `apps/` or `scripts/` (repo-wide grep). It is dead code today.
6. **Training gate references a script that does not exist.** `apps/ml/training.py::require_edge_gate_open` (lines 76–90) demands `artifacts/ml_gate.json` with `status=OPEN`, telling the operator to run `python -m scripts.validate_edge` — **`scripts/validate_edge.py` is not in this tree** (only `training.py` references it; the other `ml_gate` grep hits are the unrelated ML-6 hybrid `ml_gated_count`). `artifacts/` itself does not exist in the repo.
7. **No commission/slippage on the main nightly paper path.** `submit_trade` treats `slippage_bps`/`commission` as informational attribution fields only (docstring, `paper_execution.py:259–261`); commission defaults to `Decimal("0")` (line 399). The nightly auto-trader (`auto_trader.py::execute_decisions`, lines 378–419) passes neither → raw next-bar-open fills at zero cost. Only the **weekly rebalance** path applies a deterministic cost model.
8. **Three different "confidence" derivations coexist**, with different label thresholds: stock-engine `50 + 50·|composite|` with Low<40/High>70 (`scoring.py:182–183`); recommendation-engine signal-agreement with High≥60/Medium≥30 (`recommendation_engine.py:205–210`); options per-rule constants with a shadow-only `confidence_v2`. Nothing reconciles them.
9. **Outcome labeling lags 30 days and has no explicit censored state.** Unlabeled rows are silently retried; "couldn't label" and "not yet due" are indistinguishable in the table (`score_outcomes.py`).
10. **`quote_age_seconds` is measured at ingest**, not at decision/read time (`options/data_provider/base_adapter.py:48–58`; acknowledged in `derived_confidence.py:176–177` "age measured at ingest"). Decision-time staleness is invisible.
11. **Three parallel ML stacks** with separate feature definitions and no shared schema: `apps/ml/` (LightGBM meta-label research), `apps/api/src/ml/` (Phase 11 sklearn shadow: registry/pickles/drift + ML-5/6 `shadow/` subpackage), `apps/api/src/domain/ml/` (in-process LightGBM shadow scorer + `historical_label` backfill).
12. **The only real model versioning in production rows is config-hash versioning of the deterministic engines** (`MODEL_VERSION = "stock_swing_v1:<sha256[:16] of config>"`) plus image-level `GIT_SHA` provenance. No trained-artifact version ever reaches a DB row.

---

## 1. LightGBM: version, type, entry points, artifacts, loading

**Package version.** `pyproject.toml:27` — `"lightgbm>=4.3.0"` (with `scikit-learn>=1.4.0`, line 28). `uv.lock` resolves **lightgbm 4.6.0** (`uv.lock:708–710`).

**Model type.** Binary **classifier** (meta-labeler over deterministic Buy decisions). `apps/ml/training.py::LGB_PARAMS` (lines 33–45): `objective: "binary"`, metrics `["auc","binary_logloss"]`, `num_leaves 31`, `max_depth 6`, `lr 0.05`, `feature_fraction 0.8`, `bagging 0.8/5`, `min_data_in_leaf 20`, `seed 42`. `NUM_BOOST_ROUND = 300`, `EARLY_STOPPING = 30` (lines 46–47). Not a regressor, not a ranker.

**Training entry points.**
- `python -m apps.ml.cli train` → `apps/ml/cli.py::_cmd_train` → `apps/ml/training.py::train_and_evaluate` (line 244). Flow: edge-gate check → `load_dataset()` → 80/20 date-based CV/lockbox split → 5-fold purged-embargoed-grouped CV (`apps/ml/splits.py::purged_embargoed_group_folds`) → OOF threshold sweep 0.10..0.60 step 0.02 with retention constraints (keep 40–80% of Buys, `training.py:49–54`) → full fit on CV → lockbox eval → shadow-ready gate (`sharpe_uplift ≥ 0.30`, `dd_delta ≥ −5.0`, `trade_reduction ≥ 0.20`, ≥100 lockbox trades, CV uplift ≥ 0; `decide_ready_for_shadow`, lines 204–236).
- Research variants: `apps/ml/e1_ablation.py` (risk-feature ablation, CV-only) and `apps/ml/phase2_pipeline.py` (alpha158-style features + asymmetric barrier + AFML bet sizing, shadow-only).
- Runtime shadow training: `apps/api/src/domain/ml/shadow_scorer.py::get_shadow_model` (lines 45–66) retrains LightGBM on the **full** `historical_label` window (no lockbox split) in-process, on demand.

**Inference entry points.**
- `apps/ml/training.py` — `model.predict(X_va, num_iteration=model.best_iteration)` (line 155, CV) and `full_model.predict(X_lock)` (line 324, lockbox). Research-time only.
- `apps/api/src/domain/ml/shadow_scorer.py::predict_proba_for_candidates` (line 98) — `model.booster.predict(X)` (line 121), returns `{asset_id: ml_proba}`. **No callers found anywhere** — verified by repo-wide grep. This is the intended production inference seam and it is currently dead.

**Artifact format + paths.**
- LightGBM: **no model file is ever written.** `train_and_evaluate` writes only `artifacts/ml_training_result.json` (metrics, threshold sweep, `feature_list`, feature importance; `ARTIFACTS_DIR`/`TRAIN_RESULT_PATH`, `training.py:62–64` and 383–405). The gate file `artifacts/ml_gate.json` is *read* (line 63, 76–90) but its producer (`scripts/validate_edge.py`) does not exist in this tree. `artifacts/` is absent from the repo (runtime-only, gitignored).
- sklearn (Phase 11S/11T path): joblib pickle **dict** with keys `model`, `preprocessor`, `feature_names`, `task`, `trained_on{train_median, train_scale, dataset_path, dataset_checksum_sha256}`, `model_version`, `label_version`, `dataset_version` (read in `apps/api/src/ml/model_registry.py::_read_pickle_metadata`, lines 128–147, and `apps/api/src/ml/shadow_scorer.py::run`, lines 341–350). Registered into `models/model_registry.json` (`REGISTRY_PATH`, `model_registry.py:24`; CLI `scripts/manage_model_registry.py`, append-only, requires `--commit --confirm-commit YES`). **The registry file currently contains `[]`.** No pickle files exist in the repo.
- Nothing model-related is stored in the DB. ML-6 hybrid predictions go to `ml_shadow_prediction` rows (predictions, not models; `apps/api/src/ml/shadow/scorer.py` docstring).

**How loaded.**
- LightGBM: never loaded from disk — retrained + cached in `_CACHED_MODEL` module global (`domain/ml/shadow_scorer.py:42–66`).
- sklearn: `apps/api/src/ml/shadow_scorer.py::run` (line 309): registry lookup by `model_id` → status must be `shadow_only` → sha256 checksum of pickle must match registration (lines 334–340, fail-loud on mismatch) → `joblib.load`.
- Paper-side ML advice: `apps/api/src/ml/shadow/runtime.py` loads the latest `ml_shadow_prediction` **row** (not a model) fail-soft; kill switch `ML_CAN_AFFECT_TRADES: bool = False` (`apps/api/src/config/__init__.py:78`; options twin `OPTIONS_ML_CAN_AFFECT_TRADES: bool = False`, line 235).

---

## 2. Feature pipeline

**LightGBM meta-label features — source of truth: `apps/ml/dataset.py`.**
- `NUMERIC_FEATURES` (lines 24–36), in order: `composite_score`, `confidence`, `residual_momentum_20d`, `residual_momentum_60d`, `sector_relative_rank`, `trend_strength_20d`, `price_vs_200sma`, `atr_percent_14`, `avg_dollar_volume_20d`, `realized_vol_20d`, `atr_pctile_1y`.
- `CATEGORICAL_FEATURES = ["market_trend", "vol_regime"]` (line 37), lower-cased with `"unknown"` fallback (lines 64–65), one-hot via `pd.get_dummies(prefix=cat, dummy_na=False)` (lines 76–83). **Final ordering = NUMERIC_FEATURES then dummy columns in category-discovery order — data-dependent, not frozen.** The trained feature list is echoed into `TrainingResult.feature_list` and the results JSON, but no schema version identifier exists.
- Target: `TARGET_COL = "y_hit"` = `(label == 1)` (lines 38, 72). Rows filtered to `action ∈ {"Buy"}` and `engine_version == MODEL_VERSION` (lines 94–107).
- Missing values: numeric feature `None` → `np.nan` (line 69) — LightGBM handles natively at train time.
- Inference alignment (`domain/ml/shadow_scorer.py::predict_proba_for_candidates`): builds rows from live `FactorSnapshot` + `RegimeSnapshot` via `_build_feature_row` (lines 69–95), one-hot by string interpolation (`market_trend_{trend}`), then aligns: missing model columns filled `0.0` and **`.fillna(0.0)` applied to everything** (lines 117–120). This differs from training (NaN) — a silent distribution shift for missing data.

**sklearn shadow-stack feature policy — `apps/api/src/ml/features.py`** (single source of truth for that stack, with leakage guard):
- `FEATURE_COLUMNS` = engine-state + data-quality + catalyst + market-legacy + market-new groups (lines 35–91).
- `TRAINING_FEATURE_WHITELIST` (lines 96–101) excludes the endogenous engine-state group (PD-5 endogeneity audit).
- Leakage guard: `OUTCOME_FORBIDDEN_PATTERNS` (lines 133–146) + `is_forbidden_feature_name` (line 149) — hard-stops `realized_`, `fwd_ret_`, `pnl`, etc. from feature names.
- 11T inference builds vectors from `paper_observation_label.gate_snapshot` JSONB; **any missing feature excludes the row** (`missing_features`) rather than imputing (`ml/shadow_scorer.py::_build_feature_vector`, lines 274–306).

**Feature-schema versioning.** Only the (unused) registry captures it: pickle `dataset_version` → registry `feature_schema_version` and `label_version` (`model_registry.py:194–195`), plus `feature_names` inside the pickle. The LightGBM path has **no** feature-schema versioning at all.

---

## 3. Scores: raw score vs probability; confidence_v2; confidence_label

**LightGBM output** is a probability (binary objective → `booster.predict` returns P(y_hit=1)); named `ml_proba` at the (dead) inference seam. Threshold selection happens in research (`best_threshold`, `training.py:311`), never in production.

**Deterministic stock engine** (`apps/api/src/domain/stock_engine/scoring.py`):
- `composite` = weighted sum of clamped factors, weights at lines 34–40 (**note:** actual `WEIGHTS` = rm60 .35 / rm20 .10 / sector .10 / trend .25 / vol .20 — the module docstring at lines 5–10 shows different numbers; the code is authoritative), plus anti-extension penalty when `price_vs_200sma > 0.15` (lines 56–58, 175–180).
- `confidence = 50 + 50·|composite|` (line 182); `confidence_label`: `"Low"` if <40, `"High"` if >70, else `"Medium"` (line 183). Action mapping Buy ≥ 0.25 / Hold ≥ −0.25 / Trim ≥ −0.65 / else Sell (`map_action`, lines 196–203).

**Recommendation engine** (`apps/api/src/domain/recommendations/recommendation_engine.py::_compute_confidence`, lines 163–211): confidence = fraction of non-zero weighted signals whose sign agrees with the composite, minus penalties `0.20` (not all families computable) and `0.30` (stale data), floored at 0, ×100. `confidence_label`: **High ≥ 60, Medium ≥ 30, else Low** (lines 205–210). This becomes `Recommendation.conviction` and `rationale.confidence_label`.

**Options `confidence_v2`** — exact math in `apps/api/src/options/strategy_candidates/derived_confidence.py::compute_confidence_v2` (line 181):

```
confidence_v2 = 0.35·delta_placement + 0.30·economics_quality
              + 0.20·signal_alignment + 0.15·freshness_quality      (weights, lines 47–50)

delta_placement   = min over short legs of clip01(1 − ||δ| − 0.30| / 0.15); missing → 0.40   (lines 89–108)
economics_quality = clip01((credit/width)/0.33); with POP: 0.5·that + 0.5·clip01((pop−0.50)/0.35); missing → 0.40  (lines 111–131)
signal_alignment  = 0.70 directional / 0.50 neutral, +0.10 if high-importance event in DTE window, cap 1.0  (lines 134–155)
freshness_quality = 1.0 at quote_age ≤ 60s, linear to 0.0 at 900s; missing → 0.50  (lines 158–178)
```

Shadow-only (`MODEL_TAG = "v2_shadow"`, line 65): written into `options_strategy_candidate.diagnostics` via `result.to_diagnostics()` at `apps/api/src/options/strategy_candidates/service.py:202–213`. The per-rule constant `confidence` remains authoritative (module docstring, lines 3–7). Deterministic, pure stdlib, replay-safe.

**11T shadow buckets** (not "confidence" but the third scoring tier): `BUCKET_EDGES_FROZEN = (0.33, 0.66)` low/mid/high (`apps/api/src/ml/shadow_scorer.py:34`, `assign_bucket` lines 122–132); regressions mapped through `frozen_sigmoid_v1.0.0` (lines 135–151).

---

## 4. Reasoning envelope (`apps/api/src/reasoning/`)

**What goes in.** `ReasoningEnvelope` (`envelope.py:81–114`): `skeleton_id`, `slot_fills` (slot → vocabulary canonical_name(s)), structured `InvalidationTrigger` (`condition_vocab` + `threshold`), `ThesisStatement` (`horizon` ∈ intraday/short_term/swing/position, `expected_signal` ∈ price_up/price_down/vol_expansion/vol_compression/range_hold; lines 35–49), `uncertainty_markers` (locked enum, `uncertainty_markers.py`), `generated_at`, `source` ∈ live/replay/backtest/operator_manual. Construction only via `build_envelope()` (line 165) — fail-loud validation of required slots, cardinality, unknown slots (`_validate_slot_fills`, lines 121–162). `envelope_hash()` = sha256 of canonical JSON (lines 94–114).

**Skeletons.** `skeletons.py::SkeletonId` (lines 24–31), six locked skeletons: `momentum_breakout`, `mean_reversion_pullback`, `breadth_thrust_entry`, `iv_compression_setup`, `catalyst_anticipation`, `regime_aligned_continuation`. Each `SkeletonSpec` carries slots (typed against `SlotVocabType` = signal/regime/strategy_family/invalidation_trigger) and a render `template`. Supporting modules: `generator.py` (`DecisionContext` → `generate_envelope_detailed`), `signal_extractor.py`, `skeleton_selector.py`, `marker_assigner.py`, `invalidation_populator.py`, `catalyst_substrate.py`, `renderer.py` (deterministic — "the renderer NEVER receives freeform prose"), `validators/forbidden_phrases_tier_a.json`.

**Storage.** `audit.py::record_envelope` (lines 20–70): raw-SQL INSERT into **`reasoning_audit`** (columns: `envelope_hash`, `skeleton_id`, `slot_fills_json`, `invalidation_json`, `thesis_json`, `uncertainty_markers`, `source`, `envelope_generated_at`, `paper_trade_id`), idempotent via `ON CONFLICT ON CONSTRAINT uq_reasoning_audit_envelope_hash_trade DO NOTHING`. Append-only by contract. **No ORM model exists in `db/models.py`** — raw SQL only.

**Linkage to trades.** `paper_trade_id` column on `reasoning_audit`. Wiring: `apps/worker/src/jobs/run_paper_trading.py:242–247` calls `generate_envelope_for_paper_trade(...)` then `record_envelope(...)`. Resolution logic in `worker_integration.py` (never raises; returns `(envelope|None, source_kind, reason)`): replay trades resolve `CandidateIdea.factor_breakdown/regime_snapshot`; live recommendation-sourced trades attempt `recommendation_bridge.assemble_features_from_recommendation`, but per the module docstring (lines 16–21) **live trades mostly get `None` envelopes today** because `Recommendation` rows don't carry the factor_breakdown + regime_snapshot bundle the generator needs — surfaced as `incomplete_lifecycle` ("honest absence").

---

## 5. Recommendation provenance

**Table `recommendation`** (`apps/api/src/db/models.py:306–333`): `id` (uuid str), `asset_id` FK, `generated_at` (tz-aware, default now), `action` (buy|sell|hold semantics; actual values Buy/Hold/Trim/Sell), `conviction` (0–100 numeric = engine confidence), `rationale` (Text — JSON blob), `model_version` (String 64), `snapshot_hash` (String 32; hash itself is 16 hex chars), `expires_at`, `created_at`. **Unique index `ux_recommendation_snap` on (asset_id, model_version, snapshot_hash)** — the idempotency key.

**Row production** — `apps/worker/src/jobs/registry.py::run_recommendations_for_all_accounts` (line 142): loads `load_engine_config()` once; universe = all `Asset.is_active` ∪ account's held assets (Lot join, lines 185–199); per account calls `run_for_account(session, account_id, config, asset_ids)` (`recommendation_engine.py:525`) and commits per account; per-account try/except. Idempotent via snapshot-hash dedup.

**Persist** — `recommendation_engine.py::persist` (line 394): `model_version = model_version_override or result.engine_version` (line 417; replay callers namespace as `"{engine}+replay:{label}"`, docstring lines 404–410, so replay rows never collide with live). Dedup lookup `_find_existing_by_snapshot` on the (asset_id, model_version, snapshot_hash) column (lines 385–391). `snapshot_hash = sha256(sorted-JSON of inputs)[:16]` (`_snapshot_hash`, lines 214–216). `rationale` JSON stores thesis, snapshot_hash, enough_data, stale_data, confidence_label, tags, composite_score, family_scores, and any policy adjustment block (original vs adjusted action/score/confidence, lines 428–450). Then: one `RecommendationEvidence` row per signal (`evidence_type=factor_key`, `source=family`, JSON summary, weight; lines 464–478) and a stub `RecommendationOutcome` with `price_at_recommendation` when current price known (lines 480–485).

**Model refs on the row:** only `model_version` (engine config-hash version) — **no trained-model artifact reference exists** (there is no artifact; see §1).

Cron context (from `apps/web/src/lib/picks/freshness.ts:193` comment): `run_recommendations_for_all_accounts` at `30 22 * * 1-5` (scheduler TZ).

---

## 6. Outcome labeling — `score_recommendation_outcomes`

Job: `apps/worker/src/jobs/score_outcomes.py::score_recommendation_outcomes` (line 134); registered in `registry.py:283`.

- **Eligibility:** joins `RecommendationOutcome ⋈ Recommendation` where `Recommendation.generated_at ≤ now − 30d` (`MIN_AGE_DAYS = 30`, line 32) **and** `RecommendationOutcome.barrier_label IS NULL` (lines 143–150).
- **Horizon:** evidence factor keys → `classify_signal_type` → `horizon_for_signal` (`apps/api/src/domain/recommendations/outcome_labeling.py:52, 72–78`): trend → **63 bars**, mean_reversion → **10 bars**, default → **30 bars** (constants lines 36–38).
- **Labeling:** σ_t0 from 20-bar pre-entry window (`compute_sigma_t0`; requires ≥30 bars of series, `score_outcomes.py:87`); triple barrier at **PT = 2.0σ, SL = 2.0σ** (`PT_SIGMAS`/`SL_SIGMAS`, lines 34–35) via `triple_barrier_label` over daily `PriceBar` (adjusted_close preferred, lines 63–64). Writes `barrier_label`, `barrier_first_touch_at`, `barrier_n_bars`, `signal_type`, `price_at_recommendation` (if absent), `price_after_30d/90d` + `realized_30d/90d_return`, and pre-entry-only regime tags `trend_regime`/`volatility_regime`/`drawdown_regime` (`classify_all`, no lookahead; lines 109–129).
- **Resolved vs unresolved/censored:** resolved = `barrier_label` non-NULL. `score_one_outcome` returns False (row stays NULL, retried next run) when: `generated_at` missing; < 30 bars of history; σ invalid; or `triple_barrier_label` returns None (insufficient forward bars — i.e., **censored rows are indistinguishable from not-yet-due rows**; there is no explicit censoring flag).
- **Tables:** `recommendation_outcome` (`models.py:363–393`, one-to-one with recommendation, `barrier_label` Integer, timestamps).
- **Distinct labeling systems (do not conflate):** (a) `historical_label` (`models.py:865–915`, unique on as_of_date+asset_id+engine_version) — the LightGBM training set, backfilled by `apps/api/src/domain/ml/backfill_service.py` with its own triple barrier: `n_bars = 20` fixed, PT/SL = entry·(1 ± 2·realized_vol_20d·√(n/252)) (module docstring). (b) `paper_observation_label` — forward-return labels for paper observations, written by operator CLI `scripts/run_paper_labeller.py` (Phase 11P.5, append-only, `--commit --confirm-commit YES`), consumed by the 11T shadow scorer and `scripts/build_ml_dataset.py`.

---

## 7. Ingestion paths (prices/quotes)

**Daily stock prices** — job `ingest_prices_daily` (`apps/worker/src/jobs/ingest_prices_daily.py`): provider chain **Tiingo (if `TIINGO_API_KEY`) → Yahoo** (`_provider_chain`, lines 16–30). **Polygon is deliberately excluded from the daily chain** — its raw bars carry `adjusted_close=None` and first-non-empty semantics would degrade the live total-return series (comment lines 24–29). Orchestrator: `apps/api/src/domain/prices/service.py::ingest_symbols` — incremental start-date with 5-bar buffer, fetch from chain **until first non-empty**, normalize → validate → dedupe, per-bar source-priority upsert into `price_bar` (module docstring lines 1–9). Providers live in `apps/api/src/domain/prices/providers/{base,tiingo,yahoo,polygon}.py`.

**Backfills:**
- `backfill_prices` (`apps/worker/src/jobs/backfill_prices.py`) — 2 years, all active assets + SPY, Tiingo → Yahoo, `incremental=False`.
- `backfill_gap_history` (`apps/worker/src/jobs/backfill_gap_history.py`, BP28) — deep-history gap fill from `2022-01-01`, chain **Polygon(raw) → Tiingo → Yahoo**, dry-run default, JSON checkpoint, batch progress; build-only, never scheduled (docstring).
- `tiingo_backfill_eod` (`registry.py:50–134`) — legacy Tiingo-only, 1y, hardcoded 10-symbol `_UNIVERSE`, upsert `on_conflict_do_nothing(constraint="uq_price_bar")`, provider column `"tiingo"`.
- Legacy/aux adapters: `apps/api/src/providers/{tiingo,polygon,benzinga,sec_edgar,firecrawl_summarizer}.py` (Polygon also powers `refresh_company_names`). yfinance is used directly by research scripts (e.g. `run_phase12_price_action.py` for ES=F) and regime gate data.

**Options chains** — job `options_chain_snapshot` (`apps/worker/src/jobs/options_chain_snapshot.py`) → `apps/api/src/options/data/chain_ingest.py`: INSERT into `options_chain_snapshot` with `quote_age_seconds, provider, provider_version` (`_INSERT_SQL`, ~lines 86–102), `ON CONFLICT ... DO NOTHING` on the natural key; liquidity-profile filtering with reject counts; adapters `tradier/finnhub/thetadata` under `apps/api/src/options/data_provider/`.

**Where quote_age/staleness is computed:**
- `quote_age_seconds` is computed **by the adapter at ingest time** and stored on the snapshot row (`base_adapter.py:48–58`, clamped at 0 for clock skew; a provider-timestamp variant is preferred when present). Every downstream reader (e.g. `confidence_v2.freshness_quality`) therefore sees age-at-ingest, explicitly labeled "age measured at ingest" (`derived_confidence.py:176–177`). Decision-time staleness is not recomputed.
- Stock-side staleness: `recommendation_engine.py::_is_stale` (lines 141–160), `STALE_DAYS = 5` (line 43), replay-correct via `as_of` reference; feeds the 0.30 confidence penalty.

---

## 8. Existing evaluation scripts

| Path | What it does |
|---|---|
| `apps/api/src/domain/backtest/walk_forward.py` | Walk-forward IS/OOS audit over `Recommendation.generated_at` timeline; WFE metric = expectancy (mean realized return/rec); Decimal-only, no model training. Tests: `apps/api/tests/unit/test_walk_forward.py`, `integration/test_walk_forward_pg.py`. |
| `apps/api/src/backtest/replay_driver.py` | BACKTEST-PAPER-5 single-day real-paper-parity replay: live engine `compute_for_asset(as_of=T)` → `persist(generated_at=T, version+replay-namespace)` → `submit_trade(submitted_at=end-of-T)` next-bar fill. |
| `scripts/replay_paper_history.py` | 11Z incident replay of paper-trading rows from recovered upstream data; safe wrapper around `run_paper_daily`; operator-only, never scheduled. |
| `scripts/replay_paper_execution_chain.py` | 11Z replay of the account→recommendation→run_paper_trading→submit_trade execution chain. |
| `apps/ml/training.py` / `apps/ml/e1_ablation.py` / `apps/ml/phase2_pipeline.py` | LightGBM meta-label training + gate; E1 risk-feature ablation (CV-only decision gate); Phase 2 alpha158 + asymmetric-barrier + AFML sizing + fresh-forward validation (shadow-only). |
| `apps/ml/splits.py` | `purged_embargoed_group_folds` — purged/embargoed grouped CV. |
| `scripts/run_phase12_price_action.py` | Phase 12 compression/breakout framework, ES=F (yfinance) + SPY, variants A–E, deterministic. |
| `scripts/run_phase15_mean_reversion.py` | Phase 15 long-only mean-reversion edge model; next-bar-open entry, exits 1/3/5/10/20 bars; **costs modeled 10 bps + 20 bps round-trip** (research only). |
| `scripts/run_phase20_regime_gated.py` | Phase 20 regime-gated mean reversion; four PIT-clean FRED/yfinance gates (rates/VRP/credit/liquidity). |
| `scripts/run_shadow_scoring.py` | Phase 11T manual shadow scoring CLI over `paper_observation_label` (pickle-registry path); dry-run default; JSON report under `reports/`. |
| `scripts/run_model_drift_report.py` | Phase 11U.4 drift report CLI (read-only, exit-coded). |
| `scripts/compare_label_versions.py`, `scripts/diff_shadow_vs_scheduler.py`, `scripts/_audit_filter_calibration.py`, `scripts/run_turnover_report.py` | Label-version comparison, shadow-vs-scheduler divergence, filter calibration audit, turnover diagnostics. |
| `apps/api/src/ml/replay/` (`replayer.py`, `validation_harness.py`, `leakage.py`, `point_in_time.py`, `comparator.py`) | PIT replay + leakage validation harness for the sklearn shadow stack. |
| `scripts/build_ml_dataset.py` | 11Z read-only JSONL dataset builder (paper trades ⋈ provenance ⋈ outcomes); asserts `ML_CAN_AFFECT_TRADES` is False; date-split leakage rule. |
| Options: `scripts/run_options_paper_eval.py`, `run_options_promotion_eval.py`, `run_options_shadow_eval.py`, `compute_options_strategy_outcomes.py`; `apps/api/src/options/paper/eval_runner.py` | Options paper eval / promotion-gate eval / shadow eval / strategy outcome computation. |
| Alpha-investigation memory (BP8–BP27B) lives under `docs/research/` (e.g. `quant-repos-extraction*.md`, `OUTCOME_LABELING_READINESS.md`). | Context docs, not runnable. |

---

## 9. Paper execution: fills, commission, slippage

**Fill rule** — `apps/api/src/domain/paper_trading/paper_execution.py::find_next_open` (lines 135–161): first `price_bar` with `timeframe='1d'` and `ts > after_ts`, fill price = that bar's **OPEN** (fallback `close` if open NULL). Returns None (→ `PaperTradeRejected("no price bar available after submitted_at")`, line 280) when no future bar exists — this is the next-bar, no-lookahead guarantee.

**`submit_trade`** (line 235): exactly one of `quantity`/`usd_amount`; portfolio/asset existence checks; qty from `usd_amount / fill_price`; buy path enforces cash buffer (`_cash_buffer_pct`, line 36) and min notional (`_min_notional_usd`, line 49) with `shrink_to_cash` (line 62); sell computes `realized_pnl`; MP1S provenance stamps `opened_by_recommendation_id`/`opening_trade_id` on `paper_position` (`models.py:445–469`). `fill_price_override` substitutes the price but the timestamp still comes from `find_next_open` (docstring lines 255–258).

**Commission/slippage modeling:**
- In `submit_trade` itself: **none.** `slippage_bps` and `commission` are stored on the trade row "for attribution; they are informational only (already baked into `fill_price_override`)" (docstring lines 259–261); commission defaults `Decimal("0")` (line 399).
- Nightly account path (`run_paper_trading` → `auto_trader.py::execute_decisions`, lines 378–419): `submit_trade` called **without** slippage/commission/override → raw next-open fill, zero cost. Same for the exit cycle (`scripts/run_paper_exit_cycle.py:283`).
- Weekly rebalance path only: `apps/api/src/domain/stock_engine/portfolio/rebalance_engine.py:255–256, 312–313` passes `fill_price_override=cost.fill_price` + `slippage_bps` from the deterministic cost model `apps/api/src/domain/stock_engine/portfolio/cost_model.py`: `spread_bps_proxy = 10000·(H−L)/C/4`, `impact_bps = 10000·notional/max(adv20·10, 1)`, `slippage_bps = max(2.0, 0.5·(spread+impact))`, `commission = 0` ("stated default") (docstring lines 1–21).
- Research-side cost models exist separately (`apps/api/src/domain/evaluation/costs.py` — commission_bps + slippage_bps round-trip; Phase-15 script hardcodes 10+20 bps) but none of these touch the nightly executed paper P&L.

**Net: the canonical nightly paper track records zero-cost next-bar-open fills.**

---

## 10. Model version + feature-schema provenance today

What exists:
- **Engine config-hash version:** `MODEL_VERSION = f"{ENGINE_NAME}:{ENGINE_CONFIG_HASH}"` where `ENGINE_CONFIG_HASH = sha256(sorted-JSON of weights/thresholds/gate-set/transform/penalty consts)[:16]` (`scoring.py:61–78`; `ENGINE_NAME="stock_swing_v1"`, `GATE_SET_VERSION`, `SCORE_TRANSFORM_VERSION` lines 49–51). Keys `historical_label.engine_version` and the LightGBM dataset filter.
- **Recommendation rows:** `model_version` + `snapshot_hash` unique triple (§5); replay namespace override.
- **Options:** `proposal_hash` String(64) on canary positions (`apps/api/src/db/options_models.py:248–250`, widened 32→64 in migration 093); `options_paper_trade.strategy_version` (Text, NOT NULL, `options_models.py:230`) and `strategy_candidate_id` (line 259, migration 099) close the candidate→trade attribution loop.
- **Image provenance:** `apps/api/src/build_provenance.py` — `GIT_SHA`/`GIT_BRANCH`/`GIT_DIRTY` baked at Docker build (P0-4, after two image/code-drift incidents).
- **Registry (dormant):** `registry_version="registry-v1.0.0"`, sha256 artifact + dataset checksums, `label_version`, `feature_schema_version`, immutable append-only entries (`model_registry.py`) — **zero entries**.
- **Envelope hash:** sha256 audit key for reasoning artifacts (§4).

What does **not** exist:
- No versioning of any trained LightGBM model (no artifact at all).
- No feature-schema version for the production feature vector (ordering is data-dependent, §2).
- No DB linkage from any prediction/recommendation row to a trained-model artifact or checksum.
- No `MLflow`/DVC/experiment tracker of any kind.

---

## FACTS-FOR-NEXT-SPRINTS

- **LightGBM version:** `lightgbm>=4.3.0` (`pyproject.toml:27`), locked **4.6.0** (`uv.lock:708`). Binary classifier (meta-labeler), params `apps/ml/training.py::LGB_PARAMS` (lines 33–47), seed 42.
- **Model artifact path(s):** **NONE for LightGBM** — nothing persisted; runtime model is retrained+cached in `apps/api/src/domain/ml/shadow_scorer.py::get_shadow_model` (`_CACHED_MODEL`, lines 42–66). Training writes metrics-only `artifacts/ml_training_result.json` and reads gate `artifacts/ml_gate.json` (`apps/ml/training.py:62–64`); gate producer `scripts/validate_edge.py` **does not exist**. Dormant sklearn registry: `models/model_registry.json` (currently `[]`), loader `apps/api/src/ml/model_registry.py` (`REGISTRY_PATH` line 24), checksum-verified joblib load in `apps/api/src/ml/shadow_scorer.py::run` (lines 319–350).
- **Predict call sites:** `apps/api/src/domain/ml/shadow_scorer.py::predict_proba_for_candidates` line 98 (`booster.predict` line 121) — **zero callers (dead seam)**; research-time predicts at `apps/ml/training.py:155` (CV) and `:324` (lockbox); sklearn shadow predicts in `apps/api/src/ml/shadow_scorer.py::score_features_classification/_regression` (lines 194–228); ML-6 hybrid predictions persist to `ml_shadow_prediction` via `apps/api/src/ml/shadow/scorer.py`. Kill switch `ML_CAN_AFFECT_TRADES=False` (`apps/api/src/config/__init__.py:78`).
- **Feature list location:** `apps/ml/dataset.py::NUMERIC_FEATURES` (lines 24–36) + `CATEGORICAL_FEATURES` (line 37), one-hot in `_one_hot_encode` (lines 76–83; ordering data-dependent, unversioned); target `y_hit` (line 38). Sklearn-stack policy + leakage guard: `apps/api/src/ml/features.py` (`TRAINING_FEATURE_WHITELIST` lines 96–101, `OUTCOME_FORBIDDEN_PATTERNS` lines 133–146). Inference NaN→0.0 mismatch at `domain/ml/shadow_scorer.py:117–120`.
- **confidence_v2 formula location:** `apps/api/src/options/strategy_candidates/derived_confidence.py::compute_confidence_v2` (line 181; weights 0.35/0.30/0.20/0.15 at lines 47–50; component funcs lines 89–178); stamped shadow-only into `options_strategy_candidate.diagnostics` at `apps/api/src/options/strategy_candidates/service.py:202–213` (`MODEL_TAG="v2_shadow"`). Stock confidence labels: `scoring.py:182–183` (50+50|c|; Low<40/High>70) and `recommendation_engine.py::_compute_confidence` lines 163–211 (agreement-based; High≥60/Medium≥30).
- **Outcomes table + resolved criteria:** `recommendation_outcome` (`apps/api/src/db/models.py:363–393`); resolved ⇔ `barrier_label IS NOT NULL`; labeled by `apps/worker/src/jobs/score_outcomes.py::score_recommendation_outcomes` (line 134) for recs `generated_at ≤ now−30d` (`MIN_AGE_DAYS=30`); horizons 63/10/30 bars by signal type (`outcome_labeling.py:36–38,72–78`); barriers ±2.0σ (`score_outcomes.py:34–35`); no censored flag (NULL rows retried forever). Training labels: `historical_label` (`models.py:865`, unique as_of_date+asset_id+engine_version) written by `apps/api/src/domain/ml/backfill_service.py` (n_bars=20, ±2·rv20·√(n/252)). Paper labels: `paper_observation_label` via `scripts/run_paper_labeller.py`.
- **Recommendation count query hints:** table `recommendation`, dedup key unique index `ux_recommendation_snap (asset_id, model_version, snapshot_hash)` (`models.py:327–333`); `model_version = engine_version` (replay rows namespaced `"{engine}+replay:{label}"` — exclude with `model_version NOT LIKE '%+replay:%'`); per-asset-latest pattern in `recommendation_engine.py::list_latest_per_asset` (lines 492–517); producer job `run_recommendations_for_all_accounts` (`apps/worker/src/jobs/registry.py:142`, cron ~`30 22 * * 1-5`); evidence in `recommendation_evidence` (evidence_type=factor_key), stub outcome row created at persist (`recommendation_engine.py:480–485`).
- **Paper fill rule:** `paper_execution.py::find_next_open` (lines 135–161) — first 1d bar strictly after `submitted_at`, fill at OPEN; `submit_trade` line 235; **no commission/slippage on the nightly path** (auto_trader `execute_decisions` lines 378–419 passes none; commission default 0 at line 399); cost model only on weekly rebalance (`rebalance_engine.py:255–256,312–313` + `cost_model.py`: max(2bps, 0.5·(spread/4 + impact)), commission=0).
- **Versioning that exists:** engine config hash `MODEL_VERSION` (`scoring.py:61–78`), `snapshot_hash` (`recommendation_engine.py:214–216`), options `proposal_hash` (64-char, `options_models.py:250`) + `strategy_version`/`strategy_candidate_id` (`options_models.py:230,259`), image `GIT_SHA/GIT_BRANCH/GIT_DIRTY` (`apps/api/src/build_provenance.py`), envelope sha256 (`envelope.py:94–114`). **No trained-artifact versioning anywhere in the live path.**
