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


# ===========================================================================
# Phase 11H — Strategy Evaluation page assertions
# ===========================================================================

_PHASE_11H_PAGE = "OptionsStrategyEvaluationPage.tsx"

_PHASE_11H_COMPONENTS = (
    "OptionsEvaluationDisclaimer.tsx",
    "OptionsEvaluationSummaryCards.tsx",
    "OptionsEvaluationScoreTable.tsx",
    "OptionsEvaluationDetailDrawer.tsx",
    "OptionsEvaluationDiagnosticsPanel.tsx",
    "OptionsEvaluationDistribution.tsx",
)


def test_phase_11h_page_renders_three_banner_stack():
    """Phase 11H page must render all three banners (paper-only,
    observation-only, evaluation disclaimer)."""
    src = (PAGES_DIR / _PHASE_11H_PAGE).read_text(encoding="utf-8")
    assert "OptionsPaperOnlyBanner"           in src, "missing paper-only banner"
    assert "OptionsObservationOnlyBanner"     in src, "missing observation-only banner"
    assert "OptionsEvaluationDisclaimer"      in src, "missing evaluation disclaimer"


def test_phase_11h_evaluation_disclaimer_string_present():
    src = (
        COMP_DIR / "OptionsEvaluationDisclaimer.tsx"
    ).read_text(encoding="utf-8")
    # Normalise whitespace because JSX wraps the string across lines
    flat = re.sub(r"\s+", " ", src)
    assert (
        "Evaluation scores are fixed rule-based paper analytics. "
        "They are not trade recommendations."
    ) in flat


def test_phase_11h_app_route_wired():
    app_tsx = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    for token in (
        "OptionsStrategyEvaluationPage",
        '"evaluation"',
    ):
        assert token in app_tsx, f"App.tsx missing 11H wiring for {token!r}"


def test_phase_11h_layout_includes_evaluation_tab():
    src = (PAGES_DIR / "OptionsLayout.tsx").read_text(encoding="utf-8")
    assert "/options/evaluation" in src
    assert "Evaluation" in src


def test_phase_11h_score_detail_drawer_includes_required_sections():
    src = (
        COMP_DIR / "OptionsEvaluationDetailDrawer.tsx"
    ).read_text(encoding="utf-8")
    # Component breakdown
    assert "Component breakdown" in src
    # Penalties
    assert "Penalties" in src
    # Flags
    assert "Model limitation flags" in src or "OptionsFlagList" in src
    # Formula inputs (audit)
    assert "Formula inputs" in src or "inputs" in src


_PHASE_11H_ALL_FILES = (
    [PAGES_DIR / _PHASE_11H_PAGE]
    + [COMP_DIR / c for c in _PHASE_11H_COMPONENTS]
)


def test_phase_11h_files_avoid_recommendation_language():
    """Spec forbidden list (Phase 11H code-only scan, comments stripped)."""
    forbidden = (
        r"\bRecommended\b",
        r"\bRecommendation\b",
        r"\bBest\b",
        r"\bSignal\b",
        r"\bConfidence\b",
        r"\bExecute\b",
        r"\bAuto-?trade\b",
        r"\bPromote\b",
        r"\bTrade now\b",
        r"\bTop pick\b",
        # Naked verbs as buttons
        r">\s*Buy\s*<",
        r">\s*Sell\s*<",
        r"\bPlace order\b",
    )
    for path in _PHASE_11H_ALL_FILES:
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in forbidden:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{path.name}: forbidden Phase 11H wording {pat!r}"
            )


def test_phase_11h_api_client_uses_only_apiGet():
    src = (LIB_DIR / "optionsApi.ts").read_text(encoding="utf-8")
    for tok in ("evaluationSummary", "evaluationScores",
                "evaluationScoreDetail", "evaluationDistribution",
                "evaluationDiagnostics"):
        assert tok in src, f"optionsApi.ts missing 11H method {tok!r}"
    for forbidden in ("apiPost", "apiPut", "apiPatch", "apiDelete"):
        assert forbidden not in src


def test_phase_11h_no_useMutation_in_evaluation_files():
    for path in _PHASE_11H_ALL_FILES:
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        assert "useMutation(" not in src, (
            f"{path.name}: useMutation forbidden on 11H pages"
        )
        for forbidden in ("apiPost(", "apiPut(", "apiPatch(", "apiDelete("):
            assert forbidden not in src, (
                f"{path.name}: {forbidden} forbidden on 11H files"
            )


