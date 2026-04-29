"""Phase 11U.fix - context_daily gate lookup unit tests."""

from __future__ import annotations

import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.run_paper_daily import (
    PRODUCTION_GATE_NAMES,
    _read_gates_from_context_daily,
)


def _row(name: str, value: bool):
    r = MagicMock()
    r.context_name = name
    r.value_bool = value
    return r


class _FakeSession:
    def __init__(self, rows: list):
        self._rows = rows
        self.calls: list[dict] = []

    def execute(self, sql, params):
        self.calls.append(params)

        class _Result:
            def all(self_inner):
                return self._rows
        # Return *self*'s captured rows.
        result = _Result()
        result.all = lambda: self._rows  # type: ignore[assignment]
        return result


def test_returns_dict_when_all_four_gates_present():
    s = _FakeSession([
        _row("rates_calm", False),
        _row("vrp_supportive", True),
        _row("credit_stable", True),
        _row("liquidity_expanding", False),
    ])
    out = _read_gates_from_context_daily(s, dt.date(2026, 4, 28))
    assert out == {
        "rates_calm": False,
        "vrp_supportive": True,
        "credit_stable": True,
        "liquidity_expanding": False,
    }


def test_returns_none_when_any_gate_missing():
    s = _FakeSession([
        _row("rates_calm", False),
        _row("vrp_supportive", True),
        _row("credit_stable", True),
        # liquidity_expanding missing
    ])
    out = _read_gates_from_context_daily(s, dt.date(2026, 4, 28))
    assert out is None


def test_returns_none_when_no_rows():
    s = _FakeSession([])
    out = _read_gates_from_context_daily(s, dt.date(2026, 4, 28))
    assert out is None


def test_query_uses_le_run_date_filter():
    s = _FakeSession([
        _row(g, True) for g in PRODUCTION_GATE_NAMES
    ])
    target = dt.date(2026, 4, 28)
    _read_gates_from_context_daily(s, target)
    assert len(s.calls) == 1
    # Bound parameter must be the run_date (no future).
    assert s.calls[0]["run_date"] == target


def test_query_targets_only_four_production_gates():
    s = _FakeSession([])
    _read_gates_from_context_daily(s, dt.date(2026, 4, 28))
    names = s.calls[0]["names"]
    assert sorted(names) == sorted(PRODUCTION_GATE_NAMES)


def test_production_gate_names_are_frozen():
    assert PRODUCTION_GATE_NAMES == (
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    )


def test_returns_bool_type_not_truthy_int():
    s = _FakeSession([
        _row("rates_calm", 0),
        _row("vrp_supportive", 1),
        _row("credit_stable", True),
        _row("liquidity_expanding", False),
    ])
    out = _read_gates_from_context_daily(s, dt.date(2026, 4, 28))
    for v in out.values():
        assert isinstance(v, bool)


def test_no_future_date_in_query():
    """Source-level guard: the SQL query must use `<=` for the
    cutoff and `ORDER BY ... DESC`."""
    import inspect
    src = inspect.getsource(_read_gates_from_context_daily)
    assert "as_of_date <= :run_date" in src
    assert "ORDER BY context_name, as_of_date DESC" in src
    # Forbidden patterns
    for forbidden in (
        "as_of_date >= :", "as_of_date > :", "as_of_date = :",
    ):
        assert forbidden not in src, (
            f"forbidden cutoff pattern: {forbidden!r}"
        )
