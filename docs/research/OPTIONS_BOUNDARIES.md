---
phase: 11A
status: DESIGN ONLY
date: 2026-04-26
locks:
  bidirectional_grep_enforcement: true
  separate_db_schema: true
  separate_api_namespace: true
  separate_ui_page: true
  options_paper_only: true
  options_ml_can_affect_trades: false
  v2_isolated_from_options: true
sources:
  synthesis: ~/.claude-octopus/discover/options-system-research/synthesis.md
  reviewers: [Codex, Gemini, Sonnet, Opus]
---

# Options System Boundaries — Hard Isolation From V2 / Equity / Live Execution

**Status:** Design only.
**Mandate:** The options system runs **side-by-side** with the existing V2 / equity / governance / execution stack with **zero semantic coupling**. This document specifies the mechanical enforcement: grep invariants, behavioral isolation tests, schema/API/UI separation rules, and CI gates.

---

## 1. Mandate

| Constraint | Enforcement |
|---|---|
| No options module imports any V2 / equity / execution code | Grep CI (§3.1) |
| No V2 / equity / execution code imports any options module | Grep CI (§3.2) |
| No options data ever flows into V2 governance | Schema FK invariant + integration test |
| No V2 governance state ever flows into options | Schema FK invariant + integration test |
| No options ML output ever reaches options trade-decision path | Mirror Phase 10C.1 discipline; grep CI (§3.3) |
| ML_CAN_AFFECT_TRADES (equity) stays false | Existing equity invariant; not weakened by options |
| OPTIONS_PAPER_ONLY (options) stays true v1 | New invariant; permanent v1 |
| OPTIONS_ML_CAN_AFFECT_TRADES stays false v1 | New invariant; permanent v1 |

---

## 2. Architectural separation

### 2.1 Source-tree separation

```
apps/api/src/options/                  ← all options Python code; SEPARATE from existing modules
apps/worker/src/jobs/options_*         ← all options worker jobs
apps/web/src/pages/Options.tsx         ← single new page route /options
apps/web/src/components/options/       ← all options UI components
apps/web/src/lib/options/              ← all options frontend hooks / types
infra/alembic/versions/phase11_*       ← all options migrations; phase11 prefix distinguishes from V2 (phase9 / phase10 / 045 / 046)
```

**No file outside these paths may belong to the options system.**
**No file inside these paths may import from any V2 / equity / execution module.**

### 2.2 Database-schema separation

All options tables prefixed `options_*`:
- `options_chain` — snapshot per `(snapshot_at, underlying, expiry, strike, right)`
- `options_features` — daily computed features per underlying
- `options_paper_trade` — multi-leg trade header
- `options_paper_trade_leg` — per-leg detail
- `options_paper_trade_event` — append-only state-transition log
- `options_risk_snapshot` — daily per-trade Greeks + MTM
- `options_portfolio_risk_snapshot` — daily aggregate
- `options_ml_prediction` — ML advisory output (display-only)

**Hard invariants (Phase 11B migration must enforce):**
- ZERO foreign keys from any `options_*` table to any non-`options_*` table
- ZERO foreign keys from any non-`options_*` table to any `options_*` table
- Migration verification SQL (run in CI):
  ```sql
  SELECT confrelid::regclass AS referenced, conname
  FROM pg_constraint
  WHERE contype = 'f'
    AND (
      (conrelid::regclass::text LIKE 'options_%' AND confrelid::regclass::text NOT LIKE 'options_%')
      OR
      (conrelid::regclass::text NOT LIKE 'options_%' AND confrelid::regclass::text LIKE 'options_%')
    );
  -- expected: 0 rows
  ```

### 2.3 API separation

- All options endpoints mounted under `/api/options/*`
- Router file: `apps/api/src/api/options/*.py`
- Router NEVER co-included in same `include_router` call as V2 routers
- Existing V2 `/api/v2-promotion/*` and `/api/b2-v2/*` namespaces unchanged

### 2.4 UI separation

- Single new page route `/options` (separate from existing `/ops`)
- Component tree under `apps/web/src/components/options/` only
- No options UI components mounted on V2 governance pages
- No V2 UI components mounted on options page
- ML advisory panel on options page is independent of equity ML advisory design (each domain has its own prediction surface)

---