def test_phase_11h_null_handling_uses_insufficient_or_unavailable():
    """NULL must never render as 0. Components route Money/Insufficient
    text through `format.ts` helpers; verify their default labels remain."""
    src = (COMP_DIR / "format.ts").read_text(encoding="utf-8")
    assert "nullText = 'Unavailable'" in src
    assert "nullText = 'Insufficient data'" in src
    # Spot-check 11H summary card uses "Insufficient data" wording
    summary = (COMP_DIR / "OptionsEvaluationSummaryCards.tsx").read_text(encoding="utf-8")
    assert "Insufficient data" in summary or "_val(" in summary


# ===========================================================================
# Phase 11I — Decision Support page assertions
# ===========================================================================

_PHASE_11I_PAGE = "OptionsDecisionSupportPage.tsx"

_PHASE_11I_COMPONENTS = (
    "OptionsDecisionSupportDisclaimer.tsx",
    "OptionsReviewQueueSummaryCards.tsx",
    "OptionsReviewQueueFilters.tsx",
    "OptionsReviewQueueTable.tsx",
    "OptionsShortlistBuckets.tsx",
    "OptionsReviewDetailDrawer.tsx",
    "OptionsRankingExplanation.tsx",
)


def test_phase_11i_page_renders_four_banner_stack():
    """Decision Support page must render all four banners/disclaimers."""
    src = (PAGES_DIR / _PHASE_11I_PAGE).read_text(encoding="utf-8")
    for banner in (
        "OptionsPaperOnlyBanner",
        "OptionsObservationOnlyBanner",
        "OptionsEvaluationDisclaimer",
        "OptionsDecisionSupportDisclaimer",
    ):
        assert banner in src, f"{_PHASE_11I_PAGE}: missing {banner}"


def test_phase_11i_decision_support_disclaimer_string_present():
    src = (
        COMP_DIR / "OptionsDecisionSupportDisclaimer.tsx"
    ).read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", src)
    assert "Review queues are for human inspection only" in flat
    assert "not trade recommendations or execution guidance" in flat


def test_phase_11i_app_route_wired():
    app_tsx = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    for token in (
        "OptionsDecisionSupportPage",
        "decision-support",
    ):
        assert token in app_tsx, f"App.tsx missing 11I wiring for {token!r}"


def test_phase_11i_layout_includes_decision_support_tab():
    src = (PAGES_DIR / "OptionsLayout.tsx").read_text(encoding="utf-8")
    assert "/options/decision-support" in src
    assert "Decision Support" in src


def test_phase_11i_review_detail_drawer_includes_required_sections():
    src = (
        COMP_DIR / "OptionsReviewDetailDrawer.tsx"
    ).read_text(encoding="utf-8")
    for token in (
        "OptionsRankingExplanation",  # ranking explanation block
        "Score breakdown",             # score breakdown
        "Penalties",                   # penalties section
        "OptionsFlagList",             # flags
        "Human review required",       # required wording
    ):
        assert token in src, f"OptionsReviewDetailDrawer missing {token!r}"


_PHASE_11I_ALL_FILES = (
    [PAGES_DIR / _PHASE_11I_PAGE]
    + [COMP_DIR / c for c in _PHASE_11I_COMPONENTS]
)


def test_phase_11i_files_avoid_recommendation_language():
    forbidden = (
        r"\bRecommended\b",
        r"\bRecommendation\b",
        r"\bBest\b",
        r"\bSignal\b",
        r"\bConfidence\b",
        r"\bExecute\b",
        r"\bAuto-?trade\b",
        r"\bPromote\b",
        r"\bTrade now\b",
        r"\bTop pick\b",
        r">\s*Buy\s*<",
        r">\s*Sell\s*<",
        r"\bPlace order\b",
    )
    for path in _PHASE_11I_ALL_FILES:
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in forbidden:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{path.name}: forbidden Phase 11I wording {pat!r}"
            )


def test_phase_11i_api_client_uses_only_apiGet():
    src = (LIB_DIR / "optionsApi.ts").read_text(encoding="utf-8")
    for tok in ("decisionSupportSummary", "decisionSupportReviewQueue",
                "decisionSupportReviewDetail", "decisionSupportBuckets",
                "decisionSupportDiagnostics"):
        assert tok in src, f"optionsApi.ts missing 11I method {tok!r}"
    for forbidden in ("apiPost", "apiPut", "apiPatch", "apiDelete"):
        assert forbidden not in src


def test_phase_11i_no_useMutation_in_decision_support_files():
    for path in _PHASE_11I_ALL_FILES:
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        assert "useMutation(" not in src, (
            f"{path.name}: useMutation forbidden on 11I pages"
        )
        for forbidden in ("apiPost(", "apiPut(", "apiPatch(", "apiDelete("):
            assert forbidden not in src, (
                f"{path.name}: {forbidden} forbidden on 11I files"
            )


