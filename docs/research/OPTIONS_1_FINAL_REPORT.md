# Phase Options-1 — Options paper-trading shadow evaluator (final report)

**Status:** implementation complete, pending commit
**Built on:** Phase 11X.2 (`b83c0e5`) base
**Scope:** read-only diagnostic that decides "would the options
system have found a paper-tradable contract today?" without ever
opening an options or paper trade.

---

## 1. Goal

Answer one question per run_date:

> Did the options data + filter chain produce at least one
> contract that *would* have qualified for a paper trade?

Persist the answer to a single append-only diagnostic table.
NEVER open a real `options_paper_trade`, `paper_trade`, or
`paper_position` row. NEVER schedule itself. NEVER touch
trading / scoring / candidate-generation paths.

## 2. Files in the bundle

| File | Type |
|---|---|
| `infra/alembic/versions/056_options_shadow_decision_log.py` | NEW migration — `options_shadow_decision_log` table |
| `apps/api/src/options/shadow_evaluator.py` | NEW evaluator module (deterministic filter chain + persister) |
| `apps/api/src/api/options_shadow.py` | NEW GET-only API: `/options/shadow/{summary,runs,runs/:date}` |
| `scripts/run_options_shadow_eval.py` | NEW CLI runner (default dry-run; `--commit` requires env flag) |
| `apps/api/tests/integration/test_options_shadow_eval_pg.py` | NEW integration suite (12 tests) |
| `docs/research/OPTIONS_1_FINAL_REPORT.md` | NEW (this doc) |

NOT changed:
- `apps/worker/src/` — no scheduler entry, no worker registry entry.
- `apps/api/src/data/strategy/` — no engine A/B / paper / selector wiring.
- `apps/api/src/data/features/` — no macro gate / candidate scoring change.
- `apps/api/src/api/main.py` — already imports `options_shadow_router`
  (committed in `3ec55de` as part of the E/E.1/E.2 bundle); the
  router's actual implementation lands here.

The Options-1 Settings block (7 knobs, all default-off) was already
committed as part of `3ec55de` as "dead defaults until Options-1
code lands." This commit completes that contract.

## 3. Schema (migration 056)

```
public.options_shadow_decision_log
  id                 bigint identity PK
  run_date           date NOT NULL
  underlying_symbol  text NOT NULL
  option_symbol      text NOT NULL
  expiration         date NOT NULL
  strike             numeric(12,4) NOT NULL
  option_type        text  CHECK ∈ {call, put}
  side               text  CHECK ∈ {buy, sell}
  strategy_name      text NOT NULL
  would_trade        boolean NOT NULL
  reason             text NOT NULL
  liquidity_pass     boolean NOT NULL
  spread_pass        boolean NOT NULL
  open_interest_pass boolean NOT NULL
  volume_pass        boolean NOT NULL
  greeks_pass        boolean NOT NULL
  iv_rank_pass       boolean NOT NULL
  risk_pass          boolean NOT NULL
  score              numeric(20,6)
  diagnostics        jsonb (default '{}')
  created_at         timestamptz default now()

  Indexes:
    ux_options_shadow_run_option   UNIQUE (run_date, option_symbol)
    ix_options_shadow_run_date     (run_date DESC)
    ix_options_shadow_would_trade  (would_trade, run_date DESC)
    ix_options_shadow_underlying   (underlying_symbol, run_date DESC)
```

Append-only by convention (idempotent INSERT via UNIQUE; no
UPDATE/DELETE writers).

## 4. Filter chain (deterministic)

For each `options_chain_snapshot` row at `run_date`, with the
matching `options_feature_daily` row when available:

| Filter | Rule | Threshold |
|---|---|---|
| liquidity | bid ≥ MIN_BID, ask > bid | `OPTIONS_SHADOW_MIN_BID` |
| spread | ask − bid ≤ MAX_SPREAD | `OPTIONS_SHADOW_MAX_SPREAD` |
| open_interest | OI ≥ MIN_OPEN_INTEREST | `OPTIONS_SHADOW_MIN_OPEN_INTEREST` |
| volume | volume present and ≥ 0 | (soft check) |
| dte | DTE ∈ [MIN_DTE, MAX_DTE] | `OPTIONS_SHADOW_MIN_DTE`/`MAX_DTE` |
| greeks | delta+gamma+iv present, OR feature row falls back | (graceful) |
| iv_rank | iv_rank_252d present OR chain iv present | (graceful) |
| risk | abs(delta) ≤ 0.95 when present | hardcoded |

