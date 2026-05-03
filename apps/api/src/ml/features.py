"""Feature & label column policy.

Single source of truth for what belongs on each side of the train/label
boundary. Leakage guards consult this module to reject unexpected columns.

Rules:
  * IDENTITY_COLUMNS  — keys + timestamps; never trained on
  * FEATURE_COLUMNS   — strictly known at decision_ts
  * LABEL_COLUMNS     — strictly resolved after decision_ts
  * OUTCOME_FORBIDDEN_PATTERNS — substrings that must NOT appear in features
"""

from __future__ import annotations

# --- Identity / metadata (never train on these) -----------------------------

IDENTITY_COLUMNS = (
    "decision_id",
    "as_of_date",            # decision date (pd.Timestamp, tz-naive date)
    "decision_ts",            # full timestamp for leakage checks
    "instrument",
    "symbol",
    "engine",
    "decision_version",
)

# --- Features (known at decision time) --------------------------------------

# PD-5 — feature endogeneity audit. Features are now grouped so we can
# pick a TRAINING_FEATURE_WHITELIST that excludes recoded selector
# decisions (engine_is_*, regime_*, trade_policy_*, input_* booleans).

# Group 1 — selector/engine state. ENDOGENOUS to deterministic engines.
# Available in metadata for analysis but EXCLUDED from training.
FEATURES_ENGINE_STATE = (
    "engine_is_a", "engine_is_b", "engine_is_c",
    "regime_stress", "regime_directional", "regime_neutral",
    "gates_favorable",
    "trade_policy_neutral", "trade_policy_reduce",
    "trade_policy_confirm", "trade_policy_block",
    "trade_policy_watch",
    # Boolean recodings of selector gate inputs — endogenous.
    "input_rates_calm", "input_vrp_supportive",
    "input_credit_stable", "input_liquidity_expanding",
    "input_vol_elevated", "input_vol_expanding",
    "input_range_loose",
)

# Group 2 — data quality / portfolio risk. Useful covariates.
FEATURES_DATA_QUALITY = (
    "feature_confidence",
    "missing_field_count",
    "stale_field_count",
    "data_confidence_bucket",
)

# Group 3 — catalyst / event timing.
FEATURES_CATALYST = (
    "catalyst_score",
    "event_risk_score",
    "days_to_earnings",
    "has_earnings_soon",
)

# Group 4 — market-derived. Continuous, non-endogenous to selector.
# Already in inputs_used JSONB.
FEATURES_MARKET_LEGACY = (
    "input_z_score",
    "input_atr_ratio",
)

# Group 5 — PD-5 NEW non-endogenous market features. Computed in
# `dataset._derive_market_features()` from price bars. NaN when bars
# are insufficient (no fake values).
FEATURES_MARKET_NEW = (
    "ret_z_5d",          # 5-day TS-momentum z-score
    "ret_z_20d",         # 20-day TS-momentum z-score
    "ret_z_60d",         # 60-day TS-momentum z-score
    "rvol_20d",          # 20-day stdev of daily returns (annualized)
    "vol_of_vol_20d",    # rolling stdev of realized vol
    "log_atr_20d",       # log of 20-day ATR / close (range-vol proxy)
)

# Full feature column set — used by leakage guard + dataset builder.
FEATURE_COLUMNS = (
    *FEATURES_ENGINE_STATE,
    *FEATURES_DATA_QUALITY,
    *FEATURES_CATALYST,
    *FEATURES_MARKET_LEGACY,
    *FEATURES_MARKET_NEW,
)

# PD-5 — TRAINING WHITELIST. Excludes endogenous engine/regime/policy
# state. Keeps continuous market features + data-quality + catalyst.
# Shadow trainer should consume THIS, not FEATURE_COLUMNS.
TRAINING_FEATURE_WHITELIST = (
    *FEATURES_DATA_QUALITY,
    *FEATURES_CATALYST,
    *FEATURES_MARKET_LEGACY,
    *FEATURES_MARKET_NEW,
)

# Convenience map for the audit report.
FEATURE_GROUPS = {
    "engine_state":  FEATURES_ENGINE_STATE,
    "data_quality":  FEATURES_DATA_QUALITY,
    "catalyst":      FEATURES_CATALYST,
    "market_legacy": FEATURES_MARKET_LEGACY,
    "market_new":    FEATURES_MARKET_NEW,
}

# --- Labels (resolved strictly AFTER decision_ts) ---------------------------

LABEL_COLUMNS = (
    # Gross fixed-horizon labels (legacy)
    "fwd_ret_1d", "fwd_ret_3d", "fwd_ret_5d", "fwd_ret_10d",
    "label_win_1d", "label_win_3d", "label_win_5d", "label_win_10d",
    # PA-2 — net-of-cost variants
    "fwd_ret_net_1d", "fwd_ret_net_3d", "fwd_ret_net_5d", "fwd_ret_net_10d",
    "label_win_net_1d", "label_win_net_3d", "label_win_net_5d", "label_win_net_10d",
    # PC-4 — triple-barrier
    "label_tb_outcome", "label_tb_ret",
    "label_tb_hit_time", "label_tb_barrier_type",
    # Paper-trade realized outcomes
    "realized_net_ret", "realized_days_held",
    "realized_max_adverse", "realized_max_favorable",
    "hit_target", "hit_stop",
    "label_win_realized",
)

# --- Forbidden substrings inside feature columns ----------------------------
# Hard stop — if any feature column matches any of these, raise LeakageError.
OUTCOME_FORBIDDEN_PATTERNS = (
    "realized_",
    "fwd_ret_",
    "label_win",
    "hit_target",
    "hit_stop",
    "exit_",
    "max_adverse",
    "max_favorable",
    "pnl",
    "days_held",
    "close_after_",
    "outcome_",
)


def is_forbidden_feature_name(col: str) -> bool:
    """Return True if `col` matches any outcome/leakage pattern."""
    low = col.lower()
    return any(p in low for p in OUTCOME_FORBIDDEN_PATTERNS)