## 3. Grep invariants (CI enforcement)

The following greps run in CI on every PR. **Any non-zero match fails the build.**

### 3.1 Options modules MUST NOT import V2 / equity / execution

```bash
git grep -E "engine_a|engine_b|b2_v2_comparison|v2_promotion_gates|v2_promotion_state|v2_promotion(?!_snapshot)\b|v2_promotion_snapshot|v2_oos_monitoring|v2_stat_validation|paper_trade_log|decision_log|paper_shadow_log|run_v2_promotion_snapshot|engine_b_router|engine_b_promotion|engine_b_decision|engine_b_analytics|shadow_strategy" \
    apps/api/src/options/ \
    apps/worker/src/jobs/options_*.py
# expected: 0 matches
```

Allowed exceptions: docstring mentions of "separate from V2" type statements
(no import lines; verified by also requiring imports-only check):

```bash
git grep -E "^(from|import).*\b(engine_a|engine_b|v2_promotion|b2_v2_comparison|v2_oos_monitoring|v2_stat_validation|paper_trade_log|decision_log|paper_shadow_log|shadow_strategy)" \
    apps/api/src/options/
# expected: 0 matches
```

### 3.2 V2 / equity / execution modules MUST NOT import options

```bash
git grep -E "^(from|import).*\boptions\.|apps\.api\.src\.options" \
    apps/api/src/research/v2_promotion_gates.py \
    apps/api/src/research/v2_promotion_state.py \
    apps/api/src/research/b2_v2_comparison.py \
    apps/api/src/research/v2_oos_monitoring.py \
    apps/api/src/research/v2_stat_validation.py \
    apps/api/src/api/v2_promotion.py \
    apps/api/src/api/b2_v2_comparison.py \
    apps/api/src/api/engine_b_transition.py \
    apps/worker/src/jobs/v2_promotion_snapshot.py
# expected: 0 matches
```

### 3.3 Options ML output MUST NOT reach options trade-decision path

```bash
git grep -E "ml_advisory|ml_inference|ml_model|vol_regime_classifier|skew_alert_classifier|MLAdvisory" \
    apps/api/src/options/strategies/ \
    apps/api/src/options/paper/ \
    apps/api/src/api/options/paper_trades.py \
    apps/api/src/api/options/strategies.py
# expected: 0 matches
```

### 3.4 Forbidden v1 strategies and feature flags

```bash
# No naked-short patterns
git grep -E "naked|sell_naked|short_naked|undefined_risk" apps/api/src/options/strategies/
# expected: 0 matches

# No 0DTE references
git grep -E "0dte|zero_dte|zerodte" apps/api/src/options/strategies/
# expected: 0 matches

# No DL/RL libraries
git grep -E "torch|tensorflow|jax|flax|stable_baselines|gymnasium" apps/api/src/options/
# expected: 0 matches

# OPTIONS_PAPER_ONLY flag remains true
grep -E "OPTIONS_PAPER_ONLY\s*[:=]\s*True" apps/api/src/config/__init__.py
# expected: ≥ 1 match
grep -E "OPTIONS_PAPER_ONLY\s*[:=]\s*False" apps/api/src/config/__init__.py
# expected: 0 matches

# OPTIONS_ML_CAN_AFFECT_TRADES flag remains false
grep -E "OPTIONS_ML_CAN_AFFECT_TRADES\s*[:=]\s*False" apps/api/src/config/__init__.py
# expected: ≥ 1 match
grep -E "OPTIONS_ML_CAN_AFFECT_TRADES\s*[:=]\s*True" apps/api/src/config/__init__.py
# expected: 0 matches
```

### 3.5 No last-price fills

```bash
git grep -E "fill.*last_price|last_price.*fill|last_traded.*as_fill|fill_at_last" \
    apps/api/src/options/paper/
# expected: 0 matches
```

### 3.6 Banned ML validation idioms (mirror Phase 10C.1)

```bash
git grep -E "KFold|train_test_split|StratifiedKFold|shuffle\s*=\s*True|cross_val_score" \
    apps/api/src/options/ml_advisory/
# expected: 0 matches (all validation must use prequential / walk-forward)
```

### 3.7 No ad-hoc raw-SQL reads of equity tables from options code