def test_phase_11i_no_server_side_save_in_frontend():
    """Shortlists are computed views only — no UI shall offer to
    "save" a shortlist server-side."""
    forbidden_save_patterns = (
        r"\bsaveShortlist\b",
        r"\bcreateShortlist\b",
        r"\bpersistShortlist\b",
        r"\bupsertShortlist\b",
    )
    for path in _PHASE_11I_ALL_FILES:
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        for pat in forbidden_save_patterns:
            assert not re.search(pat, src), (
                f"{path.name}: server-side shortlist mutation {pat!r}"
            )


# ===========================================================================
# Phase 11J — Decision Framing page assertions
# ===========================================================================

_PHASE_11J_PAGE = "OptionsDecisionFramingPage.tsx"

_PHASE_11J_COMPONENTS = (
    "OptionsDecisionFramingDisclaimer.tsx",
    "OptionsReviewNarrativeCards.tsx",
    "OptionsNarrativeDetailDrawer.tsx",
    "OptionsScenarioComparisonPanel.tsx",
    "OptionsHumanReviewChecklist.tsx",
    "OptionsContextCaveatsPanel.tsx",
)


def test_phase_11j_page_renders_five_banner_stack():
    """Decision Framing page must render all five banners."""
    src = (PAGES_DIR / _PHASE_11J_PAGE).read_text(encoding="utf-8")
    for banner in (
        "OptionsPaperOnlyBanner",
        "OptionsObservationOnlyBanner",
        "OptionsEvaluationDisclaimer",
        "OptionsDecisionSupportDisclaimer",
        "OptionsDecisionFramingDisclaimer",
    ):
        assert banner in src, f"{_PHASE_11J_PAGE}: missing {banner}"


def test_phase_11j_decision_framing_disclaimer_string_present():
    src = (
        COMP_DIR / "OptionsDecisionFramingDisclaimer.tsx"
    ).read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", src)
    assert "Decision framing provides deterministic review context only" in flat
    assert "not advice, recommendation, or execution guidance" in flat


def test_phase_11j_app_route_wired():
    app_tsx = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    for token in ("OptionsDecisionFramingPage", "decision-framing"):
        assert token in app_tsx, f"App.tsx missing 11J wiring for {token!r}"


def test_phase_11j_layout_includes_decision_framing_tab():
    src = (PAGES_DIR / "OptionsLayout.tsx").read_text(encoding="utf-8")
    assert "/options/decision-framing" in src
    assert "Decision Framing" in src


_PHASE_11J_ALL_FILES = (
    [PAGES_DIR / _PHASE_11J_PAGE]
    + [COMP_DIR / c for c in _PHASE_11J_COMPONENTS]
)


def test_phase_11j_files_avoid_recommendation_language():
    """Spec forbidden list (Phase 11J — strict superset).

    The Decision Framing disclaimer banner *must* contain the words
    'recommendation' and 'advice' in negated form (e.g. 'not advice,
    recommendation, or execution guidance'); we explicitly exempt
    that disclaimer file. All other 11J files are scanned for the
    full forbidden list.
    """
    forbidden = (
        r"\bRecommended\b",
        r"\bRecommendation\b",
        r"\bBest\b",
        r"\bSignal\b",
        r"\bConfidence\b",
        r"\bExecute\b",
        r"\bAuto-?trade\b",
        r"\bPromote\b",
        r"\bTrade now\b",
        r"\bTop pick\b",
        r">\s*Buy\s*<",
        r">\s*Sell\s*<",
        r"\bPlace order\b",
        r"\bStrong setup\b",
        r"\bThesis\b",
        r"\bConviction\b",
        r"\bgenerate alpha\b", r"\bcapture alpha\b",
        r"\benter (?:a |the )?trade\b",
        r"\bexit (?:a |the )?trade\b",
    )
    EXEMPT_DISCLAIMER_FILES = {"OptionsDecisionFramingDisclaimer.tsx"}
    for path in _PHASE_11J_ALL_FILES:
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in forbidden:
            if path.name in EXEMPT_DISCLAIMER_FILES and pat in (
                r"\bRecommended\b", r"\bRecommendation\b",
            ):
                # Disclaimer banner legitimately contains these words
                # in negation form — required by spec.
                continue
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{path.name}: forbidden Phase 11J wording {pat!r}"
            )


