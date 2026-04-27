"""Phase 11K.1 — UI wording audit safety tests.

Frontend-only audit: enforces neutralised labels surfaced in the
operator dashboard (Top Catalysts, Engine Attribution, Activity Feed,
Header / TopStrip, Since Yesterday panel, Performance panel, Global
footer). Backend logic is NOT touched in 11K.1.

Tests scan TS/TSX source as text. They:
  * Verify replacement labels exist (EVENT_IMPACT_HIGH, etc.)
  * Verify forbidden action wording is absent in the audited files
    (BUY/SELL/TRADE-NOW/RECOMMEND/BEST/PREFER/CHOOSE/EXECUTE)
  * Verify required tooltip strings exist
  * Verify the global footer renders the spec disclaimer

Audited file set is explicit so the test does NOT bleed into
unrelated UI surfaces.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
WEB_SRC   = REPO_ROOT / "apps" / "web" / "src"


# Audited surfaces (Phase 11K.1 scope only)
_AUDITED_FILES = {
    "TopCatalysts":       WEB_SRC / "components" / "overview" / "TopCatalysts.tsx",
    "DailyActivityCard":  WEB_SRC / "components" / "paper" / "DailyActivityCard.tsx",
    "TopStrip":           WEB_SRC / "components" / "shell" / "TopStrip.tsx",
    "Shell":              WEB_SRC / "components" / "shell" / "Shell.tsx",
    "TradeBlotter":       WEB_SRC / "components" / "overview" / "TradeBlotter.tsx",
    "WhatChanged":        WEB_SRC / "components" / "overview" / "WhatChanged.tsx",
    "PerformancePanel":   WEB_SRC / "components" / "operator" / "PerformancePanel.tsx",
    "Overview":           WEB_SRC / "pages" / "Overview.tsx",
}


def _read(name: str) -> str:
    p = _AUDITED_FILES[name]
    return p.read_text(encoding="utf-8")


def _strip_ts_comments(src: str) -> str:
    out_lines: list[str] = []
    in_block = False
    for ln in src.splitlines():
        stripped = ln.strip()
        if in_block:
            if "*/" in ln:
                in_block = False
            continue
        if stripped.startswith("//"):
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block = True
            continue
        if stripped.startswith("*"):
            continue
        if "//" in ln:
            ln = ln.split("//", 1)[0]
        out_lines.append(ln)
    return "\n".join(out_lines)


# ===========================================================================
# 1. Top Catalysts — neutralised labels + tooltip
# ===========================================================================

def test_top_catalysts_uses_neutralised_event_impact_labels():
    src = _read("TopCatalysts")
    for tok in (
        "EVENT_IMPACT_HIGH",
        "EVENT_IMPACT_MODERATE",
        "EVENT_MONITOR",
        "NO_EVENT_SIGNAL",
    ):
        assert tok in src, f"TopCatalysts missing replacement label {tok!r}"


def test_top_catalysts_does_not_render_action_labels():
    """Audited code-only scan — old action labels (block/reduce/watch/
    neutral as user-visible chip text) replaced by event-impact codes."""
    src = _strip_ts_comments(_read("TopCatalysts"))
    for forbidden in (
        r'label:\s*"block"',
        r'label:\s*"reduce"',
        r'label:\s*"watch"',
        r'label:\s*"neutral"',
    ):
        assert not re.search(forbidden, src), (
            f"TopCatalysts still uses old chip label {forbidden!r}"
        )


def test_top_catalysts_tooltip_string_present():
    src = _read("TopCatalysts")
    flat = re.sub(r"\s+", " ", src)
    assert (
        "Catalyst labels are event classifications only. They do not "
        "imply actions or portfolio adjustments."
    ) in flat


# ===========================================================================
# 2. Engine attribution — HIGH/LOW/MIXED contribution level + guardrail
# ===========================================================================

def test_daily_activity_engine_health_label_helper_uses_contribution_levels():
    src = _read("DailyActivityCard")
    for tok in (
        "_engineHealthLabel",
        "HIGH contribution level",
        "LOW contribution level",
        "MIXED contribution level",
        "MONITORING contribution level",
    ):
        assert tok in src, f"DailyActivityCard missing {tok!r}"


def test_daily_activity_engine_attribution_tooltip_present():
    src = _read("DailyActivityCard")
    flat = re.sub(r"\s+", " ", src)
    assert (
        "Engine attribution reflects historical paper-trading "
        "contribution only. It does not indicate future performance "
        "or strategy selection."
    ) in flat


def test_overview_engine_health_returns_neutralised_status_strings():
    src = _read("Overview")
    for tok in (
        "HIGH contribution level",
        "LOW contribution level",
        "MIXED contribution level",
        "MONITORING contribution level",
    ):
        assert tok in src, f"Overview engineHealth missing {tok!r}"


def test_overview_no_keep_active_or_positive_contributor():
    src = _strip_ts_comments(_read("Overview"))
    for forbidden in (
        r'"Keep active\."',
        r'"positive contributor"',
        r'"negative drag"',
    ):
        assert not re.search(forbidden, src), (
            f"Overview still uses old phrase {forbidden!r}"
        )


def test_overview_uses_historical_contribution_observed():
    src = _read("Overview")
    flat = re.sub(r"\s+", " ", src)
    assert "historical contribution observed" in flat
    assert "Historical Sharpe contribution" in flat


# ===========================================================================
# 3. Activity feed — Conditions not satisfied / state transition recorded
# ===========================================================================

def test_trade_blotter_uses_neutralised_state_labels():
    src = _read("TradeBlotter")
    for tok in (
        "STATE TRANSITION RECORDED",
        "Conditions not satisfied",
        "EVALUATION CYCLE COMPLETED",
    ):
        assert tok in src, f"TradeBlotter missing {tok!r}"


def test_trade_blotter_does_not_render_skip_open_action():
    """Old user-visible 'SKIP'/'ENTER'/'EXIT' chip labels removed."""
    src = _strip_ts_comments(_read("TradeBlotter"))
    for forbidden in (
        r'enter:\s*"ENTER"',
        r'exit:\s*"EXIT"',
        r'skip:\s*"SKIP"',
    ):
        assert not re.search(forbidden, src), (
            f"TradeBlotter still uses old chip label {forbidden!r}"
        )


def test_daily_activity_uses_observation_wording():
    src = _read("DailyActivityCard")
    flat = re.sub(r"\s+", " ", src)
    # "decision(s)" replaced with "observation(s)" in user-facing copy
    assert "observation{decisions === 1 ? \"\" : \"s\"}" in flat or \
           "observation(s)" in flat
    # "no state change recorded" replaces "flat"
    assert "no state change recorded" in flat


def test_daily_activity_feed_tooltip_present():
    src = _read("DailyActivityCard")
    flat = re.sub(r"\s+", " ", src)
    assert (
        "Events reflect internal evaluation states. They do not "
        "represent trade actions or instructions."
    ) in flat


def test_daily_activity_gates_tooltip_present():
    src = _read("DailyActivityCard")
    flat = re.sub(r"\s+", " ", src)
    assert (
        "Gates represent rule condition alignment. Partial completion "
        "does not imply pending or expected action."
    ) in flat


# ===========================================================================
# 4. TopStrip — Standing by replaced + tooltips on NAV/Return/Regime
# ===========================================================================

def test_topstrip_no_standing_by():
    src = _strip_ts_comments(_read("TopStrip"))
    assert '"Standing by"' not in src
    assert "Standing by" not in src


def test_topstrip_engine_idle_uses_neutral_phrase():
    src = _read("TopStrip")
    assert "No evaluation path currently active" in src


def test_topstrip_cell_supports_tooltip_prop():
    src = _read("TopStrip")
    assert "tooltip?: string" in src
    assert "title={tooltip}" in src


def test_topstrip_nav_return_regime_have_tooltips():
    src = _read("TopStrip")
    flat = re.sub(r"\s+", " ", src)
    nav_tooltip = (
        "Values reflect simulated paper-trading results. "
        "They do not indicate future outcomes."
    )
    assert nav_tooltip in flat
    regime_tooltip = (
        "Regime is a model classification and does not imply direction."
    )
    assert regime_tooltip in flat


# ===========================================================================
# 5. Since Yesterday — recorded state transitions
# ===========================================================================

def test_what_changed_uses_state_transitions_label():
    src = _read("WhatChanged")
    flat = re.sub(r"\s+", " ", src)
    assert "Recorded state transitions" in flat
    assert "state transition" in flat


def test_what_changed_does_not_use_trades_label():
    src = _strip_ts_comments(_read("WhatChanged"))
    assert 'label: "Trades"' not in src
    assert '+${todayCount} entry' not in src


# ===========================================================================
# 6. PerformancePanel — Trades label replaced
# ===========================================================================

def test_performance_panel_uses_recorded_state_transitions():
    src = _read("PerformancePanel")
    assert "Recorded state transitions" in src
    src_no_comments = _strip_ts_comments(src)
    assert 'label="Trades"' not in src_no_comments


# ===========================================================================
# 7. Global footer — persistent observational disclaimer
# ===========================================================================

def test_shell_renders_global_observational_footer():
    src = _read("Shell")
    flat = re.sub(r"\s+", " ", src)
    assert (
        "This system provides observational analytics only. It does "
        "not generate recommendations, signals, or execution guidance."
    ) in flat
    # The footer must be rendered persistently inside Shell
    assert "<footer" in src


# ===========================================================================
# 8. Forbidden action wording in audited files (code-only)
# ===========================================================================

# This list mirrors the spec's forbidden set:
# buy / sell / trade / signal / recommend / best / worst / prefer / choose / execute
# Several of these legitimately appear in unrelated contexts (the word
# "trade" inside compound nouns like "paper-trade"); we narrow to
# action-noun pairs and forbid bare imperative button-style labels.
_FORBIDDEN_USER_FACING = (
    r">\s*Buy\s*<",
    r">\s*Sell\s*<",
    r">\s*Trade\s+now\s*<",
    r">\s*Place\s+order\s*<",
    r">\s*Execute\s*<",
    r"\bBest\s+trade\b",
    r"\bRecommended\s+trade\b",
    r"\bTop\s+pick\b",
    r"\bAuto-?trade\b",
    r"\bPrefer\s+(?:trade|order)\b",
    r"\bChoose\s+(?:trade|order)\b",
)


def test_audited_files_do_not_contain_forbidden_action_wording():
    for name, path in _AUDITED_FILES.items():
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{name}: forbidden action wording {pat!r}"
            )


def test_audited_files_avoid_old_status_codes_as_button_labels():
    """STRONG / WEAK / BLOCK / REDUCE / WATCH must not appear as
    user-visible button-style labels (>STRONG< etc.)."""
    forbidden = (
        r">\s*STRONG\s*<",
        r">\s*WEAK\s*<",
        r">\s*BLOCK\s*<",
        r">\s*REDUCE\s*<",
        r">\s*WATCH\s*<",
    )
    for name, path in _AUDITED_FILES.items():
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"{name}: forbidden button label {pat!r}"
            )
