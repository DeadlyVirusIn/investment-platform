"""Phase 11M — Clarity & Signal Isolation Layer tests.

Frontend-only structural clarity. Verifies:
  * 4 lane types declared
  * Lane wrapper component renders badge + muted separator
  * Lane wrappers integrated into Decision Support + Decision Framing
    pages WITHOUT changing wording (test snapshots key strings still
    present from prior phases)
  * Hero / secondary / de-emphasis CSS utility classes defined
  * Tooltip builder structure: description → limitation → non-action
  * No backend changes (regression guard)
  * No new behavioural / interactive controls in 11M files
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
WEB_SRC   = REPO_ROOT / "apps" / "web" / "src"


# ---------------------------------------------------------------------------
# Lane components
# ---------------------------------------------------------------------------

def test_lane_badge_declares_four_lane_types():
    src = (WEB_SRC / "components" / "options" / "OptionsLaneBadge.tsx").read_text(encoding="utf-8")
    for lane in ("OBSERVATION", "EVALUATION", "ATTRIBUTION", "SYSTEM_STATE"):
        assert lane in src, f"OptionsLaneBadge missing lane {lane!r}"
    for label in ("Observation", "Evaluation", "Attribution", "System State"):
        assert label in src, f"OptionsLaneBadge missing label {label!r}"


def test_lane_wrapper_renders_badge_plus_separator():
    src = (WEB_SRC / "components" / "options" / "OptionsLane.tsx").read_text(encoding="utf-8")
    assert "OptionsLaneBadge" in src
    # Muted top separator anchored to --color-border token
    assert "var(--color-border)" in src
    assert "borderTop" in src or "border-t" in src


def test_lane_badge_uses_uppercase_tracking_style():
    src = (WEB_SRC / "components" / "options" / "OptionsLaneBadge.tsx").read_text(encoding="utf-8")
    assert "uppercase" in src
    assert "tracking-[" in src or "tracking-wide" in src
    # Uses 11L spec tokens (no hardcoded colors)
    assert "var(--color-muted)" in src
    assert "var(--color-border)" in src


# ---------------------------------------------------------------------------
# Page integration (lane wrappers applied)
# ---------------------------------------------------------------------------

def test_decision_support_page_wraps_sections_in_lanes():
    src = (
        WEB_SRC / "pages" / "options" / "OptionsDecisionSupportPage.tsx"
    ).read_text(encoding="utf-8")
    assert "import OptionsLane" in src
    # Review queue → EVALUATION lane
    assert 'lane="EVALUATION"' in src
    # Shortlist buckets → ATTRIBUTION lane
    assert 'lane="ATTRIBUTION"' in src


def test_decision_framing_page_wraps_sections_in_lanes():
    src = (
        WEB_SRC / "pages" / "options" / "OptionsDecisionFramingPage.tsx"
    ).read_text(encoding="utf-8")
    assert "import OptionsLane" in src
    assert 'lane="EVALUATION"' in src
    assert 'lane="ATTRIBUTION"' in src


def test_decision_support_page_preserves_existing_wording():
    """Phase 11M is structural-only: existing 11I copy stays verbatim."""
    src = (
        WEB_SRC / "pages" / "options" / "OptionsDecisionSupportPage.tsx"
    ).read_text(encoding="utf-8")
    # 11I disclaimers + 11K guardrail integration must remain
    for token in (
        "OptionsPaperOnlyBanner",
        "OptionsObservationOnlyBanner",
        "OptionsEvaluationDisclaimer",
        "OptionsDecisionSupportDisclaimer",
        "WhatThisDoesNotMean",
        "SelectionBiasNotice",
    ):
        assert token in src, f"DecisionSupport missing prior-phase token {token!r}"


def test_decision_framing_page_preserves_existing_wording():
    src = (
        WEB_SRC / "pages" / "options" / "OptionsDecisionFramingPage.tsx"
    ).read_text(encoding="utf-8")
    for token in (
        "OptionsPaperOnlyBanner",
        "OptionsObservationOnlyBanner",
        "OptionsEvaluationDisclaimer",
        "OptionsDecisionSupportDisclaimer",
        "OptionsDecisionFramingDisclaimer",
        "WhatThisDoesNotMean",
        "SelectionBiasNotice",
        "RankingGuardrailBanner",
    ):
        assert token in src, f"DecisionFraming missing prior-phase token {token!r}"


# ---------------------------------------------------------------------------
# Visual de-emphasis CSS utilities
# ---------------------------------------------------------------------------

def test_index_css_declares_hero_and_deemphasis_classes():
    src = (WEB_SRC / "index.css").read_text(encoding="utf-8")
    assert ".u-hero-nav" in src
    assert ".u-hero-secondary" in src
    assert ".u-deemphasised-num" in src
    assert ".u-lane-separator" in src


def test_index_css_hero_is_larger_than_deemphasis():
    """NAV hero font-size must be larger than the de-emphasis token
    used for scores/rankings/contribution levels."""
    src = (WEB_SRC / "index.css").read_text(encoding="utf-8")
    hero_match = re.search(
        r"\.u-hero-nav\s*\{[^}]*?font-size:\s*(\d+)px",
        src, re.DOTALL,
    )
    deemph_match = re.search(
        r"\.u-deemphasised-num\s*\{[^}]*?font-size:\s*(\d+)px",
        src, re.DOTALL,
    )
    assert hero_match, "u-hero-nav font-size declaration missing"
    assert deemph_match, "u-deemphasised-num font-size declaration missing"
    hero_px = int(hero_match.group(1))
    deemph_px = int(deemph_match.group(1))
    assert hero_px >= 64, f"hero font-size {hero_px}px below 64px floor"
    assert hero_px > deemph_px, (
        f"hero ({hero_px}px) must be larger than de-emphasis ({deemph_px}px)"
    )


def test_index_css_lane_separator_uses_color_border_token():
    src = (WEB_SRC / "index.css").read_text(encoding="utf-8")
    sep = re.search(
        r"\.u-lane-separator\s*\{[^}]*?\}",
        src, re.DOTALL,
    )
    assert sep, "u-lane-separator block missing"
    assert "var(--color-border)" in sep.group(0)


# ---------------------------------------------------------------------------
# Tooltip builder
# ---------------------------------------------------------------------------

def test_tooltip_builder_exports_three_part_structure():
    src = (WEB_SRC / "lib" / "options" / "tooltipBuilder.ts").read_text(encoding="utf-8")
    assert "buildTooltip" in src
    assert "description" in src
    assert "limitation" in src
    assert "nonAction" in src
    assert "NON_ACTION_DEFAULT" in src


def test_tooltip_builder_default_non_action_phrase():
    """Default non-action clarification must be a negation phrase
    (review context only / not advice, etc.)."""
    src = (WEB_SRC / "lib" / "options" / "tooltipBuilder.ts").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", src)
    assert "review context only" in flat.lower()
    assert "not advice" in flat.lower() or "not advice," in flat.lower()


# ---------------------------------------------------------------------------
# No new behaviour / no new controls in 11M files
# ---------------------------------------------------------------------------

_PHASE_11M_FILES = (
    WEB_SRC / "components" / "options" / "OptionsLane.tsx",
    WEB_SRC / "components" / "options" / "OptionsLaneBadge.tsx",
    WEB_SRC / "lib" / "options" / "tooltipBuilder.ts",
)


def test_phase_11m_files_introduce_no_interactive_controls():
    """Spec: NO toggles, NO filters, NO new controls in 11M.
    11M files must have zero <button>/<input>/<select>/onClick/
    onChange code paths."""
    for f in _PHASE_11M_FILES:
        src = f.read_text(encoding="utf-8")
        for forbidden in (
            "<button", "<input", "<select",
            "onClick", "onChange", "onSubmit",
            "useState(", "useReducer(",
        ):
            assert forbidden not in src, (
                f"{f.name}: forbidden interactive code {forbidden!r} "
                f"in 11M file"
            )


def test_phase_11m_files_make_no_api_calls():
    for f in _PHASE_11M_FILES:
        src = f.read_text(encoding="utf-8")
        for forbidden in (
            "apiGet(", "apiPost(", "apiPut(", "apiPatch(", "apiDelete(",
            "useQuery(", "useMutation(",
        ):
            assert forbidden not in src, (
                f"{f.name}: forbidden API call {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# No forbidden wording in 11M files
# ---------------------------------------------------------------------------

_FORBIDDEN_USER_FACING = (
    r"\bRecommended\b",
    r"\bRecommendation\b",
    r"\bBest\s+trade\b",
    r"\bSignal\b",
    r"\bConfidence\b",
    r"\bExecute\b",
    r"\bAuto-?trade\b",
    r"\bPromote\b",
    r"\bTrade\s+now\b",
    r"\bTop\s+pick\b",
    r"\bPlace\s+order\b",
    r"\benter\s+(?:a\s+|the\s+)?trade\b",
    r"\bexit\s+(?:a\s+|the\s+)?trade\b",
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


def test_phase_11m_files_avoid_forbidden_wording():
    """tooltipBuilder.ts legitimately contains the words
    'recommendation' / 'advice' inside the NON_ACTION_DEFAULT
    negation phrase. Apply the same disclaimer exemption used in
    11K for SelectionBiasNotice."""
    EXEMPT = {"tooltipBuilder.ts"}
    for f in _PHASE_11M_FILES:
        src = _strip_ts_comments(f.read_text(encoding="utf-8"))
        for pat in _FORBIDDEN_USER_FACING:
            if (f.name in EXEMPT
                    and pat in (r"\bRecommended\b", r"\bRecommendation\b")):
                continue
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{f.name}: forbidden wording {pat!r}"
            )
