"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/investment"
    FERNET_KEY: str = ""          # base64-urlsafe 32-byte key; required for secret encryption
    TIINGO_API_KEY: str = ""
    POLYGON_API_KEY: str = ""     # paid Massive/Polygon — primary historical daily source
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "0.1.0"
    # Owner/admin allowlist (Admin-1). Comma-separated emails, case-insensitive.
    # Source of truth for the owner guard — no DB role column. Empty = no owner
    # (admin surface denied to everyone).
    ARTHOS_OWNER_EMAILS: str = ""

    # Canonical stock practice portfolio (Phase A — single source of truth).
    # Every user-facing portfolio surface reads THIS id only — never an
    # aggregate of active portfolios. Default = Replay Recovery Account.
    CANONICAL_STOCK_PORTFOLIO_ID: str = "166b12ed-4b6d-4ec8-854d-234baa7d029a"

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
    # TRADIER PROVIDER (Phase Opt-B3a — sandbox EOD-delayed options chain)
    # Provider abstraction lives in
    # apps/api/src/options/data_provider/tradier_adapter.py. Activated
    # via OPTIONS_DATA_PROVIDER=tradier. Sandbox token bound to a
    # Tradier brokerage sandbox account.
    # ------------------------------------------------------------------
    TRADIER_BASE_URL: str = "https://sandbox.tradier.com/v1"
    TRADIER_ACCESS_TOKEN: str = ""
    TRADIER_TIMEOUT_SECONDS: int = 15
    TRADIER_RATE_LIMIT_QPS: float = 1.0
    TRADIER_DTE_WINDOW_DAYS: int = 60

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

    # ------------------------------------------------------------------
    # ELITE ARTHOS PRIORITY 7 — Agent Gateway v0 (fail-closed)
    # ------------------------------------------------------------------
    # PERMANENT default OFF. When False, the /agent/* router is NOT
    # mounted (every agent route 404s) and the owner token-management
    # console router is NOT mounted either — there is no way to mint a
    # token, so a leaked binary/config cannot activate the surface.
    # Flipping to True is dev/test only; a production flip is a separate
    # approval-gated decision (spec §10 rollout). The gateway is
    # read/jobs/drafts only — there is NO live-trading scope by design
    # (spec §3, NON-GOALS). See docs/architecture/AGENT_GATEWAY_V0_SPEC.md.
    AGENT_GATEWAY_ENABLED: bool = False
    # Token TTL policy (spec §2): mandatory expiry, v0 default 30d, max 90d.
    AGENT_TOKEN_DEFAULT_TTL_DAYS: int = 30
    AGENT_TOKEN_MAX_TTL_DAYS: int = 90

    # ------------------------------------------------------------------
    # ELITE ARTHOS PRODUCT SLICES — three INDEPENDENT fail-closed flags
    # ------------------------------------------------------------------
    # Each mounts one router in main.py; all default OFF (routes 404, no
    # public navigation). Owner/session authorization is enforced inside
    # the routers (require_owner on every mutation — the flag only controls
    # existence, never authorization). Generated content is always created
    # pending human review (service-enforced state machines); none of these
    # slices touches trading, execution, or recommendation generation.
    # P0-5 exactly-once — when True, run_paper_trading acquires a per-trading-
    # day execution lease so only one executor proceeds even if reached via
    # multiple scheduled paths (tick-loop claim + supercronic). Default OFF →
    # byte-identical legacy behavior until the execution_lease table (migration
    # 118) ships. The unique trade constraint stays as defense-in-depth.
    PAPER_EXECUTION_LEASE_ENABLED: bool = False

    THESIS_LEDGER_ENABLED: bool = False       # /api/theses + /api/admin/theses*
    RESEARCH_INBOX_ENABLED: bool = False      # /api/admin/inbox/*
    LEARNING_LOOP_ENABLED: bool = False       # /api/admin/lessons/*

    # Wave 1A — Recommendation Publication Preflight (deterministic trust
    # gate). Default OFF → publication behavior byte-identical to legacy.
    # When on: /api/admin/preflight/* mounts, GET /recommendations filters
    # HOLD/BLOCKED candidates from beginner surfaces and embeds a read-safe
    # verdict projection. No LLM, no override path, fail-closed.
    RECOMMENDATION_PREFLIGHT_ENABLED: bool = False

    # Wave 1B — Research Safe Mode (signal-derived system posture). Default
    # OFF → Wave-1A behavior exactly: no signals read, no events written,
    # no posture routes, no banner; SYSTEM_POSTURE_OVERRIDE (dev/test lever)
    # applies ONLY while this flag is off. ON → posture derives from the
    # deterministic signal registry; the override is ignored.
    SYSTEM_POSTURE_ENABLED: bool = False
    SYSTEM_POSTURE_OVERRIDE: str = ""

    # Wave 1C — "What changed?" recommendation delta. Default OFF → route
    # absent, recommendation responses byte-compatible, zero extra queries.
    # Read-only, zero-migration; consumes persisted preflight/posture facts
    # without ever triggering an evaluation.
    REC_DELTA_ENABLED: bool = False

    # ------------------------------------------------------------------
    # PHASE 16 v1 — Intraday context overlay (ephemeral)
    # ------------------------------------------------------------------
    # PERMANENT default OFF. When False, the market-tape poller does
    # NOT compute the intraday overlay and the overlay read endpoint
    # returns 404 for every recommendation_id. Flipping to True adds
    # an in-memory derivation step to each poll cycle (no DB writes,
    # no schema impact). See docs/research/INTRADAY_CONTEXT_OVERLAY.md.
    INTRADAY_OVERLAY_ENABLED: bool = False

    # ------------------------------------------------------------------
    # PHASE 16 Phase 2 — Intraday ML shadow data collection
    # ------------------------------------------------------------------
    # PERMANENT default OFF. When False, the market-tape poller does
    # NOT write `intraday_observation` rows. Flipping to True activates
    # one new UPSERT per (recommendation_id, 15-min slot) per cycle.
    # No trainer / scorer / UI / cron change is gated by this flag.
    # See docs/research/INTRADAY_ML_SHADOW.md.
    INTRADAY_ML_SHADOW_ENABLED: bool = False

    # ------------------------------------------------------------------
    # PHASE Opt-C1 — Options ML learning desk (gated)
    # ------------------------------------------------------------------
    # PERMANENT default OFF. Even when True, /api/options/learning/summary
    # returns aggregates ONLY after the closed-trade thresholds pass:
    #   - ≥30 total CLOSED paper trades
    #   - ≥10 CLOSED per strategy in ≥3 distinct strategies
    #   - ≥30 distinct trading days of CLOSED coverage
    # See docs/research/OPTIONS_OPT_C1_REFINEMENT.md §8.
    ML_OPTIONS_LEARNING_ENABLED: bool = False

    # ------------------------------------------------------------------
    # PHASE 11W (Phase D.2) — Real provider adapter (default OFF)
    # ------------------------------------------------------------------
    # PERMANENT default OFF in production. When False, the resolver
    # rejects any provider_name other than 'mock' BEFORE any network
    # call. Flipping requires operator-explicit env var + an API key.
    # All knobs below are belt-and-suspenders: cost cap, timeout, and
    # max output tokens are enforced before the provider is invoked.
    RESEARCH_REAL_PROVIDER_ENABLED: bool = False
    # Default provider for the manual run path. 'mock' is always
    # available; 'gemini' requires the flag above + an API key.
    RESEARCH_PROVIDER_NAME: str = "mock"
    # Gemini API key. None / empty blocks the provider before any
    # network call, even when RESEARCH_REAL_PROVIDER_ENABLED=true.
    RESEARCH_GEMINI_API_KEY: str | None = None
    # Hard timeout per provider call. Exceeded → provider_error.
    RESEARCH_PROVIDER_TIMEOUT_SECONDS: int = 20
    # Hard ceiling on output tokens we will request. Used in cost
    # estimation BEFORE the provider call.
    RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS: int = 500
    # Hard ceiling on worst-case estimated cost per single run. Over
    # this → status='cost_exceeded' written without invoking provider.
    RESEARCH_PROVIDER_MAX_COST_USD: float = 0.05

    # ------------------------------------------------------------------
    # PHASE 11W (Phase D.3) — Second real provider (Anthropic, default OFF)
    # ------------------------------------------------------------------
    # Default OFF in production. Resolver rejects 'anthropic' before
    # any network call unless ENABLED=true AND API_KEY non-empty.
    # Pricing constants live in the adapter; cost cap is enforced
    # pre-flight by the manual_run orchestrator (same mechanism as
    # gemini). Lazy SDK import — no anthropic dep is required at
    # module-load time.
    RESEARCH_ANTHROPIC_ENABLED: bool = False
    RESEARCH_ANTHROPIC_API_KEY: str | None = None
    RESEARCH_ANTHROPIC_MODEL: str = "claude-haiku-4-5"
    RESEARCH_ANTHROPIC_TIMEOUT_SECONDS: int = 20
    RESEARCH_ANTHROPIC_MAX_OUTPUT_TOKENS: int = 500
    RESEARCH_ANTHROPIC_MAX_COST_USD: float = 0.05

    # ------------------------------------------------------------------
    # PHASE 11X.2 — Controlled pilot paper execution (safe-gate evolution)
    # ------------------------------------------------------------------
    # Tightly-scoped paper-only path that opens at most ONE 0.25× sized
    # paper trade per day, gated by the existing safe_gate_evolution_shadow
    # diagnostic. NEVER live, NEVER broker, NEVER options. Default OFF.
    # Rollback = set this flag to false and restart.
    SAFE_GATE_EVOLUTION_PILOT_EXECUTION: bool = False
    SAFE_GATE_EVOLUTION_PILOT_MAX_TRADES_PER_DAY: int = 1
    SAFE_GATE_EVOLUTION_PILOT_SIZE_MULTIPLIER: float = 0.25
    SAFE_GATE_EVOLUTION_PILOT_MIN_MACRO_FAVORABLE: int = 1
    # Notional dollars per pilot trade BEFORE size multiplier.
    # Final qty = (notional × multiplier) / fill_price.
    SAFE_GATE_EVOLUTION_PILOT_NOTIONAL_USD: float = 1000.0

    # ------------------------------------------------------------------
    # PHASE OPTIONS-1 — Options paper-trading shadow evaluator
    # ------------------------------------------------------------------
    # Read-only diagnostic that decides "would the options system
    # have found a paper-tradable contract today?" Writes ONLY to
    # `options_shadow_decision_log`. NEVER opens trades. Default OFF
    # at the runner level; the evaluator can also be invoked
    # directly with persist=False for pure dry-run.
    OPTIONS_SHADOW_EVAL_ENABLED: bool = False
    # Opt-B — generator output taxonomy. "directional" (legacy debit/long
    # structures) or "credit" (engine-aligned SHORT_*_CREDIT_SPREAD +
    # IRON_CONDOR). Default keeps legacy behaviour; flip to "credit" to
    # emit engine-executable defined-risk structures. No engine/risk
    # change — this only selects which rule_ids the generator emits.
    OPTIONS_GENERATOR_STRUCTURES: str = "directional"
    # Phase C Stage 2A — when True, the generator materializes + persists
    # the complete set of selected legs (2 for credit spreads, 4 for iron
    # condors) into options_candidate_leg. Default OFF. Pure persistence:
    # never changes qualification, scoring, ranking, selection params, or
    # wing width; if any leg can't be priced the candidate still emits
    # unchanged (legs simply incomplete). Economics (Stage 2B) reads these
    # legs — this flag does NOT enable economics.
    OPTIONS_PERSIST_LEGS: bool = False
    OPTIONS_SHADOW_MIN_OPEN_INTEREST: int = 500
    OPTIONS_SHADOW_MAX_SPREAD: float = 0.10
    OPTIONS_SHADOW_MIN_BID: float = 0.01
    OPTIONS_SHADOW_MIN_DTE: int = 7
    OPTIONS_SHADOW_MAX_DTE: int = 45
    OPTIONS_SHADOW_TOP_N: int = 5

    # ------------------------------------------------------------------
    # Phase Opt-B3a Phase B — chain-integrity invariants
    # ------------------------------------------------------------------
    # Production providers allowed in shadow-eval runs. Any provider
    # not in this whitelist is filtered out at chain-selection time.
    # Test fixtures (csv-fixture, yahoo, mock) are EXCLUDED.
    OPTIONS_PRODUCTION_PROVIDERS: tuple[str, ...] = ("tradier", "thetadata")
    # Maximum allowable age of the chain batch backing a shadow-eval
    # run, computed live as (NOW() - snapshot_at_utc). Replaces
    # reliance on the frozen quote_age_seconds field.
    MAX_RUN_CHAIN_AGE_HOURS: int = 24
    # Universe of underlyings eligible for shadow-eval consumption.
    # Mirror of chain_ingest.DEFAULT_UNIVERSE — kept here so the
    # evaluator can enforce universe closure at its own boundary
    # (Invariant: RUN_UNIVERSE_CLOSURE).
    OPTIONS_RUN_UNIVERSE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "GLD", "TLT")

    # ------------------------------------------------------------------
    # Phase Opt-C2 Pre-Canary 0 — controlled canary activation
    # ------------------------------------------------------------------
    # Master canary gate — gates promotion + lifecycle. Default OFF.
    # Independent from OPTIONS_ENABLED (which remains the master
    # broad-execution gate and stays OFF). When CANARY_ENABLED=true,
    # promoter + lifecycle jobs respect the per-portfolio caps below.
    OPTIONS_CANARY_ENABLED: bool = False
    # Single underlying for canary universe.
    OPTIONS_CANARY_UNIVERSE: str = "SPY"
    # Single strategy family allowed. P6B.0: aligned to an engine
    # defined-risk strategy (BULL_CALL_SPREAD is NOT in the engine's
    # DEFINED_RISK_STRATEGIES; SHORT_PUT_CREDIT_SPREAD is bullish + engine-
    # validated + generator-emitted). Seed migrated in 092.
    OPTIONS_CANARY_STRATEGY: str = "SHORT_PUT_CREDIT_SPREAD"
    # Hard slot cap per portfolio (enforced in promoter).
    OPTIONS_CANARY_MAX_OPEN: int = 1
    # Max dollar reservation per trade (enforced via max_loss_dollars).
    OPTIONS_CANARY_MAX_CAPITAL_USD: float = 500.0
    # DTE window for canary proposals (excludes 0DTE chaos and very
    # long-dated theta-bound holds).
    OPTIONS_CANARY_MIN_DTE: int = 21
    OPTIONS_CANARY_MAX_DTE: int = 45
    # P6B.0 selection + exit knobs (inert until OPTIONS_CANARY_ENABLED).
    # Minimum candidate confidence to be promotable.
    OPTIONS_CANARY_MIN_CONFIDENCE: float = 0.60
    # Take-profit: close when captured >= this fraction of max profit.
    OPTIONS_CANARY_TP_PCT: float = 0.50
    # DTE management: close at/under this many days to expiry.
    OPTIONS_CANARY_DTE_CLOSE: int = 7
    # P6D.33A economic viability gate (selector + lifecycle TP guard).
    # Intentionally NOT wired into compose — these defaults are the source
    # of truth everywhere; full model documented in
    # apps.api.src.options.canary.economics.
    # Entry credit must be >= multiple × (close drag + round-trip fees).
    OPTIONS_CANARY_MIN_CREDIT_MULTIPLE: float = 2.0
    # Floor on net (after round-trip fees) max profit / max loss.
    OPTIONS_CANARY_MIN_NET_REWARD_RISK: float = 0.10
    # P6D.34C — targeted intraday quote refresh + decision freshness gate.
    # Intentionally NOT wired into compose (same precedent as the 33A pair
    # above) — these defaults are the source of truth everywhere.
    # Refresh the chain for each underlying with an open canary position
    # at the start of every lifecycle cycle (before exit decisions).
    OPTIONS_CANARY_QUOTE_REFRESH_ENABLED: bool = True
    # Max effective quote age (seconds, P6D.34A effective_age_seconds) for
    # a CLOSE decision (take-profit / DTE management) to be trusted; older
    # → HOLD_STALE_QUOTES. Expiry settlement is exempt (price_bar-based).
    OPTIONS_CANARY_MAX_DECISION_AGE_SECONDS: int = 900
    # P6D.36D — enforced portfolio-level risk controls in promote_one
    # (settings-only, NOT wired into compose; same precedent as the
    # 33A/34C/34D knobs). Defaults PRESERVE max_open=1 behavior; scaling
    # max_open beyond 1 stays blocked until the universe/per-underlying
    # cap policy is decided (QQQ-only universe + cap 1 cannot fill a
    # second slot by design).
    # Max OPEN canary positions per underlying symbol.
    OPTIONS_CANARY_MAX_PER_UNDERLYING: int = 1
    # Max promotions per portfolio per calendar day (DB CURRENT_DATE).
    OPTIONS_CANARY_MAX_PROMOTIONS_PER_DAY: int = 1
    # Projected cash AFTER reserving must stay >= this floor. 0 = no
    # floor beyond the existing non-negative-cash debit guard.
    OPTIONS_CANARY_MIN_CASH_FLOOR_DOLLARS: float = 0.0
    # Projected SUM of structural max_loss across OPEN positions
    # (including the new trade) must stay <= this cap. Default equals
    # OPTIONS_CANARY_MAX_CAPITAL_USD so exactly one max-size trade fits
    # — behavior-identical at max_open=1.
    OPTIONS_CANARY_MAX_AGGREGATE_LOSS_DOLLARS: float = 500.0
    # P6D.37B — exit-specific fillability profile (settings-only, NOT
    # wired into compose; same precedent as the 33A/34C/34D/36D knobs).
    # Applies ONLY to close_trade exit fills; entry fills, expiry
    # settlement, and the lifecycle decision gates are untouched.
    # Defaults are INERT: they reproduce the entry gate exactly
    # (OI>=500, absolute $0.10 spread cap). Rollout flips via env to
    # OPTIONS_EXIT_MIN_OI=0 + OPTIONS_EXIT_MAX_SPREAD_PCT=0.015.
    # Min open interest required on an EXIT fill. 0 disables the OI
    # gate on exits (you already hold the position; OI is an entry-
    # opportunity filter, not an exit-sanity one).
    OPTIONS_EXIT_MIN_OI: int = 500
    # Relative spread cap on exits, as a FRACTION of mid (0.015 = 1.5%).
    # Effective cap = max(FLOOR, PCT * mid). 0.0 = relative term off →
    # absolute floor only (inert/current behavior).
    OPTIONS_EXIT_MAX_SPREAD_PCT: float = 0.0
    # Absolute floor (dollars) of the exit spread cap. Equals the entry
    # gate's MAX_BID_ASK_SPREAD_DOLLARS by default.
    OPTIONS_EXIT_MAX_SPREAD_FLOOR_DOLLARS: float = 0.10
    # P6D.37C — role-aware wing OI threshold at ENTRY (settings-only,
    # NOT wired into compose). Min open interest for BUY (hedge/wing)
    # legs at open; SELL (risk) legs always keep the strict
    # MIN_OPEN_INTEREST=500. Every engine strategy is a credit
    # structure (SPCS/SCCS/IC), so side==BUY is exactly the protective
    # wing. Default 500 is INERT (== the strict gate); rollout flips to
    # 100 via env after validation. Background: QQQ OI concentrates on
    # the $5 strike grid, $1 wings land off-grid (~300 OI) with spreads
    # as tight as 30k-OI strikes — 2 of 6 candidate-days in the 37A
    # window were zero-promotable on wing OI alone.
    OPTIONS_CANARY_WING_MIN_OI: int = 500
    # P6D.34D — promotion freshness gate (settings-only, NOT wired into
    # compose; same precedent as the 33A/34C knobs above). Max effective
    # quote age (seconds) for a candidate's leg quotes at PROMOTION time;
    # any older/missing leg quote skips the candidate with reason
    # 'stale_quotes' BEFORE the fillability gate (correct attribution —
    # compute_fill's 60s MAX_QUOTE_AGE gate would otherwise report it as
    # 'unfillable'). The 60s fill gate stays authoritative (P6D.12
    # selector==engine parity); this is the coarse classifier.
    OPTIONS_CANARY_MAX_PROMOTION_AGE_SECONDS: int = 900

    # ------------------------------------------------------------------
    # PHASE 11W (Phase E) — Manual research-run activation (research-only)
    # ------------------------------------------------------------------
    # Adds a tightly-gated *manual* trigger for the research-artifact
    # pipeline. Default OFF. Activation requires BOTH
    # `RESEARCH_RO_ENABLED=true` AND `RESEARCH_MANUAL_RUN_ENABLED=true`
    # at process boot. NEVER schedules itself. NEVER touches
    # execution / scoring / candidate / paper / options paths.
    # NEVER returns raw model body to the API caller (only metadata).
    # The HTTP route, when mounted, is admin-gated by
    # `RESEARCH_ADMIN_TOKEN` (X-Admin-Token header).
    RESEARCH_MANUAL_RUN_ENABLED: bool = False
    # Per-run worst-case dollar ceiling. Mirrors / overlays the
    # existing per-provider RESEARCH_PROVIDER_MAX_COST_USD and
    # RESEARCH_ANTHROPIC_MAX_COST_USD knobs. The smaller of {this,
    # provider-specific cap} wins.
    RESEARCH_MAX_RUN_COST_USD: float = 0.05
    # Daily aggregate dollar ceiling across all manual runs. The
    # orchestrator queries SUM(cost_usd) for runs started today and
    # refuses new runs once this is reached.
    RESEARCH_MAX_DAILY_COST_USD: float = 1.00
    # Per-(symbol, day) run count cap. Prevents trivial spam of the
    # same ticker by an operator.
    RESEARCH_MAX_TICKER_DAILY_RUNS: int = 3
    # CSV of provider names that the manual run is allowed to call.
    # Defaults to mock so a fresh deployment cannot trigger a paid
    # provider until an operator explicitly widens the allowlist.
    RESEARCH_ALLOWED_PROVIDERS: str = "mock"
    # CSV of symbols allowed for manual research. Empty = no
    # allowlist (any symbol whose `asset` row exists is accepted).
    RESEARCH_ALLOWED_SYMBOLS: str = ""
    # Admin token required by the HTTP route. Empty disables HTTP
    # mounting entirely even if RESEARCH_MANUAL_RUN_ENABLED is on.
    RESEARCH_ADMIN_TOKEN: str = ""

    # ------------------------------------------------------------------
    # PHASE 11W (Phase E.1) — Enterprise-safe controls (research-only)
    # ------------------------------------------------------------------
    # CSV of operator IDs allowed to invoke manual run. Empty = no
    # operator allowed (refuses every request) UNLESS the process is
    # in `RESEARCH_LOCAL_TEST_MODE` for local dev. Production must
    # explicitly enumerate operators.
    RESEARCH_ALLOWED_OPERATORS: str = ""
    # Local/dev opt-out from operator allowlist. NEVER set true in
    # production. When true and `RESEARCH_ALLOWED_OPERATORS` is empty,
    # any operator_id is accepted; the audit row records this as
    # 'local_test_mode' for visibility.
    RESEARCH_LOCAL_TEST_MODE: bool = False
    # Per-operator daily run cap (counts ALL terminal statuses).
    RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY: int = 5
    # Per-symbol daily run cap (overlaps existing
    # RESEARCH_MAX_TICKER_DAILY_RUNS but is enforced through the
    # audit log so rejected attempts also count when needed).
    RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY: int = 3
    # Maximum simultaneous in-flight manual runs across the cluster.
    # Counted via audit rows whose status='in_flight' and created_at
    # is within the last 5 minutes.
    RESEARCH_MAX_CONCURRENT_MANUAL_RUNS: int = 1
    # Rolling-window thresholds for anomaly detection (deterministic,
    # rule-based; no ML).
    RESEARCH_ANOMALY_REJECTED_WINDOW_MIN: int = 30
    RESEARCH_ANOMALY_REJECTED_THRESHOLD: int = 5
    RESEARCH_ANOMALY_TOKEN_VIOLATION_THRESHOLD: int = 3
    RESEARCH_ANOMALY_DUPLICATE_THRESHOLD: int = 5
    # Cost-spike alert: a single attempt whose estimated_cost is
    # this many times the per-run cap raises an anomaly flag.
    RESEARCH_ANOMALY_COST_SPIKE_MULTIPLIER: float = 5.0

    # ------------------------------------------------------------------
    # PHASE 11W (Phase E.3) — Auto enforcement + cooldown
    # ------------------------------------------------------------------
    # Default OFF. When False, the evaluator only runs in dry-run
    # mode (analysis only; no state change, no alert). When True,
    # `run_manual_safely` evaluates the operator's signal summary
    # before each provider call and auto-applies the resulting state
    # transition if the desired state differs from the current.
    RESEARCH_AUTO_ENFORCEMENT_ENABLED: bool = False
    # Lookback window for "recent violations" used by demotion
    # rules.
    RESEARCH_ENFORCEMENT_LOOKBACK_HOURS: int = 24
    # Cooldown durations per transition target.
    RESEARCH_WATCH_COOLDOWN_HOURS: int = 24
    RESEARCH_RESTRICTED_COOLDOWN_HOURS: int = 24
    RESEARCH_TOKEN_RESTRICTED_COOLDOWN_HOURS: int = 72
    RESEARCH_BLOCKED_COOLDOWN_HOURS: int = 24
    # Admin-override usage thresholds in the lookback window.
    RESEARCH_ADMIN_OVERRIDE_WATCH_THRESHOLD: int = 2
    RESEARCH_ADMIN_OVERRIDE_RESTRICT_THRESHOLD: int = 5
    # Alert deduplication window (minutes). Identical
    # (operator_id, alert_type, severity) inside this window
    # collapse into the existing open alert.
    RESEARCH_ALERT_DEDUP_WINDOW_MIN: int = 30
    # Auto-resolve open alerts older than this when the operator
    # has returned to `clear`.
    RESEARCH_ALERT_AUTO_RESOLVE_HOURS: int = 24

    # ------------------------------------------------------------------
    # PHASE 11W (Phase F.1) — Premium UX tier (read-only)
    # ------------------------------------------------------------------
    # Server-side default tier. Resolves the caller's tier when no
    # X-Research-Tier header is provided. Default `free`. NEVER
    # auto-elevates a caller. NOT a billing system — temporary
    # config-driven gate until a real entitlement system lands.
    RESEARCH_PREMIUM_TIER: str = "free"

    # ------------------------------------------------------------------
    # PHASE G — auth + subscription tier resolution
    # ------------------------------------------------------------------
    # Elite ArthOS "Honest Numbers" — dataset-level ingest contracts
    # (domain/prices/contracts.py): quarantine suspect bars, fail closed on
    # widespread corruption, structured per-symbol reports. Default OFF —
    # the legacy validate_batch path is byte-identical when false. Enable
    # only after the wired path's tests and an owner review of quarantine
    # thresholds.
    INGEST_CONTRACTS_ENABLED: bool = False
    # Elite ArthOS "Honest Numbers" — Priority 3: honest paper execution
    # costs (domain\paper_trading\execution_costs.py). When True, the bare
    # submit_trade fill path applies adverse slippage (liquidity-aware
    # square-root impact when 20-bar avg dollar volume exists, flat
    # spread-floor fallback otherwise) plus commission, both deducted from
    # cash and stamped on the trade row via the existing fill_price /
    # slippage_bps / commission columns. Callers that pass
    # fill_price_override / slippage_bps / commission (weekly rebalance)
    # keep their own cost model. Default OFF — the legacy zero-cost fill
    # path is byte-identical when false.
    PAPER_COST_MODEL_ENABLED: bool = False
    # Commission in basis points of gross notional (0 = free broker).
    PAPER_COMMISSION_BPS: float = 0.0
    # Slippage floor in bps (half-spread proxy; mirrors the weekly
    # rebalance cost model's 2bps minimum). Also the flat deterministic
    # fallback when no dollar-volume data exists for the asset.
    PAPER_SPREAD_FLOOR_BPS: float = 2.0
    # Hard cap (bps) on liquidity-aware slippage for very large orders.
    PAPER_SLIPPAGE_CAP_BPS: float = 50.0
    # Square-root impact coefficient: slippage_bps =
    # k * sqrt(order_notional / avg_dollar_volume) — k is the slippage in
    # bps for an order equal to one full day's average dollar volume.
    PAPER_IMPACT_K_BPS: float = 10.0
    # When True, get_current_user() falls back to a synthetic dev user
    # and tier resolution honors the legacy `RESEARCH_PREMIUM_TIER`
    # env. NEVER set true in production.
    AUTH_DISABLED_LOCAL: bool = False
    # M1 accounts: when True, the X-Auth-User-Id device header is honored as an
    # identity fallback (demo/dev ONLY). MUST stay False in production — public
    # auth resolves identity from the session cookie, never a client header.
    DEMO_DEVICE_MODE: bool = False
    # Session cookie Secure flag. False for local HTTP dev; True in prod (HTTPS).
    SESSION_COOKIE_SECURE: bool = False
    # M1B login rate-limit / lockout (brute-force protection on POST /api/login).
    # After MAX failed attempts (by email or IP) within WINDOW seconds, further
    # attempts are rejected with the SAME generic error for LOCKOUT seconds.
    AUTH_LOGIN_MAX_ATTEMPTS: int = 5
    AUTH_LOGIN_WINDOW_SECONDS: int = 900
    AUTH_LOGIN_LOCKOUT_SECONDS: int = 900
    # M1C trusted-proxy IP extraction. When False (default) the rate-limiter uses
    # the direct peer IP. When True AND the direct peer is inside one of the
    # trusted CIDRs, the first forwarded client IP (CF-Connecting-IP or the first
    # X-Forwarded-For entry) is used. Never trust forwarded headers from an
    # untrusted direct peer.
    AUTH_TRUST_PROXY_HEADERS: bool = False
    AUTH_TRUSTED_PROXY_CIDRS: str = ""   # CSV, e.g. "127.0.0.1/32,10.0.0.0/8"
    # M1C login_attempt retention (days) for the prune job. Must exceed the
    # window+lockout horizon; the prune helper also enforces a hard min-keep.
    AUTH_LOGIN_ATTEMPT_RETENTION_DAYS: int = 7
    # M6A — CORS allowed origins (comma-separated). Dev default preserves the
    # Vite origin. In prod, set the SPA domain(s); never use '*' with credentials
    # (the auth cookie flow requires allow_credentials=True). The deploy preflight
    # rejects '*' and localhost-only origins in prod.
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"
    # When True, expired/past_due/canceled subscriptions still grant
    # the prior tier for `RESEARCH_GRACE_HOURS` hours after the
    # period end. Disabled by default — strict downgrade.
    RESEARCH_GRACE_ENABLED: bool = False
    RESEARCH_GRACE_HOURS: int = 72

    # ------------------------------------------------------------------
    # PHASE F2 — Agent insights LLM adapter (read-only, default OFF)
    # ------------------------------------------------------------------
    # Wraps the deterministic narrator (Phase F1) in a single
    # Anthropic Messages-API call. NO DB writes, NO caching, NO
    # background tasks. The /api/insights/{kind} endpoint returns 503
    # unless BOTH AGENT_INSIGHTS_ENABLED is true AND ANTHROPIC_API_KEY
    # is non-empty. Insight output is read-only research context; it
    # MUST NEVER influence scoring, signals, trades, exits, or
    # execution. Rollback = set AGENT_INSIGHTS_ENABLED=false.
    AGENT_INSIGHTS_ENABLED: bool = False
    ANTHROPIC_API_KEY: str = ""
    AGENT_INSIGHTS_MODEL: str = "claude-3-5-haiku-latest"
    AGENT_INSIGHTS_MAX_TOKENS: int = 800
    AGENT_INSIGHTS_TIMEOUT_SECONDS: float = 5.0
    # Soft per-process cost ceiling for insight calls. Not enforced
    # at the SDK boundary in F2 (no per-call cost accounting yet);
    # operators surface this number in dashboards. Phase F3 will
    # wire a real running-total guard.
    AGENT_INSIGHTS_COST_GUARD_USD: float = 5.0

    # F5 — admin-only cache maintenance gate. When True the
    # `DELETE /api/insights/cache` route is mounted, gated by the
    # same `X-Admin-Token` header used by research_manual. Default
    # False so production deployments cannot accidentally expose a
    # destructive endpoint.
    AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED: bool = False


settings = Settings()
