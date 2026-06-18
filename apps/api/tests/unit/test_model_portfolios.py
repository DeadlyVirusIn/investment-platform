"""MVP — model-portfolio track-record math (pure, no DB)."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from apps.api.src.api.model_portfolios import (
    compute_nav_series,
    require_user_id,
    CURATED,
)


D = dt.date


def test_nav_indexed_to_one_at_start():
    pm = {"A": {D(2022, 1, 3): 100.0, D(2022, 1, 4): 110.0}}
    s = compute_nav_series(pm, {"A": 1.0})
    assert s[0][1] == 1.0                       # NAV starts at 1.0
    assert abs(s[1][1] - 1.1) < 1e-9            # +10%
    assert abs(s[1][2] - 0.1) < 1e-9            # daily return


def test_weights_renormalized_and_blended():
    pm = {
        "A": {D(2022, 1, 3): 100.0, D(2022, 1, 4): 120.0},   # +20%
        "B": {D(2022, 1, 3): 50.0, D(2022, 1, 4): 50.0},     # flat
    }
    s = compute_nav_series(pm, {"A": 1.0, "B": 1.0})         # 50/50 after renorm
    assert abs(s[-1][1] - 1.10) < 1e-9                       # (1.2+1.0)/2


def test_intersection_start_and_forward_fill():
    pm = {
        "A": {D(2022, 1, 3): 10.0, D(2022, 1, 4): 11.0, D(2022, 1, 5): 12.0},
        "B": {D(2022, 1, 4): 20.0, D(2022, 1, 5): 22.0},     # starts later
    }
    s = compute_nav_series(pm, {"A": 0.5, "B": 0.5})
    assert s[0][0] == D(2022, 1, 4)                          # latest common start
    assert s[0][1] == 1.0


def test_empty_inputs():
    assert compute_nav_series({}, {"A": 1.0}) == []
    assert compute_nav_series({"A": {D(2022, 1, 3): 10.0}}, {}) == []


def test_curated_weights_sum_to_one():
    for spec in CURATED:
        assert abs(sum(spec["holdings"].values()) - 1.0) < 1e-9, spec["slug"]
        assert spec["slug"] and spec["name"] and spec["thesis"]


# --- Sprint B — per-user identity (auth layer) ---


def test_require_user_id_rejects_anonymous():
    for bad in (None, "", "   "):
        with pytest.raises(HTTPException) as e:
            require_user_id(bad)
        assert e.value.status_code == 401


def test_require_user_id_returns_trimmed_capped_id():
    assert require_user_id("  user-abc  ") == "user-abc"
    assert require_user_id("x" * 100) == "x" * 64   # capped to column width
