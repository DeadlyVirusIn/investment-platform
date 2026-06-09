"""Phase G2 — options portfolio DETAIL endpoint contract tests.

Pins the read-only response shape the OptionsPortfolio detail UI binds to,
the SHORT_PUT_CREDIT_SPREAD setup explanation, GET-only routing, and that the
detail service contains no writes (display-only, reuses MTM/decide_exit).
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path("apps/api/src/options/portfolio/detail.py")


def test_module_imports():
    import apps.api.src.options.portfolio.detail as mod  # noqa: F401


def test_setup_explanation_covers_spcs():
    from apps.api.src.options.portfolio.detail import SETUP_EXPLANATIONS
    s = SETUP_EXPLANATIONS["SHORT_PUT_CREDIT_SPREAD"]
    for k in ("summary", "max_profit", "max_loss", "profit_when", "risk_when"):
        assert s.get(k), f"setup missing {k}"
    assert "higher-strike put" in s["summary"]
    assert "lower-strike put" in s["summary"]


def test_portfolio_summary_keys_pinned():
    src = _SRC.read_text(encoding="utf-8")
    for key in (
        '"cash"', '"reserved_capital"', '"open_positions"',
        '"capital_at_risk"', '"max_profit"', '"unrealized_pnl"',
        '"realized_pnl"', '"buying_power"',
    ):
        assert key in src, f"portfolio summary missing {key}"


def test_position_and_leg_keys_pinned():
    src = _SRC.read_text(encoding="utf-8")
    for key in (
        # position
        '"entry_credit"', '"current_cost_to_close"', '"unrealized_pnl_pct"',
        '"captured_pct"', '"max_loss"', '"lifecycle"', '"setup"', '"legs"',
        '"opened_at"', '"dte"', '"status"',
        # leg
        '"side"', '"strike"', '"option_type"', '"entry_fill_price"',
        '"bid"', '"ask"', '"mid"', '"open_interest"', '"spread"',
        '"quote_age_seconds"', '"leg_pnl"',
        # lifecycle
        '"action"', '"tp_threshold_pct"', '"dte_management_days"',
    ):
        assert key in src, f"detail response missing {key}"


def test_detail_route_registered_get_only():
    from apps.api.src.options.routes_readonly import router
    by_path: dict[str, set] = {}
    for r in router.routes:
        by_path.setdefault(getattr(r, "path", ""), set()).update(
            getattr(r, "methods", set()) or set())
    path = "/options/portfolio/detail"   # router prefix=/options
    assert path in by_path, f"detail route not registered; have {sorted(by_path)}"
    assert by_path[path] <= {"GET", "HEAD", "OPTIONS"}


def test_no_writes_in_detail_source():
    src = _SRC.read_text(encoding="utf-8")
    for pat in (
        r"\bINSERT\s+INTO\b", r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\s+FROM\b",
    ):
        assert not re.search(pat, src, re.IGNORECASE), f"write found: {pat}"
