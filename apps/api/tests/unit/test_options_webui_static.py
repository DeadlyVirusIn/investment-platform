"""Phase 11F static frontend tests — Options WebUI source scan.

Cheap + robust: no vitest infrastructure needed. We treat React TSX as
text and assert presence/absence of patterns the spec mandates.

Verifies:
  * Every page under apps/web/src/pages/options/ uses
    OptionsPaperOnlyBanner (either via direct import + render, or via the
    layout that does — the layout-only case is allowed for nested pages).
  * No options page or component contains forbidden labels:
      Execute Trade, Place Order, Buy, Sell, Recommended Trade,
      Best Trade, ML Signal, Confidence Score, Auto-trade.
  * Flag tokens (ASSIGNMENT_SIMPLIFIED_EXIT, PIN_RISK_UNCERTAIN_OUTCOME,
    MISSING_SETTLEMENT) appear in the WebUI sources at least once.
  * Options API client uses ONLY apiGet (never apiPost/apiPut/apiPatch/apiDelete).
  * No options frontend file imports anything from V2 / equity routes.
  * NULL formatters never default to 0.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
WEB_SRC   = REPO_ROOT / "apps" / "web" / "src"
PAGES_DIR = WEB_SRC / "pages" / "options"
COMP_DIR  = WEB_SRC / "components" / "options"
LIB_DIR   = WEB_SRC / "lib" / "options"


def _options_files() -> list[Path]:
    out: list[Path] = []
    for d in (PAGES_DIR, COMP_DIR, LIB_DIR):
        if d.exists():
            out.extend(d.rglob("*.tsx"))
            out.extend(d.rglob("*.ts"))
    return out


# ===========================================================================
# Banner presence — every page imports + renders OptionsPaperOnlyBanner
# OR is rendered inside OptionsLayout (which always shows the banner).
# Drawer is exempt (it's an overlay component, not a page).
# ===========================================================================

def test_paper_only_banner_present_on_every_options_page():
    pages = sorted(PAGES_DIR.rglob("*.tsx"))
    assert pages, "expected pages under apps/web/src/pages/options/"
    for p in pages:
        src = p.read_text(encoding="utf-8")
        assert "OptionsPaperOnlyBanner" in src, (
            f"{p.name} must import + render OptionsPaperOnlyBanner"
        )


def test_layout_renders_banner():
    layout = (PAGES_DIR / "OptionsLayout.tsx").read_text(encoding="utf-8")
    assert "<OptionsPaperOnlyBanner" in layout


def test_banner_string_is_present():
    src = (COMP_DIR / "OptionsPaperOnlyBanner.tsx").read_text(encoding="utf-8")
    assert "Options are paper-trading only" in src


# ===========================================================================
# Forbidden user-facing labels — must NOT appear anywhere in options UI
# ===========================================================================

_FORBIDDEN_LABELS = (
    r"\bExecute Trade\b",
    r"\bPlace Order\b",
    r"\bRecommended Trade\b",
    r"\bBest Trade\b",
    r"\bML Signal\b",
    r"\bConfidence Score\b",
    r"\bAuto-?trade\b",
    r"\bV2 comparison\b",
    # Naked verbs as button-style labels — guard against >Buy</button>
    r">\s*Buy\s*<",
    r">\s*Sell\s*<",
    r">\s*Promotion\s*<",
)


def test_no_forbidden_labels_in_options_webui():
    for f in _options_files():
        src = f.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_LABELS:
            assert not re.search(pat, src), (
                f"forbidden label {pat!r} in {f.relative_to(WEB_SRC)}"
            )


# ===========================================================================
# Flag tokens visible somewhere in the WebUI sources
# ===========================================================================

_REQUIRED_FLAG_TOKENS = (
    "ASSIGNMENT_SIMPLIFIED_EXIT",
    "PIN_RISK_UNCERTAIN_OUTCOME",
    "MISSING_SETTLEMENT",
)


def test_flag_tokens_present_in_webui_sources():
    blob = "\n".join(f.read_text(encoding="utf-8") for f in _options_files())
    for tok in _REQUIRED_FLAG_TOKENS:
        assert tok in blob, f"flag token {tok!r} not surfaced in any options UI file"


def test_flag_human_labels_present():
    """Operator-facing wording from the spec MUST be present verbatim."""
    chip = (COMP_DIR / "OptionsFlagChip.tsx").read_text(encoding="utf-8")
    for label in (
        "Assignment — simplified exit model",
        "Pin risk — outcome uncertain",
        "Missing settlement — expiry unresolved",
    ):
        assert label in chip, f"flag label {label!r} missing from OptionsFlagChip"


# ===========================================================================
# Read-only fetch — no mutating helpers anywhere
# ===========================================================================

def test_options_api_client_uses_only_apiGet():
    src = (LIB_DIR / "optionsApi.ts").read_text(encoding="utf-8")
    for forbidden in ("apiPost", "apiPut", "apiPatch", "apiDelete"):
        assert forbidden not in src, (
            f"options API client must not import {forbidden}"
        )
    assert "apiGet" in src


def test_no_mutating_fetch_in_any_options_file():
    """Scan non-comment, non-string lines for actual call sites.
    Doc comments may legitimately mention names like `useMutation`."""
    for f in _options_files():
        src = f.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if (stripped.startswith("//") or stripped.startswith("/*")
                    or stripped.startswith("*") or "`useMutation`" in line):
                continue
            for forbidden in ("apiPost(", "apiPut(", "apiPatch(",
                              "apiDelete(", "useMutation("):
                assert forbidden not in line, (
                    f"forbidden mutation hook/call {forbidden} in "
                    f"{f.relative_to(WEB_SRC)}: {stripped}"
                )


# ===========================================================================
# Boundary — no imports from equity / V2 / ML
# ===========================================================================

_FORBIDDEN_IMPORT_FRAGMENTS = (
    "v2_promotion", "v2Promotion", "engineB", "engine_b",
    "shadow", "b2v2", "b2_v2",
    "ml/", "ml_hybrid", "mlHybrid", "ml_research", "ml_replay",
)


def test_no_v2_or_equity_imports_in_options_webui():
    for f in _options_files():
        src = f.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if "import " in ln and "from" in ln
        ]
        joined = "\n".join(import_lines)
        for frag in _FORBIDDEN_IMPORT_FRAGMENTS:
            # "shadow" appears in CSS class names; only flag when in import path
            assert frag not in joined, (
                f"forbidden import fragment {frag!r} in {f.relative_to(WEB_SRC)}"
            )


# ===========================================================================
# NULL handling — fmtMoney/fmtRaw/fmtPct never default to "0" / 0
# ===========================================================================

def test_format_helpers_do_not_default_null_to_zero():
    src = (COMP_DIR / "format.ts").read_text(encoding="utf-8")
    # Defaults must be word-tokens, never the literal "0" or 0
    assert "nullText = 'Unavailable'" in src
    assert "nullText = 'Insufficient data'" in src
    assert "return 0" not in src
    assert "?? 0" not in src
    assert "|| 0" not in src


def test_naive_gex_label_present_on_features_page():
    """Spec demands the literal label — it is sent down by the API and
    consumed via the FeaturesResponse field, but the cards component
    must consume it (proving it isn't dropped)."""
    cards = (COMP_DIR / "OptionsFeatureCards.tsx").read_text(encoding="utf-8")
    assert "gamma_exposure_label" in cards


def test_naive_greeks_label_consumed_by_risk_summary():
    cards = (COMP_DIR / "OptionsRiskSummaryCards.tsx").read_text(encoding="utf-8")
    assert "greeks_source_label" in cards


# ===========================================================================
# App routing wired
# ===========================================================================

def test_app_routes_options_pages():
    app_tsx = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    for path in ("/options", "OptionsLayout", "OptionsChainPage",
                 "OptionsFeaturesPage", "OptionsPaperTradesPage",
                 "OptionsRiskDashboardPage"):
        assert path in app_tsx, f"App.tsx missing options wiring for {path!r}"


def test_sidenav_includes_options_link():
    nav = (WEB_SRC / "components" / "shell" / "SideNav.tsx").read_text(encoding="utf-8")
    assert "/options" in nav
    assert "Options" in nav


# ===========================================================================
# Phase 11G — Strategy Observatory frontend assertions
# ===========================================================================

_PHASE_11G_PAGES = (
    "OptionsStrategyObservatoryPage.tsx",
    "OptionsPaperPerformancePage.tsx",
    "OptionsStrategyDiagnosticsPage.tsx",
    "OptionsScenarioReplayPage.tsx",
)


def test_phase_11g_pages_render_observation_only_banner():
    """Every 11G page must render OptionsObservationOnlyBanner below the
    paper-only banner."""
    for name in _PHASE_11G_PAGES:
        src = (PAGES_DIR / name).read_text(encoding="utf-8")
        assert "OptionsPaperOnlyBanner" in src, f"{name}: missing paper-only banner"
        assert "OptionsObservationOnlyBanner" in src, (
            f"{name}: missing observation-only banner"
        )


def test_observation_only_banner_string_present():
    src = (
        COMP_DIR / "OptionsObservationOnlyBanner.tsx"
    ).read_text(encoding="utf-8")
    assert "Observation only — not investment advice or execution guidance" in src


def test_phase_11g_app_routes_wired():
    app_tsx = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    for token in (
        "OptionsStrategyObservatoryPage",
        "OptionsPaperPerformancePage",
        "OptionsStrategyDiagnosticsPage",
        "OptionsScenarioReplayPage",
        "/options/observatory",   # comment marker is enough
    ):
        # Allow the path-suffix form too; routes use sub-paths
        assert token in app_tsx or token.replace("/options/", '"') in app_tsx, (
            f"App.tsx missing 11G wiring for {token!r}"
        )


def test_phase_11g_observatory_pages_use_allowed_wording():
    """Spec mandates 'Observed / Simulated / Paper-only / Historical /
    Candidate rule match / Rejected by rule / Diagnostic / Replay' over
    'Recommended / Best / Signal / Confidence / Execute / Buy / Sell /
    Place order / Auto-trade / Promote'.

    The forbidden-word scan is already enforced for all options TSX in
    `test_no_forbidden_labels_in_options_webui`; this test additionally
    asserts at least one allowed token appears on each 11G page so the
    UX uses the right language.
    """
    allowed = (
        "Observed", "Observation", "Simulated", "Paper-only", "Historical",
        "Candidate rule match", "Rejected by rule", "Diagnostic", "Replay",
    )
    for name in _PHASE_11G_PAGES:
        src = (PAGES_DIR / name).read_text(encoding="utf-8")
        # The page may delegate language to its components — also scan
        # the components/options/ directory so the assertion isn't
        # over-strict on the page file alone.
        joined = src + "\n" + "\n".join(
            (COMP_DIR / c).read_text(encoding="utf-8")
            for c in (
                "OptionsObservationOnlyBanner.tsx",
                "OptionsRuleExplanationCard.tsx",
                "OptionsObservationsTable.tsx",
                "OptionsObservationDetailPanel.tsx",
                "OptionsPerformanceCards.tsx",
                "OptionsDiagnosticsPanel.tsx",
                "OptionsReplayTimeline.tsx",
            )
            if (COMP_DIR / c).exists()
        )
        assert any(tok in joined for tok in allowed), (
            f"{name} (and observatory components) lacks any of the "
            f"allowed observation-only tokens: {allowed!r}"
        )


def _strip_ts_comments(src: str) -> str:
    """Remove TS line + block comments so prose-style negations like
    `// never use "best"` don't trigger word-scan tests."""
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
        # strip end-of-line // comments
        if "//" in ln:
            ln = ln.split("//", 1)[0]
        out_lines.append(ln)
    return "\n".join(out_lines)


def test_phase_11g_pages_do_not_use_recommendation_language():
    """Re-assert spec's stricter 11G forbidden list per page (code only,
    not comments)."""
    forbidden_extra = (
        r"\bRecommended\b",
        r"\bBest\b",
        r"\bSignal\b",
        r"\bConfidence\b",
        r"\bExecute\b",
        r"\bAuto-?trade\b",
        r"\bPromote\b",
    )
    for name in _PHASE_11G_PAGES:
        src = _strip_ts_comments(
            (PAGES_DIR / name).read_text(encoding="utf-8"),
        )
        for pat in forbidden_extra:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{name}: forbidden Phase 11G word {pat!r}"
            )


