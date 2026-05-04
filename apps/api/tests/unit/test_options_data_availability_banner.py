"""Phase 11Z — frontend Options Data Availability banner contract.

Source-grep checks (no React renderer):
  1. Banner component exists.
  2. Banner is mounted into OptionsLayout.
  3. Banner only references read-only endpoints.
  4. Banner does NOT trigger writes / fake data.
  5. Layout still renders OptionsPaperOnlyBanner (existing).
  6. Layout has no POST/mutation hooks.
"""

from __future__ import annotations

import re
from pathlib import Path


BANNER = Path("apps/web/src/components/options/OptionsDataAvailabilityBanner.tsx")
LAYOUT = Path("apps/web/src/pages/options/OptionsLayout.tsx")


def test_banner_file_exists():
    assert BANNER.exists()


def test_banner_only_uses_get_endpoints():
    src = BANNER.read_text(encoding="utf-8")
    # Every fetch goes through apiGet (which is GET-only).
    assert "apiGet" in src
    forbidden = ("apiPost", "apiPut", "apiDelete", "apiPatch", "fetch(")
    for f in forbidden:
        assert f not in src, f"forbidden API call surface: {f}"


def test_banner_endpoints_are_known_read_only():
    src = BANNER.read_text(encoding="utf-8")
    # Pin which endpoints the banner reads. If new ones are added,
    # the test must be updated and the new endpoints reviewed for
    # read-only behavior.
    expected = (
        "/options/shadow/summary",
        "/options/pipeline-status",
    )
    for e in expected:
        assert e in src, f"expected read-only endpoint missing: {e}"


def test_banner_has_clear_no_data_messaging():
    src = BANNER.read_text(encoding="utf-8")
    # Three-state messaging — exact strings pinned so the UI keeps
    # consistent operator-facing wording.
    assert "No options chain data ingested" in src
    assert "shadow evaluator has not run yet" in src
    forbidden = ("ERROR", "FAILED", "broken", "outage")
    for f in forbidden:
        assert f.lower() not in src.lower(), (
            f"banner uses alarming wording: {f!r}"
        )


def test_banner_mentions_operator_commands_with_env_gates():
    src = BANNER.read_text(encoding="utf-8")
    # Both ingest and shadow eval commands must include their env
    # gates so users don't think they can flip a hidden switch.
    assert "OPTIONS_CHAIN_INGEST_CONFIRM" in src
    assert "scripts.ingest_options_chain" in src
    assert "OPTIONS_SHADOW_EVAL_ENABLED" in src
    assert "scripts.run_options_shadow_eval" in src


def test_banner_three_state_data_test_attributes():
    src = BANNER.read_text(encoding="utf-8")
    # Pin data-test hooks so QA/automation can identify which state
    # is rendered without scraping fragile copy.
    assert 'data-test="options-banner-no-chain"' in src
    assert 'data-test="options-banner-chain-no-evals"' in src


def test_banner_mounted_in_options_layout():
    src = LAYOUT.read_text(encoding="utf-8")
    assert "OptionsDataAvailabilityBanner" in src
    # Both banners present.
    assert "OptionsPaperOnlyBanner" in src
    assert "<OptionsDataAvailabilityBanner" in src


def test_options_layout_has_no_mutation_hooks():
    src = LAYOUT.read_text(encoding="utf-8")
    forbidden = ("useMutation", "apiPost", "apiPut", "apiDelete")
    for f in forbidden:
        assert f not in src, f"OptionsLayout must not mutate: {f}"


def test_banner_does_not_fake_or_seed_data():
    src = BANNER.read_text(encoding="utf-8")
    # No mock arrays, no sample data.
    forbidden_phrases = (
        "MOCK_DATA", "SAMPLE_TRADES", "fakeTrades", "seedData",
        "demoOptions",
    )
    for f in forbidden_phrases:
        assert f not in src, f"banner must not seed fake data: {f}"