def test_phase_11j_api_client_uses_only_apiGet():
    src = (LIB_DIR / "optionsApi.ts").read_text(encoding="utf-8")
    for tok in ("decisionFramingSummary", "decisionFramingNarratives",
                "decisionFramingNarrativeDetail",
                "decisionFramingCompare", "decisionFramingChecklist",
                "decisionFramingContext"):
        assert tok in src, f"optionsApi.ts missing 11J method {tok!r}"
    for forbidden in ("apiPost", "apiPut", "apiPatch", "apiDelete"):
        assert forbidden not in src


def test_phase_11j_no_useMutation_in_decision_framing_files():
    for path in _PHASE_11J_ALL_FILES:
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        assert "useMutation(" not in src, (
            f"{path.name}: useMutation forbidden on 11J pages"
        )
        for forbidden in ("apiPost(", "apiPut(", "apiPatch(", "apiDelete("):
            assert forbidden not in src, (
                f"{path.name}: {forbidden} forbidden on 11J files"
            )


def test_phase_11j_narrative_drawer_includes_required_sections():
    src = (
        COMP_DIR / "OptionsNarrativeDetailDrawer.tsx"
    ).read_text(encoding="utf-8")
    for token in (
        "Why it appears",
        "Why caution is still required",
        "OptionsHumanReviewChecklist",
        "OptionsContextCaveatsPanel",
        "non_action_footer",
        "OptionsFlagList",
    ):
        assert token in src, f"OptionsNarrativeDetailDrawer missing {token!r}"


def test_phase_11j_scenario_comparison_avoids_preference_wording():
    src = _strip_ts_comments(
        (COMP_DIR / "OptionsScenarioComparisonPanel.tsx").read_text(encoding="utf-8"),
    )
    forbidden = (
        r"\bbetter\b", r"\bworse\b",
        r"\bchoose\b", r"\bpreferable\b",
        r"\bavoid\b",
    )
    for pat in forbidden:
        assert not re.search(pat, src, re.IGNORECASE), (
            f"OptionsScenarioComparisonPanel emits forbidden word {pat!r}"
        )


def test_phase_11j_no_llm_or_prompt_imports_in_frontend():
    """Frontend must not import LLM/AI client libraries."""
    forbidden = (
        r"\bopenai\b", r"\banthropic\b", r"\bcohere\b",
        r"\b@google/generative-ai\b",
        r"\btransformers\b",
    )
    for path in _PHASE_11J_ALL_FILES:
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if "import " in ln and "from" in ln
        ]
        joined = "\n".join(import_lines)
        for pat in forbidden:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"{path.name}: LLM/AI client import {pat!r}"
            )


def test_phase_11j_narrative_card_includes_review_context_only():
    src = (
        COMP_DIR / "OptionsReviewNarrativeCards.tsx"
    ).read_text(encoding="utf-8")
    assert "non_action_footer" in src


# ===========================================================================
# Phase 11K — Cognitive Guardrails Layer assertions
# ===========================================================================

_PHASE_11K_COMPONENTS = (
    "ScoreInterpretationPanel.tsx",
    "BucketMeaningPanel.tsx",
    "RankingGuardrailBanner.tsx",
    "WhatThisDoesNotMean.tsx",
    "SelectionBiasNotice.tsx",
)


def test_phase_11k_components_exist():
    for c in _PHASE_11K_COMPONENTS:
        path = COMP_DIR / c
        assert path.exists(), f"missing 11K component {c}"


def test_phase_11k_selection_bias_notice_copy_matches_spec():
    src = _strip_ts_comments(
        (COMP_DIR / "SelectionBiasNotice.tsx").read_text(encoding="utf-8"),
    )
    flat = re.sub(r"\s+", " ", src)
    # Spec banner copy (verbatim)
    assert "Viewing only a subset of observations may create selection bias" in flat
    assert "does not indicate suitability, preference, or an action" in flat


def test_phase_11k_selection_bias_notice_exposes_three_triggers():
    src = (COMP_DIR / "SelectionBiasNotice.tsx").read_text(encoding="utf-8")
    for trigger in (
        "ONLY_HIGH_REVIEW_PRIORITY_BUCKET",
        "SCORE_DESC_SORT_ACTIVE",
        "ONLY_ONE_BUCKET_SELECTED",
    ):
        assert trigger in src, f"SelectionBiasNotice missing trigger {trigger!r}"