`would_trade=True` iff every filter passes. Reason carries the
first failing filter name (`blocked:<filter>`). Top-N per
underlying capped at `OPTIONS_SHADOW_TOP_N`; overflow rows are
re-marked `blocked:top_n_capped` for audit.

## 5. Defaults

```
OPTIONS_SHADOW_EVAL_ENABLED         = False    # required for --commit
OPTIONS_SHADOW_MIN_OPEN_INTEREST    = 500
OPTIONS_SHADOW_MAX_SPREAD           = 0.10
OPTIONS_SHADOW_MIN_BID              = 0.01
OPTIONS_SHADOW_MIN_DTE              = 7
OPTIONS_SHADOW_MAX_DTE              = 45
OPTIONS_SHADOW_TOP_N                = 5
```

Already committed as dead defaults in `3ec55de`. This commit
makes them functional.

## 6. CLI runner

```
python -m scripts.run_options_shadow_eval --date 2026-04-29 [--underlying SPY] [--dry-run|--commit]
```

`--commit` requires `OPTIONS_SHADOW_EVAL_ENABLED=true` (else
exit 2). Default is `--dry-run`. Output is JSON with run summary,
underlying count, contracts evaluated, would_trade count, blocked
reason counts, freshness warnings, top-N would_trade candidates.

## 7. GET-only API

| Method | Path |
|---|---|
| GET | `/api/options/shadow/summary` |
| GET | `/api/options/shadow/runs?limit=N` |
| GET | `/api/options/shadow/runs/{run_date}` |

Zero POST/PUT/PATCH/DELETE. Mounted under `/api` from main.py
unconditionally (the router's GET-only nature is the safety
boundary; no flag gates mounting).

## 8. Tests

| Suite | Count | Result |
|---|---|---|
| `test_options_shadow_eval_pg.py` | 12 | 12 passed |

Coverage:
- migration UNIQUE + CHECK constraints active
- `option_type='banana'` rejected by CHECK
- evaluator never writes to `options_paper_trade`, `paper_trade`,
  `paper_position`
- clean chain → 1 `would_trade=True` row with all filter passes
- bad spread blocks
- low OI blocks
- DTE out-of-range blocks
- missing greeks + present feature row passes (fallback)
- missing greeks + missing feature row blocks
- idempotent rerun (UNIQUE → 0 new rows on second call)
- `persist=False` path skips all writes
- stock paper tables untouched (paper_portfolio / paper_trade /
  paper_position deltas all zero)

## 9. Safety guarantees

| Property | Status |
|---|---|
| GET-only API | ✅ |
| Append-only writes via INSERT ... ON CONFLICT | ✅ |
| No writes to options_paper_trade / paper_trade / paper_position | ✅ (live test asserts) |
| No scheduler entry | ✅ |
| No worker registry entry | ✅ |
| No imports from execution/scoring/ML/candidate modules | ✅ |
| No reflection feedback | ✅ |
| No POST in API surface | ✅ |
| Runner default dry-run | ✅ (commit requires env flag) |
| Idempotent re-run | ✅ (UNIQUE on `(run_date, option_symbol)`) |
| Universal forbidden-token sanitization | n/a — Options-1 stores numerical data only, no model body |

## 10. Why the bundle was deferred

Implementation completed mid-session, but a higher-priority audit
pivot (Research Intelligence layer audit) interrupted the commit
step. The Options-1 settings block landed in `3ec55de` as dead
defaults; main.py landed referencing the import. This commit
finishes the contract by landing the actual module + tests + doc.

## 11. Rollback

| Step | Effect |
|---|---|
| `OPTIONS_SHADOW_EVAL_ENABLED=false` (default) + restart | CLI refuses `--commit`; evaluator can still be invoked with `persist=False` for dry-run |
| `alembic downgrade 055_phase_11z_macro_unk` | drops `options_shadow_decision_log` table; preserves all other research_ro tables |
| **No trading impact at any step.** | — |
| **No scheduler impact at any step.** | — |

## 12. Final safety verdict

**SAFE.** Diagnostic-only. Default-off. GET-only API. No execution
surface. No scheduler. No worker. No reflection feedback.
Idempotent. Migration appends one table to public schema; rollback
trivial.

Bundle ready to commit — landing it removes the latent import
error in `main.py` (where `options_shadow_router` is referenced
but the module file is currently untracked).