```bash
git grep -E "FROM (paper_trade|decision_log|paper_shadow_log|recommendation|paper_position|engine_b_decision_snapshot|v2_promotion_snapshot|v2_promotion_approval)" \
    apps/api/src/options/
# expected: 0 matches
```

### 3.8 Adapter abstraction holds

```bash
# Outside the provider adapter directory, NO references to ThetaData specifics
git grep -E "thetadata|theta_data|thdata" \
    apps/api/src/options/ \
    | grep -v "apps/api/src/options/data/providers/"
# expected: 0 matches (provider names live only inside adapter)
```

---

## 4. Behavioral isolation tests (Python)

Implemented in Phase 11B+:

`apps/api/tests/unit/test_options_isolation.py`:

```python
def test_options_modules_do_not_import_v2_or_equity():
    """Inverse of grep §3.1 — actual import-graph walk."""
    import importlib, sys
    before = set(sys.modules)
    importlib.import_module("src.options.paper.lifecycle")
    importlib.import_module("src.options.strategies.short_put_credit_spread")
    importlib.import_module("src.options.api.paper_trades")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation",
        "engine_a", "engine_b", "b2_v2_comparison",
        "shadow_strategy", "paper_trade_log", "decision_log",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), f"forbidden {f} via options"


def test_v2_modules_do_not_import_options():
    """Inverse of grep §3.2."""
    import importlib, sys
    before = set(sys.modules)
    importlib.import_module("src.research.v2_promotion_gates")
    importlib.import_module("src.research.v2_promotion_state")
    importlib.import_module("src.research.v2_oos_monitoring")
    importlib.import_module("src.research.v2_stat_validation")
    after = set(sys.modules)
    new_modules = after - before
    assert not any("options" in m for m in new_modules)


def test_options_ml_advisory_does_not_import_strategies_or_paper():
    """ML advisory is read-only; never depends on trade-decision modules."""
    import importlib, sys
    before = set(sys.modules)
    importlib.import_module("src.options.ml_advisory.vol_regime_classifier")
    importlib.import_module("src.options.ml_advisory.skew_alert_classifier")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = ("strategies.short_put_credit_spread",
                  "strategies.short_call_credit_spread",
                  "strategies.iron_condor",
                  "paper.lifecycle", "paper.fill_simulator",
                  "paper.expiration_handler", "paper.assignment_handler")
    for f in forbidden:
        assert not any(f in m for m in new_modules), f"ML reaches {f}"


def test_options_paper_only_flag_is_true():
    from src.config import settings
    assert settings.OPTIONS_PAPER_ONLY is True


def test_options_ml_can_affect_trades_flag_is_false():
    from src.config import settings
    assert settings.OPTIONS_ML_CAN_AFFECT_TRADES is False


def test_advisory_only_disclaimer_in_every_options_ml_prediction():
    from src.options.ml_advisory.vol_regime_classifier import predict
    from src.options.ml_advisory.skew_alert_classifier import predict as skew_predict
    for fn in (predict, skew_predict):
        out = fn(features=DUMMY_FEATURES)
        assert out["advisory_only"] is True
        assert out["is_used_in_decisions"] is False
        assert out["warning"] == "ML advisory — not used in decisions"
```

`apps/api/tests/integration/test_options_db_isolation.py`:

```python
def test_zero_foreign_keys_between_options_and_non_options(pg_session):
    rows = pg_session.execute(text("""
        SELECT conrelid::regclass::text AS source_tbl,
               confrelid::regclass::text AS target_tbl,
               conname
          FROM pg_constraint
         WHERE contype = 'f'
           AND ((conrelid::regclass::text LIKE 'options_%'
                  AND confrelid::regclass::text NOT LIKE 'options_%')
                 OR
                (conrelid::regclass::text NOT LIKE 'options_%'
                  AND confrelid::regclass::text LIKE 'options_%'))
    """)).fetchall()
    assert rows == [], f"cross-domain FK leak: {rows}"
```

---

## 5. Configuration / settings invariants

