"""Phase 11O - safety + boundary tests for the manual options paper
evaluation runner.

Static + behaviour assertions verifying:
  * no live/broker/execution imports
  * REGISTRY drift detection works
  * kill-switch invariants enforced
  * dry-run XOR commit invariant
  * max_open bounds
  * no recommendation language in user-facing rendered output
"""

from __future__ import annotations

import datetime
import re
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.api.src.options.paper import eval_runner
from apps.api.src.options.paper.eval_runner import (
    EvalRunnerSafetyError,
    FORBIDDEN_MODULE_PATTERNS,
    FROZEN_REGISTRY_KEYS,
    assert_no_scheduler_drift,
    assert_safety_invariants,
)
from apps.api.src.options.paper.eval_runner_models import (
    PlannedTrade,
    RunnerConfig,
    RunnerSummary,
)
from apps.api.src.options.paper.strategies import (
    LegSpec,
    RiskMetrics,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_settings(**overrides) -> SimpleNamespace:
    base = dict(
        OPTIONS_ENABLED=True,
        OPTIONS_PAPER_ONLY=True,
        OPTIONS_ML_CAN_AFFECT_TRADES=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _config(**overrides) -> RunnerConfig:
    base = dict(
        date=datetime.date(2026, 4, 27),
        underlyings=("SPY",),
        strategy_filter=None,
        dry_run=True,
        commit=False,
        max_open=5,
        explain=False,
        skip_ingest=False,
    )
    base.update(overrides)
    return RunnerConfig(**base)


# ---------------------------------------------------------------------------
# Static source scans
# ---------------------------------------------------------------------------

def test_runner_imports_no_live_modules():
    src = Path(eval_runner.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "from apps.api.src.live_",
        "from apps.api.src.broker_",
        "from apps.api.src.execution_",
        "import broker_",
        "import live_",
        "from broker_",
        "from live_",
        "from execution_",
        "order_router",
    ):
        # `order_router` legitimately appears inside the regex pattern
        # itself, so allow only that one occurrence (the regex literal).
        if forbidden == "order_router":
            assert src.count(forbidden) <= 1, (
                f"forbidden token {forbidden!r} appears more than the "
                f"single allowed regex literal"
            )
            continue
        assert forbidden not in src, f"forbidden import token {forbidden!r}"


def test_runner_module_makes_no_alembic_writes():
    src = Path(eval_runner.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "from alembic",
        "import alembic",
        "op.create_table",
        "op.execute",
        "INSERT INTO job_schedule",
    ):
        assert forbidden not in src, f"unexpected reference {forbidden!r}"


def test_runner_module_does_not_register_into_REGISTRY():
    """Existing REGISTRY must not contain any options job; runner is
    manual-only by contract."""
    from apps.worker.src.jobs.registry import REGISTRY
    assert all("options" not in k.lower() for k in REGISTRY.keys()), (
        f"REGISTRY contains options job: "
        f"{[k for k in REGISTRY if 'options' in k.lower()]}"
    )


def test_frozen_registry_keys_match_actual_registry():
    """Snapshot must equal the current REGISTRY exactly."""
    from apps.worker.src.jobs.registry import REGISTRY
    assert frozenset(REGISTRY.keys()) == FROZEN_REGISTRY_KEYS


def test_frozen_registry_does_not_contain_options_jobs():
    for k in FROZEN_REGISTRY_KEYS:
        assert "options" not in k.lower()


# ---------------------------------------------------------------------------
# Kill-switch / safety invariants
# ---------------------------------------------------------------------------

def test_assert_safety_fails_when_options_enabled_false():
    with pytest.raises(EvalRunnerSafetyError, match="OPTIONS_ENABLED"):
        assert_safety_invariants(_ok_settings(OPTIONS_ENABLED=False))


def test_assert_safety_fails_when_paper_only_false():
    with pytest.raises(EvalRunnerSafetyError, match="OPTIONS_PAPER_ONLY"):
        assert_safety_invariants(_ok_settings(OPTIONS_PAPER_ONLY=False))


def test_assert_safety_fails_when_ml_can_affect_trades_true():
    with pytest.raises(
        EvalRunnerSafetyError, match="OPTIONS_ML_CAN_AFFECT_TRADES",
    ):
        assert_safety_invariants(
            _ok_settings(OPTIONS_ML_CAN_AFFECT_TRADES=True),
        )


def test_assert_safety_blocks_live_broker_module_in_sys_modules(monkeypatch):
    monkeypatch.setitem(sys.modules, "broker_fakeclient", object())
    with pytest.raises(EvalRunnerSafetyError, match="forbidden module"):
        assert_safety_invariants(_ok_settings())


def test_assert_safety_blocks_live_module_pattern(monkeypatch):
    monkeypatch.setitem(sys.modules, "live_orders", object())
    with pytest.raises(EvalRunnerSafetyError, match="forbidden module"):
        assert_safety_invariants(_ok_settings())


def test_assert_safety_ignores_unrelated_live_render(monkeypatch):
    """Third-party UI libs whose nested module names contain 'live_'
    must NOT trigger the safety block — patterns are top-level only."""
    monkeypatch.setitem(sys.modules, "rich.live_render", object())
    # Should not raise.
    assert_safety_invariants(_ok_settings())


# ---------------------------------------------------------------------------
# Scheduler drift
# ---------------------------------------------------------------------------

def test_no_scheduler_drift_baseline():
    """Real REGISTRY must match frozen snapshot — clean baseline."""
    assert_no_scheduler_drift()


def test_no_scheduler_drift_detects_added_options_job(monkeypatch):
    from apps.worker.src.jobs import registry as registry_mod

    fake = dict(registry_mod.REGISTRY)
    fake["options_paper_eval"] = (lambda: None)  # type: ignore[assignment]
    monkeypatch.setattr(registry_mod, "REGISTRY", fake)

    with pytest.raises(EvalRunnerSafetyError):
        assert_no_scheduler_drift()


def test_no_scheduler_drift_detects_removed_key(monkeypatch):
    from apps.worker.src.jobs import registry as registry_mod

    fake = dict(registry_mod.REGISTRY)
    # Remove an arbitrary frozen key to simulate drift
    fake.pop("v2_promotion_snapshot", None)
    monkeypatch.setattr(registry_mod, "REGISTRY", fake)

    with pytest.raises(EvalRunnerSafetyError, match="REGISTRY drift"):
        assert_no_scheduler_drift()


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------

def test_dry_run_xor_commit_invariant():
    with pytest.raises(ValueError, match="mutually exclusive"):
        _config(dry_run=True, commit=True)
    with pytest.raises(ValueError, match="mutually exclusive"):
        _config(dry_run=False, commit=False)


def test_max_open_cap_within_bounds():
    for bad in (0, -1, 26, 100):
        with pytest.raises(ValueError, match="max_open"):
            _config(max_open=bad)
    for ok in (1, 5, 25):
        assert _config(max_open=ok).max_open == ok


def test_underlyings_must_be_nonempty():
    with pytest.raises(ValueError, match="underlyings"):
        _config(underlyings=())


# ---------------------------------------------------------------------------
# No-recommendations language in rendered user-facing output
# ---------------------------------------------------------------------------

def _render_sample_summary(*, commit: bool) -> str:
    """Build a synthetic RunnerSummary and render via the CLI module."""
    from scripts import run_options_paper_eval as cli

    expiry = datetime.date(2026, 6, 18)
    legs = (
        LegSpec(
            side="SELL", option_type="PUT", strike=Decimal("440"),
            expiry=expiry, qty=1, option_symbol="SPY260618P00440000",
        ),
        LegSpec(
            side="BUY", option_type="PUT", strike=Decimal("435"),
            expiry=expiry, qty=1, option_symbol="SPY260618P00435000",
        ),
    )
    risk = RiskMetrics(
        max_loss_dollars=Decimal("388.00"),
        max_profit_dollars=Decimal("112.00"),
        breakeven_lower=Decimal("438.88"),
        breakeven_upper=None,
    )
    p = PlannedTrade(
        observation_id="SPY:2026-04-27:SHORT_PUT_CREDIT_SPREAD",
        underlying="SPY",
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        legs=legs, risk=risk,
        entry_credit_dollars=Decimal("112.00"),
        quote_age_max_seconds=2,
        rejection_reasons=(), qualified=True,
    )
    cfg = _config(commit=commit, dry_run=not commit)
    summary = RunnerSummary(
        config=cfg,
        n_chain_inserted=812, n_observations_total=14,
        n_qualified=1, n_planned=1, n_planned_rejected=0,
        n_existing_open_trade_dedup=0,
        n_committed=(1 if commit else 0),
        planned_trades=(p,),
        committed_trade_ids=(((1042,) if commit else ())),
    )
    return cli._render(summary)


_FORBIDDEN_RENDER_PATTERNS = (
    r"\brecommend\w*",
    r"\bsignals?\b",
    r"\bbest\s+trade\b",
    r"\btop\s+pick\b",
    r"\bauto-?trade\b",
    r"\btrade\s+now\b",
    r"\bplace\s+order\b",
    r"\bpromote\b",
)


def test_no_recommendations_language_in_user_facing_strings_dryrun():
    rendered = _render_sample_summary(commit=False)
    for pat in _FORBIDDEN_RENDER_PATTERNS:
        assert not re.search(pat, rendered, flags=re.IGNORECASE), (
            f"forbidden render token {pat!r} in dry-run output"
        )


def test_no_recommendations_language_in_user_facing_strings_commit():
    rendered = _render_sample_summary(commit=True)
    for pat in _FORBIDDEN_RENDER_PATTERNS:
        assert not re.search(pat, rendered, flags=re.IGNORECASE), (
            f"forbidden render token {pat!r} in commit output"
        )