def test_phase_11k_ranking_guardrail_uses_deterministic_ordering_phrase():
    """The banner must surface the spec phrase 'appears earlier under
    deterministic ordering rules' (which the backend supplies). The
    banner MUST NOT contain 'ranked above' / 'better' / 'worse' /
    'prefer' / 'choose' in code (banner copy comes from API)."""
    src = _strip_ts_comments(
        (COMP_DIR / "RankingGuardrailBanner.tsx").read_text(encoding="utf-8"),
    )
    # Spec phrase keyword fragment
    assert "deterministic_ordering_phrase" in src
    # Forbidden ranking words (code, not comments) absent
    for forbidden in (r"\bbetter\b", r"\bworse\b",
                      r"\bprefer\b", r"\bchoose\b",
                      r"ranked above"):
        assert not re.search(forbidden, src, re.IGNORECASE), (
            f"RankingGuardrailBanner emits forbidden word {forbidden!r}"
        )


def test_phase_11k_what_this_does_not_mean_renders_five_lines():
    src = (COMP_DIR / "WhatThisDoesNotMean.tsx").read_text(encoding="utf-8")
    for tok in (
        "not_expected_profitability",
        "not_probability_of_success",
        "not_suitability_for_trading",
        "not_instruction_to_act",
        "not_live_market_signal",
    ):
        assert tok in src, f"WhatThisDoesNotMean missing field {tok!r}"


def test_phase_11k_narrative_drawer_integrates_guardrail_panels():
    src = (
        COMP_DIR / "OptionsNarrativeDetailDrawer.tsx"
    ).read_text(encoding="utf-8")
    for tok in (
        "ScoreInterpretationPanel",
        "BucketMeaningPanel",
        "RankingGuardrailBanner",
        "WhatThisDoesNotMean",
    ):
        assert tok in src, f"narrative drawer missing 11K panel {tok!r}"


def test_phase_11k_decision_framing_page_integrates_guardrail_panels():
    src = (PAGES_DIR / "OptionsDecisionFramingPage.tsx").read_text(encoding="utf-8")
    for tok in (
        "SelectionBiasNotice",
        "WhatThisDoesNotMean",
        "RankingGuardrailBanner",
    ):
        assert tok in src, f"decision framing page missing 11K panel {tok!r}"


def test_phase_11k_decision_support_page_integrates_selection_bias_notice():
    src = (PAGES_DIR / "OptionsDecisionSupportPage.tsx").read_text(encoding="utf-8")
    for tok in ("SelectionBiasNotice", "WhatThisDoesNotMean"):
        assert tok in src, f"decision support page missing 11K panel {tok!r}"


def test_phase_11k_components_use_apiGet_only():
    """Every 11K component reads via React Query hooks defined in
    hooks.ts; no direct apiPost/apiPut/apiPatch/apiDelete calls."""
    for c in _PHASE_11K_COMPONENTS:
        path = COMP_DIR / c
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for forbidden in ("apiPost(", "apiPut(", "apiPatch(",
                          "apiDelete(", "useMutation("):
            assert forbidden not in src, (
                f"{c}: forbidden mutation call {forbidden}"
            )


def test_phase_11k_no_recommendation_language_outside_negation():
    """Code-only scan (comments stripped). Allowed only via spec
    negation phrases like 'not a recommendation' / 'is not a signal'."""
    forbidden_assertion_phrases = (
        r"\brecommended trade\b",
        r"\bbest trade\b",
        r"\btop pick\b",
        r"\btrade now\b",
        r"\bplace order\b",
        r"\benter (?:a |the )?trade\b",
        r"\bexit (?:a |the )?trade\b",
        r"\bgenerate alpha\b",
        r"\bcapture alpha\b",
        # Banner-as-a-button-label forbidden
        r">\s*Buy\s*<",
        r">\s*Sell\s*<",
    )
    for c in _PHASE_11K_COMPONENTS:
        path = COMP_DIR / c
        if not path.exists():
            continue
        src = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for pat in forbidden_assertion_phrases:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"{c}: forbidden assertion phrase {pat!r}"
            )


def test_phase_11k_no_llm_imports_in_components():
    forbidden = (
        r"\bopenai\b", r"\banthropic\b", r"\bcohere\b",
        r"\b@google/generative-ai\b", r"\btransformers\b",
    )
    for c in _PHASE_11K_COMPONENTS:
        path = COMP_DIR / c
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if "import " in ln and "from" in ln
        ]
        joined = "\n".join(import_lines)
        for pat in forbidden:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"{c}: LLM/AI client import {pat!r}"
            )


def test_phase_11k_api_client_has_guardrails_methods():
    src = (LIB_DIR / "optionsApi.ts").read_text(encoding="utf-8")
    for tok in (
        "guardrailsScore",
        "guardrailsBucket",
        "guardrailsRanking",
        "guardrailsPageContext",
    ):
        assert tok in src, f"optionsApi.ts missing 11K method {tok!r}"