```python
# apps/api/src/config/__init__.py — new options-related settings
class Settings(BaseSettings):
    ...
    # Options system flags (NEW — Phase 11B)
    OPTIONS_ENABLED: bool = False                  # opt-in per env
    OPTIONS_PAPER_ONLY: bool = True                # PERMANENT v1
    OPTIONS_ML_CAN_AFFECT_TRADES: bool = False     # PERMANENT v1
    OPTIONS_DATA_PROVIDER: str = "thetadata"
    OPTIONS_SNAPSHOT_INTERVAL_MINUTES: int = 15
    OPTIONS_DEFAULT_FILL_MODEL: str = "mid_plus_25_pct_spread"
```

**Forbidden:** any code path that:
- Sets `OPTIONS_PAPER_ONLY = False`
- Sets `OPTIONS_ML_CAN_AFFECT_TRADES = True`
- Sets equity-side `ML_CAN_AFFECT_TRADES = True`

Each is a single-flag kill switch; tests verify they remain hardcoded
to safe values.

---

## 6. Risk register (boundary-specific)

| Risk | Severity | Mitigation |
|---|---|---|
| Developer adds an `engine_b` import in options module to "reuse logic" | High | Grep §3.1 catches in CI |
| Developer adds an `options.*` import in V2 module to "share Greeks compute" | High | Grep §3.2 catches in CI |
| Developer adds FK from `options_paper_trade` to `paper_trade` to "link options to underlying equity position" | High | Migration FK invariant SQL §2.2 + integration test §4 |
| Developer wires options ML output into strategy_screener "advisory tweak" | High | Grep §3.3 catches in CI |
| Developer flips `OPTIONS_PAPER_ONLY` to False to enable "live testing" | CRITICAL | Settings invariant §5 + integration test §4; PR review must catch |
| Provider API quirks leak into ingest job (ThetaData-specific field names) | Medium | Adapter abstraction §3.8 grep |
| Operator confuses options paper P&L with equity paper P&L in dashboard | Medium | Separate UI page, separate visual treatment, prefix all P&L labels with "Options:" |
| Schema migration accidentally drops or renames an equity table while adding options tables | High | Phase 11B migration uses `op.create_table` only on `options_*`; no `op.drop_table` or `op.alter_column` on existing equity tables |
| Options worker job consumes V2 snapshot data thinking it's a generic input | Medium | Worker job grep §3.1 + per-job docstring stating data source |

---

## 7. Verification matrix (Phase 11B+ acceptance)

| Check | Source | Pass criterion |
|---|---|---|
| Grep §3.1 (options → V2/equity imports) | CI | 0 matches |
| Grep §3.2 (V2/equity → options imports) | CI | 0 matches |
| Grep §3.3 (options ML → trade-decision path) | CI | 0 matches |
| Grep §3.4 (kill switches preserved) | CI | True flag exists, False flag absent (per direction) |
| Grep §3.5 (no last-price fills) | CI | 0 matches |
| Grep §3.6 (no banned ML validation) | CI | 0 matches |
| Grep §3.7 (no raw-SQL reads of equity tables from options) | CI | 0 matches |
| Grep §3.8 (provider adapter abstraction) | CI | 0 matches outside adapter dir |
| Behavioral §4 — `test_options_modules_do_not_import_v2_or_equity` | pytest unit | passes |
| Behavioral §4 — `test_v2_modules_do_not_import_options` | pytest unit | passes |
| Behavioral §4 — `test_options_ml_advisory_does_not_import_strategies_or_paper` | pytest unit | passes |
| Behavioral §4 — `test_options_paper_only_flag_is_true` | pytest unit | passes |
| Behavioral §4 — `test_options_ml_can_affect_trades_flag_is_false` | pytest unit | passes |
| Behavioral §4 — `test_advisory_only_disclaimer_in_every_options_ml_prediction` | pytest unit | passes |
| Behavioral §4 — `test_zero_foreign_keys_between_options_and_non_options` | pytest integration | passes |

All 14 checks must pass before any Phase 11B+ PR merges.

---

## 8. Ongoing enforcement

- CI runs all greps + behavioral tests on every PR (gate)
- Quarterly review: re-run all greps against `main` to detect drift
- Any change to flag values (`OPTIONS_PAPER_ONLY`, `OPTIONS_ML_CAN_AFFECT_TRADES`) requires:
  1. Separate design doc revision
  2. Explicit operator approval recorded in design-doc revision history
  3. Migration of permanent kill switch is impossible v1; would require new design phase

`STOP. Awaiting operator approval of full Phase 11A doc set.`
