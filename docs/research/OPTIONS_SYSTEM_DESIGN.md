---
phase: 11A
status: DESIGN ONLY
date: 2026-04-26
locks:
  provider: ThetaData
  analytics_canonical: QuantLib
  analytics_fallback: py_vollib
  ml_framework: scikit-learn
  ml_can_affect_trades: false      # permanent v1
  options_paper_only: true          # permanent v1
  strategy_universe: [short_put_credit_spread, short_call_credit_spread, iron_condor]
  underlyings: [SPY, QQQ, IWM, GLD, TLT]
  dte_range: [30, 60]
  short_strike_delta_range: [0.15, 0.30]
  min_open_interest: 500
  max_bid_ask_spread_dollars: 0.10
  snapshot_cadence_minutes: 15
sources:
  synthesis: ~/.claude-octopus/discover/options-system-research/synthesis.md
  reviewers: [Codex, Gemini, Sonnet, Opus]
---

# Options System — Master Architecture Design

**Status:** Design only. NO source code. NO migrations. NO modifications to existing equity / V2 system.
**Phase:** 11A (architecture docs only)
**Next phase:** 11B (schema only) — gated on operator approval of this doc set.

---

## 1. Mandate

Build a NEW options research + paper-trading system, completely separate
from the existing equity / V2 governance / live execution surfaces.
**Paper-only.** **No live broker integration in v1.** **No ML in
execution.** Hard separation enforced at module / schema / API / UI
levels with bidirectional grep CI checks (see `OPTIONS_BOUNDARIES.md`).

## 2. Provenance

This doc is the architectural distillation of the four-way Octo Discover
synthesis (Codex / Gemini / Sonnet / Opus, dated 2026-04-26). Where
reviewers disagreed, the chosen path is documented + the rationale
recorded. Source synthesis at
`~/.claude-octopus/discover/options-system-research/synthesis.md`.

## 3. System layout

```
apps/api/src/options/                  ← NEW namespace, parallel to equity
├── data/
│   ├── providers/
│   │   └── thetadata.py               # adapter; provider-agnostic boundary
│   ├── chains_ingest.py               # 15-min snapshot job → options_chain table
│   ├── greeks_compute.py              # QuantLib canonical + py_vollib fast path
│   └── liquidity_filter.py            # min OI, max spread, min volume
├── features/
│   ├── iv_rank.py + iv_percentile.py  # 252d IV percentile per underlying
│   ├── term_structure.py              # 30/60d IV ratio
│   ├── skew.py                        # 25-delta put/call IV diff
│   ├── vrp.py                         # IV − realized vol (rolling 30d)
│   └── put_call_ratio.py
├── strategies/
│   ├── short_put_credit_spread.py
│   ├── short_call_credit_spread.py
│   ├── iron_condor.py
│   └── strategy_screener.py           # rule-based candidate generator
├── paper/
│   ├── lifecycle.py                   # PROPOSED → OPEN → MTM → CLOSED|EXPIRED|ASSIGNED
│   ├── fill_simulator.py              # NBBO-aware, mid + spread fraction
│   ├── expiration_handler.py          # ITM/OTM/pin-risk; BUILT FIRST
│   ├── assignment_handler.py          # ex-div + early exercise
│   └── risk_snapshot.py               # daily portfolio Greeks
├── ml_advisory/                       # offline-only; mirrors equity Phase 10C.1
│   ├── vol_regime_classifier.py
│   └── skew_alert_classifier.py
├── api/                               # /api/options/* — separate prefix
│   ├── chains.py
│   ├── strategies.py
│   ├── paper_trades.py
│   ├── risk.py
│   └── ml_advisory.py
└── (no __main__; orchestration via worker jobs)

apps/worker/src/jobs/options_*         # separate job namespace
├── options_chain_snapshot.py          # 15-min cadence
├── options_features_daily.py          # nightly feature compute
├── options_paper_mtm_daily.py         # nightly mark-to-market
├── options_expiration_check.py        # T-1 day expiration alerts
└── options_ml_advisory_weekly.py      # weekly classifier refresh

apps/web/src/pages/Options.tsx         # separate page route /options
apps/web/src/components/options/       # separate component namespace
```