def test_phase_11g_observatory_components_avoid_recommendation_language():
    obs_components = (
        "OptionsObservationOnlyBanner.tsx",
        "OptionsRuleExplanationCard.tsx",
        "OptionsObservationsTable.tsx",
        "OptionsObservationDetailPanel.tsx",
        "OptionsPerformanceCards.tsx",
        "OptionsPerformanceTables.tsx",
        "OptionsDiagnosticsPanel.tsx",
        "OptionsReplayTimeline.tsx",
    )
    forbidden = (
        r"\bRecommended\b", r"\bBest\b", r"\bSignal\b",
        r"\bConfidence\b", r"\bExecute\b", r"\bAuto-?trade\b",
        r"\bPromote\b",
    )
    for c in obs_components:
        path = COMP_DIR / c
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in forbidden:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{c}: forbidden 11G word {pat!r}"
            )


def test_phase_11g_api_client_only_uses_apiGet():
    """The 11G additions to optionsApi.ts must keep using apiGet only."""
    src = (LIB_DIR / "optionsApi.ts").read_text(encoding="utf-8")
    # New 11G-named endpoints use apiGet
    for tok in ("strategies", "strategyObservations", "performanceSummary",
                "diagnostics", "scenarioReplay"):
        assert tok in src, f"optionsApi.ts missing 11G method {tok!r}"
    # No mutating helpers
    for forbidden in ("apiPost", "apiPut", "apiPatch", "apiDelete"):
        assert forbidden not in src, (
            f"optionsApi.ts must not import {forbidden}"
        )
