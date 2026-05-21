# Research Docs Index

Research + architecture artifacts for the investment platform. Two
parallel domains: **Equity / V2 governance** and **Options** (NEW v1).
The two systems are hard-isolated; cross-references in this index are
informational only.

---

## Equity / V2 governance

### Strategy + framework

- [`B2_V2_PERSIST3_UPDATE.md`](./B2_V2_PERSIST3_UPDATE.md) — V2 strategy introduction (TSMOM 60d + MA200 persist-3)
- [`B2_V2_COMPARISON_FRAMEWORK_DESIGN.md`](./B2_V2_COMPARISON_FRAMEWORK_DESIGN.md) — B2 vs V2 advisory comparison framework (v3)
- [`B2_V2_COMPARISON_RESULTS.md`](./B2_V2_COMPARISON_RESULTS.md) — implementation summary + live verdict template

### V2 promotion-trigger framework (Phases 1–9)

- [`V2_PROMOTION_TRIGGER_DESIGN.md`](./V2_PROMOTION_TRIGGER_DESIGN.md) — master design (Phases 1–9, all revisions)

### Statistical validation + monitoring (Phase 10A + 10B)

- [`V2_STAT_VALIDATION_DESIGN.md`](./V2_STAT_VALIDATION_DESIGN.md) — Phase 10A: PBO / Deflated Sharpe / Bootstrap CI
- [`V2_OOS_MONITORING_DESIGN.md`](./V2_OOS_MONITORING_DESIGN.md) — Phase 10B: read-only weekly OOS report

### ML advisory design (Phase 10C.1 — NOT implemented)

- [`V2_ML_ADVISORY_DESIGN.md`](./V2_ML_ADVISORY_DESIGN.md) — design only; ML never enters execution; `ML_CAN_AFFECT_TRADES = false` permanent

### Observation phase (current)

- [`V2_OBSERVATION_VALIDATION_PLAN.md`](./V2_OBSERVATION_VALIDATION_PLAN.md) — 60–90 day OOS observation runbook
- [`observation_log/README.md`](./observation_log/README.md) — weekly review log workflow
- [`observation_log/template.md`](./observation_log/template.md) — copy-paste weekly review template
- [`observation_log/red_flag_register.md`](./observation_log/red_flag_register.md) — running red-flag register

### Background research

- [`quant-repos-extraction.md`](./quant-repos-extraction.md) — quant-repos research extraction (R1)
- [`quant-repos-extraction-v2-deep.md`](./quant-repos-extraction-v2-deep.md) — R2
- [`quant-repos-extraction-v3-empirical.md`](./quant-repos-extraction-v3-empirical.md) — R3
- [`quant-repos-extraction-v4-codewalk.md`](./quant-repos-extraction-v4-codewalk.md) — R4

---

## Options system (NEW — Phase 11A design only)

**Status:** Design only. NO source code exists yet. All implementation
gated on operator approval per phase.

### Phase 11A — architecture docs (this set)

- [`OPTIONS_SYSTEM_DESIGN.md`](./OPTIONS_SYSTEM_DESIGN.md) — master architecture
- [`OPTIONS_DATA_PROVIDER_EVAL.md`](./OPTIONS_DATA_PROVIDER_EVAL.md) — provider comparison; v1 = ThetaData
- [`OPTIONS_STRATEGY_UNIVERSE.md`](./OPTIONS_STRATEGY_UNIVERSE.md) — 3 defined-risk strategies; SPY/QQQ/IWM/GLD/TLT; 30–60 DTE
- [`OPTIONS_PAPER_TRADING_DESIGN.md`](./OPTIONS_PAPER_TRADING_DESIGN.md) — lifecycle, fills, expiration / assignment, risk snapshot
- [`OPTIONS_BOUNDARIES.md`](./OPTIONS_BOUNDARIES.md) — bidirectional grep enforcement + behavioral isolation tests for V2 separation

### Subsequent phases (NOT yet started)

| Phase | Scope | Status |
|---|---|---|
| **11B** | Schema only — `options_*` tables, ORM models, alembic `phase11_*` migrations | Pending operator approval |
| **11C** | Data ingest only — ThetaData adapter + 15-min snapshot job + liquidity filter + Greeks compute | Pending |
| **11D** | Feature engine only — IVR/IVP/term-structure/skew/VRP/PCR pure functions + nightly job | Pending |
| **11E** | Paper-trading engine — **expiration_handler + assignment_handler FIRST**; then lifecycle, fill simulator, risk snapshot; then strategies in build order | Pending |
| **11F** | WebUI — chain viewer + strategy builder + positions table + vol dashboard + expiration calendar + ML advisory sidebar | Pending |
| **11G** | OOS validation — walk-forward backtest + PBO/DSR diagnostics over accumulated paper-trade history | Pending (after ≥ 60 days OOS) |

### Octo Discover synthesis (source for Phase 11A docs)

- `~/.claude-octopus/discover/options-system-research/synthesis.md` (outside repo; reviewer transcripts in `rounds/`)

---

## Cross-domain isolation

The equity / V2 system and the options system are **deliberately isolated**:

| Surface | Equity / V2 | Options | Coupling |
|---|---|---|---|
| Source tree | `apps/api/src/research/v2_*`, `apps/api/src/api/v2_promotion.py`, etc. | `apps/api/src/options/**` | NONE |
| DB schema | `recommendation*`, `paper_trade*`, `v2_promotion_*`, `paper_shadow_log` | `options_*` | NONE (zero FKs cross-domain) |
| API namespace | `/api/v2-promotion/*`, `/api/b2-v2/*` | `/api/options/*` | NONE |
| UI route | `/ops` | `/options` | NONE |
| Settings flag (kill switch) | `ML_CAN_AFFECT_TRADES = false` permanent | `OPTIONS_PAPER_ONLY = true`, `OPTIONS_ML_CAN_AFFECT_TRADES = false`, both permanent v1 | INDEPENDENT |
| Worker jobs | `v2_promotion_snapshot` | `options_chain_snapshot`, `options_features_daily`, `options_paper_mtm_daily`, `options_expiration_check`, `options_ml_advisory_weekly` | NONE |

Bidirectional grep CI checks enforce the import-graph separation. See
`OPTIONS_BOUNDARIES.md` §3 + §4 for the complete enforcement spec.

---

## Document conventions

All design docs in this directory carry YAML frontmatter locking the
key choices (provider, libraries, strategy universe, ML scope, etc.).
Threshold or scope changes require a documented design-doc revision
plus explicit operator approval.

Convention:
- `phase: <X>` — implementation phase the doc belongs to
- `status: DESIGN ONLY | IMPLEMENTED | DEPRECATED`
- `locks: { ... }` — frozen choices (changing requires revision history entry)
- `sources: { ... }` — provenance (synthesis files, reviewer transcripts, citations)
