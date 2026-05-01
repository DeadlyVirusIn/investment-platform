"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/investment"
    FERNET_KEY: str = ""          # base64-urlsafe 32-byte key; required for secret encryption
    TIINGO_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "0.1.0"

    # ML SIZING FEATURE FLAG (V1 promotion gate)
    # When True: target_weights <- ML-sized weights; deterministic path kept in shadow_weights for parallel log
    # When False: target_weights <- deterministic weights; ML-sized path in shadow_weights
    # Instant rollback: set env ENABLE_ML_SIZING=0 and restart (or toggle at request boundary)
    ENABLE_ML_SIZING: bool = False

    # Monitoring thresholds (bp = basis points)
    ML_ALERT_SHARPE_DELTA_BP: float = -5.0
    ML_ALERT_SHARPE_CONSEC_DAYS: int = 3
    ML_ALERT_DD_EXCESS_PCT: float = 1.0

    # Phase 3 confidence calibration (Controlled Adaptation v1)
    # Default OFF — system must behave identically when disabled.
    ENABLE_CONFIDENCE_CALIBRATION: bool = False
    CALIBRATION_MIN_SAMPLES: int = 20
    CALIBRATION_DRIFT_THRESHOLD: float = 0.15
    CALIBRATION_FACTOR_MIN: float = 0.8
    CALIBRATION_FACTOR_MAX: float = 1.2
    CALIBRATION_EXPECTED_BASELINE: float = 0.5

    # Phase 4 safe integration.
    # Shadow: calibration runs + logs but does NOT affect downstream usage.
    # Default True — explicit operator toggle required to leave shadow.
    CALIBRATION_SHADOW_MODE: bool = True

    # Global impact limiter — scales all factors toward 1.0 if batch avg
    # |adj - orig| exceeds this. Prevents large system-wide shifts.
    CALIBRATION_MAX_AVG_SHIFT: float = 0.05

    # ------------------------------------------------------------------
    # Phase reliability + catalyst layer
    # ------------------------------------------------------------------
    # Free-tier providers come first; paid providers plug in via priority.
    FINNHUB_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    FMP_API_KEY: str = ""                     # future $20/mo upgrade slot
    EODHD_API_KEY: str = ""                   # future $20/mo upgrade slot
    # Comma-separated priority orders (reload on app restart)
    CATALYST_PROVIDER_PRIORITY: str = "finnhub,yahoo"
    DATA_PROVIDER_PRIORITY: str = "yahoo,finnhub,alpha_vantage"
    # Staleness tolerance (days) for daily bars — feed into FallbackChain
    DATA_MAX_AGE_DAYS: int = 3
    # Catalyst windows
    CATALYST_BLOCK_WINDOW_DAYS: int = 2
    CATALYST_REDUCE_WINDOW_DAYS: int = 5

    # ------------------------------------------------------------------
    # Phase ML-1 research foundation
    # ------------------------------------------------------------------
    # Expose ML research endpoints + UI panel.
    ML_ADVISORY_ENABLED: bool = True
    # Allow ML output to affect paper/live execution. OFF until walk-forward
    # proves the model beats baselines and Engine C is explicitly promoted.
    ML_CAN_AFFECT_TRADES: bool = False
    # Minimum labelled decisions before training is attempted at all.
    ML_MIN_TRAINING_ROWS: int = 1000

    # ------------------------------------------------------------------
    # Phase ML-2 — passive data accumulation
    # ------------------------------------------------------------------
    # Keep every nightly snapshot for now. Retention pruning comes later.
    ML_SNAPSHOT_RETENTION_DAYS: int = 365
    # Minimum per-bucket sample size for pattern discovery to produce
    # non-low-confidence results.
    ML_PATTERN_MIN_SAMPLE: int = 30
    # Turn decision-log advisory annotation on/off without code change.
    ML_ANNOTATE_DECISIONS: bool = True

    # ------------------------------------------------------------------
    # Phase ML-2.5 — safe historical replay
    # ------------------------------------------------------------------
    # Default universe used when API caller doesn't pass one.
    ML_REPLAY_UNIVERSE: str = (
        "AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA,SPY,QQQ"
    )
    ML_REPLAY_START_DATE: str = ""
    ML_REPLAY_END_DATE: str = ""
    ML_REPLAY_MAX_SYMBOLS: int = 50
    # When True, dataset builder pulls replay rows too (default OFF — real
    # paper-trade rows are always the trust anchor).
    ML_DATASET_INCLUDE_REPLAY: bool = False
    # Sample weight applied to replay rows when combined with real rows.
    ML_REPLAY_WEIGHT: float = 0.25

    # ------------------------------------------------------------------
    # Phase ML-2.6 — catalyst backfill
    # ------------------------------------------------------------------
    CATALYST_BACKFILL_PROVIDER_PRIORITY: str = "finnhub,yahoo,alpha_vantage"
    CATALYST_BACKFILL_START_DATE: str = ""
    CATALYST_BACKFILL_END_DATE:   str = ""
    CATALYST_BACKFILL_MAX_SYMBOLS: int = 50
    CATALYST_BACKFILL_WINDOW_DAYS: int = 30
    CATALYST_BACKFILL_RATE_LIMIT_PER_MIN: int = 60
    CATALYST_BACKFILL_DRY_RUN_DEFAULT: bool = True

    # ------------------------------------------------------------------
    # Phase ML-3 — passive shadow ML
    # ------------------------------------------------------------------
    ML_SHADOW_ENABLED: bool = True
    ML_SHADOW_MIN_ROWS: int = 1000
    # PA-2 — default ML label is now NET-OF-COST. Switch back to
    # `label_win_5d` only for diagnostic gross comparisons.
    ML_SHADOW_LABEL: str = "label_win_net_5d"
    ML_SHADOW_HORIZON: int = 5
    ML_SHADOW_MODEL_TYPES: str = "logistic,ridge,rf"
    ML_SHADOW_MAX_MODEL_CONFIGS: int = 10
    ML_SHADOW_REQUIRE_BASELINE_BEAT: bool = True

    # ------------------------------------------------------------------
    # Phase SYSTEM-ALPHA
    # ------------------------------------------------------------------
    PAPER_SLIPPAGE_BPS: float = 5.0
    PAPER_APPLY_SLIPPAGE_ANALYTICS: bool = True
    PAPER_APPLY_SLIPPAGE_EXECUTION: bool = False
    SYSTEM_ALPHA_FACTOR_VERSION: str = "factor-v1.0.0"
    SYSTEM_ALPHA_FEATURE_SET_VERSION: str = "alpha-v1.0.0"

    # ------------------------------------------------------------------
    # Phase SYSTEM-ALPHA-4 — rule enforcement
    # ------------------------------------------------------------------
    ALPHA_RULES_ENABLED: bool = True
    ALPHA_RULES_MODE: str = "advisory"        # advisory|paper_reduce|paper_filter
    ALPHA_RULE_ALLOW_BLOCK: bool = False
    ALPHA_RULE_MIN_SIZE_MULTIPLIER: float = 0.50
    ALPHA_RULE_CACHE_SECONDS: int = 60
    ALPHA_RULE_REQUIRE_AUDIT: bool = True
    ALPHA_RULE_AUTO_PAUSE: bool = False
    ALPHA_RULE_ROLLBACK_HIT_RATE_DROP: float = 0.10
    ALPHA_RULE_ROLLBACK_RETURN_DROP: float = -0.01
    ALPHA_RULE_ROLLBACK_TRADE_COUNT_DROP: float = 0.50
    ALPHA_RULE_REFRESH_COOLDOWN_HOURS: int = 24
    ALPHA_RULE_DEDUPE_DAYS: int = 7

    # ------------------------------------------------------------------
    # Gate / paper exploratory mode
    # ------------------------------------------------------------------
    PAPER_GATE_MODE: str = "strict"       # strict | exploratory
    PAPER_EXPLORATORY_MIN_GATES: int = 2
    PAPER_EXPLORATORY_SIZE_MULTIPLIER: float = 0.25
    PAPER_EXPLORATORY_REQUIRE_LOW_RISK: bool = True
    PAPER_EXPLORATORY_BLOCK_ON_ANOMALY: bool = True
    PAPER_EXPLORATORY_TAG: bool = True

    # ------------------------------------------------------------------
    # Phase ML-5 — Gated Hybrid Advisor
    # ------------------------------------------------------------------
    # All defaults OFF. ML can ONLY reduce paper size when enabled, never
    # increase, never block execution unless ALLOW_BLOCK=true. Toggling
    # these does not change real-money behavior.
    ML_HYBRID_ENABLED: bool = False
    # "advisory"      → compute + log only, multiplier stays 1.0
    # "paper_reduce"  → apply reduction multiplier to paper size
    ML_HYBRID_MODE: str = "advisory"
    ML_HYBRID_MIN_CONFIDENCE: float = 0.65
    ML_HYBRID_REQUIRE_CALIBRATION: bool = True
    ML_HYBRID_REQUIRE_BASELINE_BEAT: bool = True
    ML_HYBRID_MAX_STALE_DAYS: int = 7
    ML_HYBRID_MIN_DATA_CONFIDENCE: float = 0.70
    ML_HYBRID_ALLOW_BLOCK: bool = False
    ML_HYBRID_MIN_MULTIPLIER: float = 0.50

    # ------------------------------------------------------------------
    # Phase ML-6 — Hybrid Performance Monitor + Promotion Guard
    # ------------------------------------------------------------------
    # Promotion thresholds. Guard only RECOMMENDS — never flips mode.
    ML_PROMOTION_MIN_ADVICE: int = 20
    ML_PROMOTION_MIN_OUTCOMES: int = 20
    ML_PROMOTION_MAX_ECE: float = 0.10
    ML_PROMOTION_MIN_DELTA_SHARPE: float = 0.00
    ML_PROMOTION_MAX_FALSE_AVOID_RATE: float = 0.35
    ML_PROMOTION_REQUIRED_HEALTHY_DAYS: int = 7
    ML_PROMOTION_REQUIRE_OPERATOR_APPROVAL: bool = True
    # Missed-winner upper bound — soft cap; used as reporting signal only.
    ML_PROMOTION_MAX_MISSED_WINNER_RATE: float = 0.50

    # ------------------------------------------------------------------
    # Phase ENGINE-B-MIGRATION — controlled rollout state machine
    # ------------------------------------------------------------------
    # Allowed values: LEGACY | SHADOW_COMPARE | PARTIAL_B2_25 |
    # PARTIAL_B2_50 | PARTIAL_B2_75 | FULL_B2.
    # NOTE: ONLY mode != LEGACY produces any execution change. LEGACY +
    # SHADOW_COMPARE are both LEGACY-equivalent for execution; SHADOW
    # only adds extra logging.
    ENGINE_B_MODE: str = "LEGACY"
    # Minimum days of SHADOW_COMPARE required before ADVANCE may be
    # recommended by promotion gate.
    ENGINE_B_MIN_SHADOW_DAYS: int = 60
    # Sharpe-collapse trigger — if rolling 30d Sharpe of currently-routed
    # signal falls below this, kill switch RECOMMENDS revert.
    ENGINE_B_KILL_SHARPE: float = -1.0
    # Drawdown-breach trigger — if rolling 60d max-DD on routed signal
    # exceeds this magnitude (negative percent), recommend revert.
    ENGINE_B_KILL_DD_PCT: float = -15.0
    # Operator approval flag — must be flipped externally before ADVANCE
    # is allowed to recommend a state change.
    ENGINE_B_OPERATOR_APPROVAL: bool = False

    # ------------------------------------------------------------------
    # OPTIONS SYSTEM (Phase 11B — schema only; no business logic yet)
    # ------------------------------------------------------------------
    # Master enable. Even when True, no live execution is wired in v1.
    OPTIONS_ENABLED: bool = False
    # PERMANENT v1 KILL SWITCH. Mirrors ML_CAN_AFFECT_TRADES discipline.
    # Setting to False would require a new design phase + explicit
    # operator approval. v1 has NO live execution path.
    OPTIONS_PAPER_ONLY: bool = True
    # PERMANENT v1 KILL SWITCH. Options ML output never reaches the
    # paper-trade-decision path; this flag enforces that contractually.
    # Setting to True would require a new design phase + explicit
    # operator approval.
    OPTIONS_ML_CAN_AFFECT_TRADES: bool = False
    # Provider adapter selector; v1 = ThetaData. v2 may add Polygon /
    # ORATS via separate adapters.
    OPTIONS_DATA_PROVIDER: str = "thetadata"
    # Snapshot cadence (frozen v1).
    OPTIONS_SNAPSHOT_INTERVAL_MINUTES: int = 15
    # Default fill model. Alternative: "mid_minus_one_tick".
    OPTIONS_DEFAULT_FILL_MODEL: str = "mid_plus_25_pct_spread"

    # ------------------------------------------------------------------
    # THETADATA PROVIDER (Phase 11O.1 — manual ingest wiring)
    # All keys optional at the Settings level; the adapter validates
    # them at construction time only when OPTIONS_DATA_PROVIDER is
    # "thetadata" AND the adapter is actually used. Permanent v1
    # behaviour: nothing here flips OPTIONS_ENABLED or removes any
    # kill-switch; these knobs only configure the read-only data path.
    # ------------------------------------------------------------------
    THETADATA_BASE_URL: str | None = None
    THETADATA_API_KEY: str | None = None
    THETADATA_USERNAME: str | None = None
    THETADATA_PASSWORD: str | None = None
    THETADATA_TIMEOUT_SECONDS: int = 30
    THETADATA_MAX_RETRIES: int = 2
    THETADATA_RATE_LIMIT_QPS: float = 5.0

    # ------------------------------------------------------------------
    # FRED PROVIDER (Phase 11P.2 — manual macro backfill)
    # Optional. Required only when running scripts/backfill_macro_features.py
    # against the FRED feed. Pure read. Never affects live execution.
    # ------------------------------------------------------------------
    FRED_API_KEY: str | None = None
    FRED_BASE_URL: str = "https://api.stlouisfed.org/fred"
    FRED_TIMEOUT_SECONDS: int = 30
    FRED_MAX_RETRIES: int = 3
    FRED_RATE_LIMIT_QPS: float = 1.0

    # ------------------------------------------------------------------
    # EQUITY EXPLORATORY PAPER MODE (Phase 11P.3 — operator opt-in)
    # When False, the exploratory runner refuses to commit even when
    # invoked manually with --commit. When True, the runner is enabled
    # but still respects --dry-run / --commit + confirm gates. Default
    # FALSE; flipping is operator-explicit and reversible.
    # ------------------------------------------------------------------
    EQUITY_EXPLORATORY_ENABLED: bool = False

    # ------------------------------------------------------------------
    # PHASE 11W (Phase B) — Research Intelligence + Audit Layer
    # ------------------------------------------------------------------
    # PERMANENT default OFF in production. When False, the read-only
    # /api/research/* router is NOT mounted (routes 404). Phase B ships
    # only schema + GET-only stubs + feature-flagged UI shell. Flipping
    # to True is permitted in dev/test only; production flip is a
    # later-phase decision gated by its own audit + operator approval.
    RESEARCH_RO_ENABLED: bool = False


settings = Settings()
