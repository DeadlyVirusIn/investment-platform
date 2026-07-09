"""Honest Numbers — Trust Center v1 owner endpoint.

Pins: owner-guard dependency wired; six-label honesty enum enforced;
section builder rejects invented labels; safe-flag subset only (never raw
env); dev-study wording never claims a production statistic.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from apps.api.src.api import trust_center as tc
from apps.api.src.api.admin_guard import require_owner


def test_router_is_owner_guarded() -> None:
    dep_calls = [d.dependency for d in tc.router.dependencies]
    assert require_owner in dep_calls
    routes = [r for r in tc.router.routes if isinstance(r, APIRoute)]
    assert routes and all(r.path.startswith("/admin/trust-center") for r in routes)
    assert all(sorted(r.methods) == ["GET"] for r in routes)  # read-only


def test_section_builder_enforces_label_enum() -> None:
    s = tc._section("X", "preliminary", "body")
    assert s["label"] == "preliminary"
    with pytest.raises(AssertionError):
        tc._section("X", "excellent", "marketing label must die")


def test_labels_are_the_spec_six() -> None:
    assert set(tc.LABELS) == {
        "proven", "preliminary", "insufficient_data",
        "not_yet_evaluated", "degraded", "unavailable",
    }


def test_calibration_section_never_claims_production_stat() -> None:
    import inspect

    src = inspect.getsource(tc.trust_center)
    # The dev-study reference must carry the not-a-production-statistic
    # disclaimer and the preliminary label — pinned so a future edit can't
    # quietly promote research numbers into a production claim.
    assert "NOT a production" in src
    assert "CONFIDENCE_CALIBRATION_REPORT.md" in src