## 4. Component responsibilities

### 4.1 Data layer

**Provider adapter** (`data/providers/thetadata.py`) is the only place
that knows ThetaData specifics. All downstream code consumes a
normalized `OptionChainSnapshot` dataclass. Provider swap (e.g. to
Polygon in v2) is a config + adapter file change — not a refactor.

**Chain ingest** (`data/chains_ingest.py`) runs every 15 min during
market hours. Idempotent on `(snapshot_at, underlying, expiry, strike,
right)`. Writes to `options_chain` table with `provider_version`,
`snapshot_at_utc`, `quote_age_seconds`. Rejects rows with `quote_age >
60s` as stale.

**Greeks compute** (`data/greeks_compute.py`) uses **QuantLib** as
canonical (American exercise, dividends, scenario pricing) and
**py_vollib** as fast fallback for European-style sanity checks.
Cross-validates the two on a fixed sanity-test set per Codex's mandate.

**Liquidity filter** (`data/liquidity_filter.py`) is a pure function
that drops rows below floors (min OI 500, min ADV 100, max bid-ask
spread $0.10 for ETF options). Applied before any strategy screener
considers a strike.

### 4.2 Features layer

All features are **pure functions over snapshots**. No I/O. Match the
discipline of the equity comparison framework. Computed nightly in
`options_features_daily.py` and stored in `options_features` table for
fast lookup.

| Feature | Computation | Source |
|---|---|---|
| `iv_rank_252d` | percentile of current ATM IV vs trailing 252-day | TastyTrade convention |
| `iv_percentile_252d` | same, percentile flavor | Same |
| `realized_vol_30d` | annualized stdev of last 30 daily underlying returns | Standard |
| `vrp_30d` | ATM IV − realized_vol_30d | Bakshi/Cao/Chen 1997 |
| `term_structure_30_60` | 30d IV / 60d IV ratio | Bakshi/Kapadia/Madan 2003 |
| `skew_25d` | (25-delta put IV − 25-delta call IV) | CBOE SKEW analog |
| `put_call_oi_ratio` | total put OI / total call OI | Standard |
| `put_call_volume_ratio` | total put volume / total call volume | Standard |

### 4.3 Strategies layer

Each strategy is a Python class with explicit:

- `entry_criteria(features, chain)` → list of candidate trades
- `entry_legs(candidate)` → list of `Leg(option_symbol, side, qty)`
- `exit_criteria(position)` → bool (close now)
- `max_loss(legs)` / `max_profit(legs)` / `breakeven(legs)` — pure functions

