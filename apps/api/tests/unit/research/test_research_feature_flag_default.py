"""Phase 11W (Phase B) — feature flag defaults.

`RESEARCH_RO_ENABLED` must default to False in production. Operators
flip it on in dev/test only. This test asserts the default is False
when no env var is set."""

from __future__ import annotations

import os

import pytest


def test_research_ro_enabled_default_false():
    # Force a fresh Settings load with the env var absent.
    saved = os.environ.pop("RESEARCH_RO_ENABLED", None)
    try:
        from apps.api.src.config import Settings
        s = Settings()
        assert s.RESEARCH_RO_ENABLED is False
    finally:
        if saved is not None:
            os.environ["RESEARCH_RO_ENABLED"] = saved


def test_research_ro_enabled_can_be_enabled_via_env():
    os.environ["RESEARCH_RO_ENABLED"] = "true"
    try:
        from apps.api.src.config import Settings
        s = Settings()
        assert s.RESEARCH_RO_ENABLED is True
    finally:
        del os.environ["RESEARCH_RO_ENABLED"]
