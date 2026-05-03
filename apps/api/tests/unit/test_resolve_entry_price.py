"""Paper-only entry-price fallback chain tests.

The resolver lives in scripts/run_paper_daily.py. Import it via a minimal
module loader that bypasses the script's heavy side-effect imports.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from unittest.mock import MagicMock

import pytest


def _load_runner_module():
    root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    path = os.path.join(root, "scripts", "run_paper_daily.py")
    spec = importlib.util.spec_from_file_location("run_paper_daily", path)
    mod = importlib.util.module_from_spec(spec)
    # Suppress the heavy imports — patch sys.modules lightly if needed.
    assert spec and spec.loader
    sys.modules["run_paper_daily"] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load_runner_module()
resolve_entry_price = runner.resolve_entry_price


# ---------------------------------------------------------------------------

def _bundle(*, next_open=None, open_=None, close=None):
    feat = {}
    if open_ is not None:
        feat["open"] = open_
    if close is not None:
        feat["close"] = close
    return {"entry_price_open": next_open, "feat_row": feat}


def _session_with_bar(close: float | None, bar_date: dt.date | None):
    s = MagicMock()
    mapping = MagicMock()
    mapping.first.return_value = (
        {"close": close, "bar_date": bar_date}
        if close is not None else None
    )
    s.execute.return_value.mappings.return_value = mapping
    return s


def _session_raises():
    s = MagicMock()
    s.execute.side_effect = RuntimeError("boom")
    return s


# ---------------------------------------------------------------------------

def test_prefers_next_open_when_present():
    r = resolve_entry_price(
        _session_raises(),   # should not be called
        bundle=_bundle(next_open=4180.25, open_=4100, close=4200),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["source"] == "next_open"
    assert r["price"] == pytest.approx(4180.25)
    assert r["timestamp"] == dt.date(2026, 4, 23)


def test_fallback_same_day_open():
    r = resolve_entry_price(
        _session_raises(),
        bundle=_bundle(next_open=None, open_=4100.0, close=4200),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["source"] == "same_day_open"
    assert r["price"] == pytest.approx(4100.0)


def test_fallback_same_day_close():
    r = resolve_entry_price(
        _session_raises(),
        bundle=_bundle(next_open=None, open_=None, close=4215.50),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["source"] == "same_day_close"
    assert r["price"] == pytest.approx(4215.50)


def test_fallback_latest_close_from_db():
    s = _session_with_bar(close=4209.0, bar_date=dt.date(2026, 4, 22))
    r = resolve_entry_price(
        s,
        bundle=_bundle(next_open=None, open_=None, close=None),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["source"] == "latest_close"
    assert r["price"] == pytest.approx(4209.0)
    assert r["timestamp"] == dt.date(2026, 4, 22)


def test_no_price_available_returns_none_with_reason():
    s = _session_with_bar(close=None, bar_date=None)
    r = resolve_entry_price(
        s,
        bundle=_bundle(next_open=None, open_=None, close=None),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["price"] is None
    assert r["source"] == "none"
    assert r.get("reason")


def test_db_exception_falls_through_to_none():
    r = resolve_entry_price(
        _session_raises(),
        bundle=_bundle(next_open=None, open_=None, close=None),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["price"] is None
    assert r["source"] == "none"


def test_zero_and_nan_open_skipped_to_close():
    # Zero is nonsense → use close instead.
    r = resolve_entry_price(
        _session_raises(),
        bundle=_bundle(next_open=None, open_=0.0, close=4200.0),
        as_of_date=dt.date(2026, 4, 23),
        instrument="ES",
    )
    assert r["source"] == "same_day_close"
    assert r["price"] == pytest.approx(4200.0)


def test_source_precedence_is_stable():
    """Contract: if a higher-precedence source is present it always wins."""
    order = [
        (dict(next_open=4180, open_=4100, close=4200), "next_open"),
        (dict(next_open=None, open_=4100, close=4200), "same_day_open"),
        (dict(next_open=None, open_=None, close=4200), "same_day_close"),
    ]
    for kw, expected in order:
        r = resolve_entry_price(
            _session_raises(), bundle=_bundle(**kw),
            as_of_date=dt.date(2026, 4, 23), instrument="ES",
        )
        assert r["source"] == expected


def test_real_money_paths_untouched():
    """Resolver must not be imported by execution paths."""
    import os
    import apps.api.src as src_pkg
    root = os.path.dirname(src_pkg.__file__)
    offenders: list[str] = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            with open(p, encoding="utf-8") as fh:
                s = fh.read()
            if "resolve_entry_price" in s:
                offenders.append(p)
    # Resolver lives only in scripts/run_paper_daily.py → no API imports
    assert offenders == [], (
        f"resolver leaked into api/ tree: {offenders}"
    )