**Build order** (Sonnet's mandate):
1. `short_put_credit_spread.py` — first; simplest defined-risk
2. `short_call_credit_spread.py` — mirror
3. `iron_condor.py` — combines #1 + #2; only after both work end-to-end

**Strategy screener** (`strategy_screener.py`) is a rule-based
candidate generator. Reads features + chain → produces candidate trades
→ operator selects manually via UI. **No automatic execution.**

### 4.4 Paper-trading layer

See `OPTIONS_PAPER_TRADING_DESIGN.md` for full lifecycle specification.
**Key invariant: build expiration_handler.py + assignment_handler.py
FIRST, before any strategy logic.**

### 4.5 ML advisory layer

Mirrors the discipline of equity Phase 10C.1 design:

- Two narrow classifiers only (vol regime, skew alert)
- sklearn only (no DL/RL/xgboost in v1)
- Walk-forward validation (banned: KFold, train_test_split, shuffle)
- Output dict carries `advisory_only: true`, `is_used_in_decisions: false`,
  `warning: "ML advisory — not used in decisions"`
- Hardcoded `OPTIONS_ML_CAN_AFFECT_TRADES = false`
- ML output appears only in WebUI sidebar labeled "ADVISORY ONLY"
- No imports from `strategies/`, `paper/`, or `api/paper_trades.py`
- No imports of ML from `strategies/`, `paper/`, or `api/strategies.py`

### 4.6 API layer

Read-only endpoints + a single write surface (paper-trade entry):

```
GET  /api/options/chains/{symbol}                     read-only chain
GET  /api/options/features/{symbol}                   read-only features
GET  /api/options/strategies/{symbol}                 candidate trades
GET  /api/options/paper-trades                        list positions
GET  /api/options/paper-trades/{id}                   single position detail
POST /api/options/paper-trades                        create paper trade (operator)
POST /api/options/paper-trades/{id}/close             close paper trade (operator)
GET  /api/options/risk                                portfolio risk snapshot
GET  /api/options/ml-advisory                         advisory-only ML output
```

**Mounted under `/api/options/*`. Never co-mounted with `/api/v2-promotion/*` or `/api/b2-v2/*` routers.**

### 4.7 WebUI

Single new page at `/options`. Five read-mostly screens + one write
action (paper-trade entry). See `OPTIONS_PAPER_TRADING_DESIGN.md`
§WebUI for component spec.

**No co-mounting with `/ops` (V2 governance home).**

## 5. Data flow

```
                    ┌─────────────────┐
                    │ ThetaData REST  │ (adapter; provider-agnostic)
                    └────────┬────────┘
                             │ every 15 min during market hours
                             ▼
                  options_chain (snapshots)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       liquidity_filter  greeks_compute   features (nightly)
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                    options_features
                             │
              ┌──────────────┼──────────────────┐
              ▼              ▼                  ▼
       strategy_screener  ml_advisory     risk_snapshot
              │              │                  │
              ▼              ▼                  ▼
       candidate trades   ADVISORY ONLY    portfolio Greeks
              │              │                  │
              ▼              ▼                  ▼
       ┌──────────────────────────────────────────────┐
       │              WebUI /options                  │
       │  positions / vol dashboard / expir cal /     │
       │  screener / ML advisory sidebar              │
       └──────────────────────────────────────────────┘
              │
              │ operator clicks "paper trade"
              ▼
       paper/lifecycle.py
              │
              ▼
       options_paper_trade + options_paper_trade_leg
              │
              ▼ (nightly)
       paper/expiration_handler.py + assignment_handler.py
              │
              ▼
       options_risk_snapshot
```

**Hard rule:** zero data flows from `options/` back into V2 / equity
governance, ever. The systems run side-by-side with no semantic
coupling.

## 6. Settings flags

| Flag | Default | Lifecycle |
|---|---|---|
| `OPTIONS_ENABLED` | `false` | Operator opt-in per environment; `true` for research env, `false` for prod until v2 |
| `OPTIONS_PAPER_ONLY` | `true` | **Permanent v1.** Mirrors `ML_CAN_AFFECT_TRADES = false`. Setting to `false` would require a new design phase + explicit operator approval. |
| `OPTIONS_ML_CAN_AFFECT_TRADES` | `false` | **Permanent v1.** Mirrors `ML_CAN_AFFECT_TRADES`. Single-flag kill switch for ML→trade coupling. |
| `OPTIONS_DATA_PROVIDER` | `"thetadata"` | Provider adapter selector; `"polygon"` adapter would be added in v2 |
| `OPTIONS_SNAPSHOT_INTERVAL_MINUTES` | `15` | Frozen v1 |
| `OPTIONS_DEFAULT_FILL_MODEL` | `"mid_plus_25_pct_spread"` | Frozen v1; alternative `"mid_minus_one_tick"` selectable per environment |

## 7. Phased implementation plan

| Phase | Scope | Duration | Outputs |
|---|---|---|---|
| **11A** | Architecture docs only (THIS DOC + 4 siblings + index) | ≈ 1 week | 5 design docs + index |
| **11B** | Schema only — `options_*` tables, ORM models, alembic migration `phase11_*_options_schema.py` | ≈ 1 week | DDL + models + migration; no business logic |
| **11C** | Data ingest only — provider adapter + chain snapshot job + liquidity filter + Greeks compute | ≈ 2 weeks | One new worker job; idempotent; no UI |
| **11D** | Feature engine only — IVR/IVP/term-structure/skew/VRP/PCR pure functions + nightly job | ≈ 1–2 weeks | Features stored; no strategy logic |
| **11E** | Paper-trading engine — strategy screener + lifecycle + fill simulator + expiration/assignment handlers + risk snapshot | ≈ 2–3 weeks | **Build expiration handler FIRST.** End-to-end test before strategy logic. |
| **11F** | WebUI — chain viewer + strategy builder + positions table + vol dashboard + expiration calendar + ML advisory sidebar | ≈ 2 weeks | Read-mostly UI + one write action |
| **11G** | OOS validation — walk-forward backtest + PBO/DSR diagnostics over accumulated paper-trade history | ≈ 1–2 weeks (after ≥ 60 days OOS) | Mirrors equity Phase 10A discipline |

**Total: 10–13 weeks for v1.**

## 8. Hard boundaries

See `OPTIONS_BOUNDARIES.md` for the full enforcement spec including
grep invariants and behavioral isolation tests. Summary:

- Bidirectional grep enforcement: options ↔ V2 imports must be zero
- Separate Postgres schema (`options_*`); zero FKs to equity tables
- Separate API prefix `/api/options/*`
- Separate UI page `/options`
- Permanent kill switches: `OPTIONS_PAPER_ONLY`, `OPTIONS_ML_CAN_AFFECT_TRADES`
- No naked short, no 0DTE, no DL/RL, no last-price fills

## 9. Risks + mitigations (top 5)

| Risk | Severity | Mitigation |
|---|---|---|
| Expiration / assignment handler bugs corrupting all P&L | **CRITICAL** | Build first; end-to-end test before any strategy logic ships |
| Stale chain data used for paper fills | High | Fail-fast if quote_age > 5s; document snapshot freshness invariant |
| Wide-spread blow-up on thin-OI strikes | High | Liquidity floor at strategy build time (min OI 500, max spread $0.10) |
| ML output leaking into trade selection | Medium | Mirror Phase 10C.1 grep enforcement + behavioral isolation tests |
| Cross-system contamination with V2 equity | High | Separate schema; separate API namespace; separate UI page; grep-enforced |

Full risk register: `OPTIONS_BOUNDARIES.md` §Risk register.

## 10. References

- Synthesis: `~/.claude-octopus/discover/options-system-research/synthesis.md`
- Reviewer transcripts: `~/.claude-octopus/discover/options-system-research/rounds/r001_*.md`
- Sibling docs: `OPTIONS_DATA_PROVIDER_EVAL.md`, `OPTIONS_STRATEGY_UNIVERSE.md`, `OPTIONS_PAPER_TRADING_DESIGN.md`, `OPTIONS_BOUNDARIES.md`
- Equity discipline parallels: `V2_PROMOTION_TRIGGER_DESIGN.md`, `V2_ML_ADVISORY_DESIGN.md` (mirror discipline; do NOT cross-couple)

## 11. Acceptance for Phase 11A

This doc set ships when:

1. All 5 design docs created + populated
2. `docs/research/README.md` indexes them
3. Zero source code modified (`git status --short apps/ infra/ scripts/` shows no `M` to source files)
4. Each doc carries the locked-choice frontmatter
5. Operator review sign-off recorded before any Phase 11B (schema) work begins

`STOP` after docs ship; await operator review.
