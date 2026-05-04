"""Personal-Analytics Phase — frontend visibility cards contract.

Source-grep checks (no React renderer). Pins:

  1. Three cards exist:
     - PerformanceVisibilityCard (mounted on Performance page)
     - MLInsightsCard (mounted on MLLab page)
     - OptionsShadowVisibilityCard (mounted on OptionsLayout)
  2. Cards consume only GET endpoints from the new routers
     (and existing options shadow routes).
  3. Cards contain NO buttons that suggest training, executing,
     or scheduling — wording is locked down.
  4. Cards explicitly label replay rows as "not live".
  5. ML insights card displays the "ML insight only — cannot affect
     trades" banner with `data-test="ml-insights-no-execute-banner"`.
  6. Pages mount the cards at expected positions.
"""

from __future__ import annotations

from pathlib import Path


PERF_CARD = Path(
    "apps/web/src/components/personal/PerformanceVisibilityCard.tsx"
)
ML_CARD = Path(
    "apps/web/src/components/personal/MLInsightsCard.tsx"
)
OPT_CARD = Path(
    "apps/web/src/components/personal/OptionsShadowVisibilityCard.tsx"
)
PERF_PAGE = Path("apps/web/src/pages/Performance.tsx")
MLLAB_PAGE = Path("apps/web/src/pages/MLLab.tsx")
OPT_LAYOUT = Path("apps/web/src/pages/options/OptionsLayout.tsx")


def test_card_files_exist():
    for p in (PERF_CARD, ML_CARD, OPT_CARD):
        assert p.exists(), f"missing card: {p}"


# ---------------------------------------------------------------------------
# Performance visibility card
# ---------------------------------------------------------------------------
def test_perf_card_uses_paper_perf_endpoints():
    src = PERF_CARD.read_text(encoding="utf-8")
    assert "/performance/paper/summary" in src
    assert "/performance/paper/attribution" in src
    # No POST/PUT/PATCH/DELETE/mutation surface.
    forbidden = ("apiPost", "apiPut", "apiPatch", "apiDelete", "useMutation")
    for f in forbidden:
        assert f not in src, f"{f} not allowed in {PERF_CARD.name}"


def test_perf_card_pins_no_closed_outcomes_messaging():
    src = PERF_CARD.read_text(encoding="utf-8")
    # Honest reporting per spec: never fabricate win rate.
    assert "no_closed_outcomes_yet" in src
    assert "No closed trade outcomes yet" in src


def test_perf_card_replay_label_explicit():
    src = PERF_CARD.read_text(encoding="utf-8")
    assert "NOT live trading activity" in src
    assert 'data-test="perf-replay-banner"' in src


def test_perf_card_no_run_or_train_buttons():
    src = PERF_CARD.read_text(encoding="utf-8")
    forbidden_words = (
        "Run training", "Train model", "Execute trade",
        "Promote model", "Run pipeline",
    )
    for f in forbidden_words:
        assert f not in src, f"{f} not allowed in performance card"


def test_perf_card_mounted_on_performance_page():
    src = PERF_PAGE.read_text(encoding="utf-8")
    assert "PerformanceVisibilityCard" in src
    assert "<PerformanceVisibilityCard" in src


# ---------------------------------------------------------------------------
# ML insights card
# ---------------------------------------------------------------------------
def test_ml_card_uses_ml_insights_endpoints_only():
    src = ML_CARD.read_text(encoding="utf-8")
    assert "/ml/insights/summary" in src
    assert "/ml/insights/labels" in src
    assert "/ml/insights/features" in src
    forbidden = ("apiPost", "apiPut", "apiPatch", "apiDelete", "useMutation")
    for f in forbidden:
        assert f not in src, f"{f} not allowed in {ML_CARD.name}"


def test_ml_card_no_train_or_run_buttons():
    """Card must never look like a control surface — no buttons that
    suggest the user can flip ML on, train a model, or score live."""
    src = ML_CARD.read_text(encoding="utf-8")
    # Allow lowercase mentions in copy; block control affordances.
    forbidden = (
        "Train model", "Run training", "Promote",
        "Score now", "Apply", "Enable ML",
        "<button", "onClick=", "<input",
    )
    for f in forbidden:
        assert f not in src, (
            f"ML insights card must not include control surface: {f}"
        )


def test_ml_card_pins_cannot_affect_trades_banner():
    src = ML_CARD.read_text(encoding="utf-8")
    assert 'data-test="ml-insights-no-execute-banner"' in src
    assert "ML_CAN_AFFECT_TRADES is pinned to" in src
    # Header copy that the spec mandated.
    assert "ML insight only — cannot affect trades" in src


def test_ml_card_readiness_checklist_exists():
    src = ML_CARD.read_text(encoding="utf-8")
    assert 'data-test="ml-insights-readiness-checklist"' in src
    assert "Labeled outcomes" in src
    assert "ML_CAN_AFFECT_TRADES locked to false" in src


def test_ml_card_pending_state_explicit():
    src = ML_CARD.read_text(encoding="utf-8")
    assert 'data-test="ml-insights-pending-note"' in src


def test_ml_card_mounted_on_mllab():
    src = MLLAB_PAGE.read_text(encoding="utf-8")
    assert "MLInsightsCard" in src
    assert "<MLInsightsCard" in src


# ---------------------------------------------------------------------------
# Options shadow visibility card
# ---------------------------------------------------------------------------
def test_opt_card_uses_existing_get_endpoints():
    src = OPT_CARD.read_text(encoding="utf-8")
    assert "/options/shadow/summary" in src
    assert "/options/pipeline-status" in src
    forbidden = ("apiPost", "apiPut", "apiPatch", "apiDelete", "useMutation")
    for f in forbidden:
        assert f not in src, f"{f} not allowed in {OPT_CARD.name}"


def test_opt_card_disclaimer_pinned():
    src = OPT_CARD.read_text(encoding="utf-8")
    assert (
        "Options shadow diagnostics only — no paper/live options "
        "execution"
    ) in src
    assert "options_paper_trade rows" in src
    assert "must remain 0" in src


def test_opt_card_mounted_on_options_layout():
    src = OPT_LAYOUT.read_text(encoding="utf-8")
    assert "OptionsShadowVisibilityCard" in src
    assert "<OptionsShadowVisibilityCard" in src


# ---------------------------------------------------------------------------
# Cross-cutting safety pins on all three cards + their pages
# ---------------------------------------------------------------------------
def test_no_card_contains_ml_can_affect_true():
    """Defensive: even string-literal `ML_CAN_AFFECT_TRADES=true`
    is forbidden so a copy-paste cannot accidentally flip the flag."""
    for p in (PERF_CARD, ML_CARD, OPT_CARD,
              PERF_PAGE, MLLAB_PAGE, OPT_LAYOUT):
        src = p.read_text(encoding="utf-8")
        assert "ML_CAN_AFFECT_TRADES=true" not in src, (
            f"{p}: forbidden literal ML_CAN_AFFECT_TRADES=true"
        )
        assert "ML_CAN_AFFECT_TRADES = true" not in src
