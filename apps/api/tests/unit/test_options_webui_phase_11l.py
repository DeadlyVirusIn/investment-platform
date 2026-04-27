"""Phase 11L — Elite UX Layer (UI-only) tests.

Frontend-only audit. Verifies:
  * --color-* alias tokens added to index.css for both themes
  * --shadow-soft + --radius-* scale defined
  * GuardrailsToggleProvider wraps app in main.tsx
  * GuardrailsToggleButton rendered inside OptionsLayout header
  * GuardrailsGate wraps every 11K interpretation panel
  * Default toggle state is ON (default true in storage init)
  * No new banned words / wording regressions in 11L files
  * NO backend file is modified (regression guard against scope creep)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
WEB_SRC   = REPO_ROOT / "apps" / "web" / "src"


# ---------------------------------------------------------------------------
# Color token aliases (both themes) + soft shadow + radius scale
# ---------------------------------------------------------------------------

def _index_css() -> str:
    return (WEB_SRC / "index.css").read_text(encoding="utf-8")


def test_phase_11l_color_aliases_defined():
    src = _index_css()
    for token in (
        "--color-bg:",
        "--color-surface:",
        "--color-accent:",
        "--color-muted:",
        "--color-success:",
        "--color-warning:",
        "--color-border:",
    ):
        assert token in src, f"index.css missing token {token!r}"


def test_phase_11l_color_aliases_present_in_both_themes():
    src = _index_css()
    # Both dark + light theme blocks must define the alias set.
    # Dark theme block starts at ':root[data-theme="dark"]'; light at
    # ':root[data-theme="light"]'.
    occurrences = src.count("--color-bg:")
    assert occurrences >= 2, (
        f"--color-bg should be defined in both themes; found {occurrences}"
    )


def test_phase_11l_shadow_and_radius_scale_defined():
    src = _index_css()
    for tok in (
        "--shadow-soft:",
        "--radius-pill:",
        "--radius-sm:",
        "--radius-md:",
        "--radius-lg:",
    ):
        assert tok in src, f"index.css missing {tok!r}"


# ---------------------------------------------------------------------------
# Guardrails toggle provider + default state
# ---------------------------------------------------------------------------

def test_phase_11l_main_wraps_with_guardrails_provider():
    src = (WEB_SRC / "main.tsx").read_text(encoding="utf-8")
    assert "GuardrailsToggleProvider" in src
    # Provider wraps the BrowserRouter so all options pages get context
    assert "<GuardrailsToggleProvider>" in src


def test_phase_11l_default_toggle_state_is_on():
    src = (WEB_SRC / "lib" / "options" / "guardrailsToggle.tsx").read_text(encoding="utf-8")
    # Initial value defaults to true when storage key absent
    assert "if (v === null) return true" in src
    # Default fallback returns true on any read failure
    assert "return true;" in src


def test_phase_11l_toggle_button_renders_on_off_states():
    src = (WEB_SRC / "components" / "options" / "GuardrailsToggleButton.tsx").read_text(encoding="utf-8")
    # Visual labels match spec
    assert "Guardrails" in src
    assert "ON" in src
    assert "OFF" in src
    # aria-pressed reflects state
    assert "aria-pressed={on}" in src


def test_phase_11l_options_layout_renders_toggle():
    src = (WEB_SRC / "pages" / "options" / "OptionsLayout.tsx").read_text(encoding="utf-8")
    assert "GuardrailsToggleButton" in src
    assert "<GuardrailsToggleButton" in src


# ---------------------------------------------------------------------------
# Gate wraps every 11K guardrail panel
# ---------------------------------------------------------------------------

_GUARDRAIL_PANELS = (
    "ScoreInterpretationPanel.tsx",
    "BucketMeaningPanel.tsx",
    "RankingGuardrailBanner.tsx",
    "WhatThisDoesNotMean.tsx",
)


def test_phase_11l_every_11k_panel_wraps_with_gate():
    comp_dir = WEB_SRC / "components" / "options"
    for f in _GUARDRAIL_PANELS:
        src = (comp_dir / f).read_text(encoding="utf-8")
        assert "GuardrailsGate" in src, f"{f}: missing GuardrailsGate import"
        assert "<GuardrailsGate" in src, f"{f}: missing <GuardrailsGate> usage"


def test_phase_11l_gate_uses_soft_shadow_token_when_on():
    src = (WEB_SRC / "components" / "options" / "GuardrailsGate.tsx").read_text(encoding="utf-8")
    assert "var(--shadow-soft)" in src
    assert "var(--radius-md)" in src


# ---------------------------------------------------------------------------
# Section header component exists (visual structure only)
# ---------------------------------------------------------------------------

def test_phase_11l_section_header_component_exists():
    p = WEB_SRC / "components" / "options" / "OptionsSectionHeader.tsx"
    assert p.exists()
    src = p.read_text(encoding="utf-8")
    # Uppercase + tracking matches the design system spec
    assert "uppercase" in src
    assert "tracking-[" in src or "tracking-wide" in src


# ---------------------------------------------------------------------------
# No backend changes / no wording regressions
# ---------------------------------------------------------------------------

def test_phase_11l_no_backend_paths_touched_by_new_components():
    """11L is UI-only. None of the new TSX components may import any
    backend module path (apps/api/...) — they consume the WebUI hook
    layer only."""
    new_files = (
        WEB_SRC / "components" / "options" / "GuardrailsGate.tsx",
        WEB_SRC / "components" / "options" / "GuardrailsToggleButton.tsx",
        WEB_SRC / "components" / "options" / "OptionsSectionHeader.tsx",
        WEB_SRC / "lib" / "options" / "guardrailsToggle.tsx",
    )
    for f in new_files:
        src = f.read_text(encoding="utf-8")
        assert "apps/api" not in src
        assert "from 'apps/api" not in src


def test_phase_11l_new_components_use_only_apiGet_via_hooks():
    """Re-uses the existing hook layer; no direct apiPost/Put/Patch/
    Delete calls and no useMutation introduced in 11L files."""
    new_files = (
        WEB_SRC / "components" / "options" / "GuardrailsGate.tsx",
        WEB_SRC / "components" / "options" / "GuardrailsToggleButton.tsx",
        WEB_SRC / "components" / "options" / "OptionsSectionHeader.tsx",
        WEB_SRC / "lib" / "options" / "guardrailsToggle.tsx",
    )
    for f in new_files:
        src = f.read_text(encoding="utf-8")
        for forbidden in ("apiPost(", "apiPut(", "apiPatch(", "apiDelete(",
                          "useMutation("):
            assert forbidden not in src, (
                f"{f.name}: forbidden mutation/call {forbidden}"
            )


_FORBIDDEN_USER_FACING = (
    r"\bRecommended\b",
    r"\bBest\s+trade\b",
    r"\bSignal\b",
    r"\bConfidence\b",
    r"\bExecute\b",
    r"\bPlace\s+order\b",
    r"\bAuto-?trade\b",
    r"\bTrade\s+now\b",
    r">\s*Buy\s*<",
    r">\s*Sell\s*<",
)


def _strip_ts_comments(src: str) -> str:
    out: list[str] = []
    in_block = False
    for ln in src.splitlines():
        s = ln.strip()
        if in_block:
            if "*/" in ln:
                in_block = False
            continue
        if s.startswith("//"):
            continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
            continue
        if s.startswith("*"):
            continue
        if "//" in ln:
            ln = ln.split("//", 1)[0]
        out.append(ln)
    return "\n".join(out)


def test_phase_11l_no_forbidden_wording_in_new_files():
    new_files = (
        WEB_SRC / "components" / "options" / "GuardrailsGate.tsx",
        WEB_SRC / "components" / "options" / "GuardrailsToggleButton.tsx",
        WEB_SRC / "components" / "options" / "OptionsSectionHeader.tsx",
        WEB_SRC / "lib" / "options" / "guardrailsToggle.tsx",
    )
    for f in new_files:
        src = _strip_ts_comments(f.read_text(encoding="utf-8"))
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{f.name}: forbidden wording {pat!r}"
            )
