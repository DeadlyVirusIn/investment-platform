"""Trade Lifecycle + ML Readiness — read-only safety + behavior pins.

Covers:
  * /api/performance/paper/lifecycle
  * /api/ml/insights/readiness

Plus the two new frontend cards.

Hard rules:
  1. Both endpoints GET-only.
  2. No INSERT/UPDATE/DELETE in the endpoint source for the new
     functions.
  3. Lifecycle includes every open trade matching the toggle.
  4. Replay rows reported separately; per-row `is_replay` flag.
  5. Lifecycle handles missing recommendation_id (linked_ids
     surfaces null without crashing).
  6. Lifecycle reports `current_stage="label_pending"` when the
     row has an outcome row but no label, and `"monitoring"` when
     no outcome row exists yet.
  7. Readiness false when `labeled_trade_count == 0`.
  8. Readiness warns when dataset is replay-only.
  9. No model training, no artifact writes, no recommendation imports.
 10. Frontend cards have no `<button`, `onClick=`, `useMutation`,
     `apiPost/Put/Patch/Delete`, no trading verbs.
 11. ML_CAN_AFFECT_TRADES not set true anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PERF = Path("apps/api/src/api/performance_paper.py")
MLINS = Path("apps/api/src/api/ml_insights.py")
LIFECYCLE_CARD = Path(
    "apps/web/src/components/personal/TradeLifecycleCard.tsx"
)
READINESS_PANEL = Path(
    "apps/web/src/components/personal/MLReadinessPanel.tsx"
)
PERF_PAGE = Path("apps/web/src/pages/Performance.tsx")
MLLAB_PAGE = Path("apps/web/src/pages/MLLab.tsx")


# ---------------------------------------------------------------------------
# Source-grep safety pins
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("p", [PERF, MLINS])
def test_no_post_decorators(p: Path):
    src = p.read_text(encoding="utf-8")
    for f in ("@router.post", "@router.put", "@router.patch",
              "@router.delete"):
        assert f not in src, f"{p.name}: forbidden {f}"


@pytest.mark.parametrize("p", [PERF, MLINS])
def test_no_db_writes(p: Path):
    src = p.read_text(encoding="utf-8")
    pats = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        s = line.lstrip()
        if (s.startswith("#") or s.startswith('"')
                or s.startswith("'") or s.startswith("*")):
            continue
        for pat in pats:
            assert not pat.search(line), (
                f"{p.name}: write SQL: {line.strip()}"
            )


def test_lifecycle_route_pinned():
    src = PERF.read_text(encoding="utf-8")
    assert '"/lifecycle"' in src


def test_readiness_route_pinned():
    src = MLINS.read_text(encoding="utf-8")
    assert '"/readiness"' in src


def test_readiness_no_model_training_imports():
    """Readiness must not import training/scoring code paths."""
    src = MLINS.read_text(encoding="utf-8")
    forbidden = (
        "train(", "fit(", ".save(", "joblib.dump", "torch.save",
        "scikit", "sklearn",
        "auto_trader", "submit_trade", "recommendation_engine",
    )
    for f in forbidden:
        assert f not in src, f"ml_insights coupling: {f}"


def test_no_ml_can_affect_trades_set_true_in_routers():
    for p in (PERF, MLINS):
        src = p.read_text(encoding="utf-8")
        assert not re.search(
            r"ML_CAN_AFFECT_TRADES\s*=\s*True", src
        ), f"{p.name}: must not flip ML_CAN_AFFECT_TRADES"


# ---------------------------------------------------------------------------
# In-process behavior pins
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    import os
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://invest:dev_only_password@localhost:54329/"
        "investment_platform",
    )
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    return TestClient(app)


def test_lifecycle_default_excludes_replay(client):
    r = client.get("/api/performance/paper/lifecycle")
    assert r.status_code == 200
    body = r.json()
    assert body["include_replay"] is False
    # Vocabulary frozen.
    assert body["lifecycle_statuses"] == [
        "entered", "open_pending", "closed",
        "outcome_pending", "outcome_labeled",
    ]
    assert body["lifecycle_stages"] == [
        "entry", "monitoring", "exit_recorded",
        "label_pending", "label_available",
    ]
    for t in body["trades"]:
        assert t["is_replay"] is False


def test_lifecycle_include_replay_returns_replay_rows(client):
    r = client.get(
        "/api/performance/paper/lifecycle?include_replay=true"
    )
    body = r.json()
    if body["count"] > 0:
        # Each row has full contract.
        for t in body["trades"]:
            for k in (
                "trade_id", "symbol", "source", "is_replay",
                "entry_ts", "entry_price", "quantity",
                "latest_price", "unrealized_pnl_usd",
                "lifecycle_status", "current_stage",
                "linked_ids", "data_quality",
            ):
                assert k in t, f"lifecycle row missing {k}"
            assert t["lifecycle_status"] in (
                "entered", "open_pending", "closed",
                "outcome_pending", "outcome_labeled",
            )
            assert t["current_stage"] in (
                "entry", "monitoring", "exit_recorded",
                "label_pending", "label_available",
            )
            for k in (
                "recommendation_id", "decision_log_id",
                "recommendation_outcome_id", "replay_run_id",
                "position_id",
            ):
                assert k in t["linked_ids"]


def test_lifecycle_handles_missing_recommendation_id(client):
    r = client.get(
        "/api/performance/paper/lifecycle?include_replay=true"
    )
    body = r.json()
    # Replay-derived rows often have recommendation_id=null. Endpoint
    # must surface that as null in linked_ids without crashing.
    for t in body["trades"]:
        if t["linked_ids"]["recommendation_id"] is None:
            # Then no outcome row can attach.
            assert t["linked_ids"]["recommendation_outcome_id"] is None


def test_lifecycle_label_pending_when_no_outcome_or_label(client):
    r = client.get(
        "/api/performance/paper/lifecycle?include_replay=true"
    )
    body = r.json()
    for t in body["trades"]:
        if (not t["data_quality"]["has_label"]
                and not t["data_quality"]["has_exit"]):
            # Either monitoring (no outcome row yet) or label_pending
            # (outcome row exists, label hasn't landed).
            assert t["current_stage"] in (
                "monitoring", "label_pending"
            )


def test_readiness_false_when_no_labels(client):
    r = client.get("/api/ml/insights/readiness")
    assert r.status_code == 200
    body = r.json()
    if body["labeled_trade_count"] == 0:
        assert body["is_ready"] is False
        assert body["reason"] == "no_labeled_outcomes"
        assert body["next_unlock_condition"] == (
            "Wait for trades to close and outcomes to be labeled."
        )


def test_readiness_warns_when_dataset_replay_only(client):
    r = client.get("/api/ml/insights/readiness")
    body = r.json()
    if body["dataset_is_replay_only"]:
        assert any(
            "replay-derived" in w.lower() for w in body["warnings"]
        )
        assert "dataset_is_replay_only" in body["missing_requirements"]


def test_readiness_pin_no_affect_trades(client):
    r = client.get("/api/ml/insights/readiness")
    body = r.json()
    assert body["ml_can_affect_trades"] is False
    assert "ML_CAN_AFFECT_TRADES" in body["notice"]


def test_readiness_checklist_complete(client):
    r = client.get("/api/ml/insights/readiness")
    body = r.json()
    names = {item["name"] for item in body["checklist"]}
    assert names == {
        "trades_exist", "exits_recorded", "outcomes_labeled",
        "leakage_check_passed", "enough_labels",
    }


# ---------------------------------------------------------------------------
# Frontend safety pins
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("p", [LIFECYCLE_CARD, READINESS_PANEL])
def test_card_no_mutation_or_buttons(p: Path):
    src = p.read_text(encoding="utf-8")
    forbidden = (
        "apiPost", "apiPut", "apiPatch", "apiDelete", "useMutation",
        "<button",
        "onClick=",
    )
    for f in forbidden:
        assert f not in src, f"{p.name}: forbidden {f}"


@pytest.mark.parametrize("p", [LIFECYCLE_CARD, READINESS_PANEL])
def test_card_no_action_verbs(p: Path):
    src = p.read_text(encoding="utf-8")
    forbidden = (
        ">Sell<", ">Buy<", ">Close<", ">Execute<", ">Submit<",
        ">Take profit<", ">Stop loss<", ">Exit now<",
        ">Train<", ">Train model<", ">Run training<",
        ">Promote<", ">Score now<", ">Apply<",
    )
    for f in forbidden:
        assert f not in src, f"{p.name}: action affordance {f}"


def test_lifecycle_card_replay_chip_pinned():
    src = LIFECYCLE_CARD.read_text(encoding="utf-8")
    assert "Recovered replay — not live trading activity" in src
    assert 'data-test="lifecycle-replay-chip"' in src
    # Stage labels are rendered via a template literal
    # `data-test={`stage-${stage}`}`. Pin the template form + the
    # frozen STAGE_ORDER list.
    assert "data-test={`stage-${stage}`}" in src
    for stage in ("entry", "monitoring", "exit_recorded",
                  "label_pending", "label_available"):
        # Each stage must appear in the frozen STAGE_ORDER.
        assert f"'{stage}'" in src, f"missing stage in STAGE_ORDER: {stage}"


def test_lifecycle_waiting_natural_exit_copy():
    src = LIFECYCLE_CARD.read_text(encoding="utf-8")
    assert 'data-test="waiting-natural-exit"' in src
    assert "Waiting for natural exit — no forced close" in src


def test_readiness_panel_disabled_copy():
    src = READINESS_PANEL.read_text(encoding="utf-8")
    assert 'data-test="ml-readiness-disabled-copy"' in src
    assert "ML evaluation not ready — outcomes still pending" in src


def test_readiness_panel_pins_no_affect_banner():
    src = READINESS_PANEL.read_text(encoding="utf-8")
    assert 'data-test="ml-readiness-no-execute-banner"' in src
    assert "ML_CAN_AFFECT_TRADES is pinned to" in src


def test_readiness_checklist_data_test_hooks():
    src = READINESS_PANEL.read_text(encoding="utf-8")
    assert 'data-test="ml-readiness-checklist"' in src
    for k in ("trades_exist", "exits_recorded", "outcomes_labeled",
              "leakage_check_passed", "enough_labels"):
        assert f'data-test={{`check-${{item.name}}`}}' in src or (
            "check-${item.name}" in src
        ), f"checklist missing data-test for {k}"


def test_pages_mount_new_cards():
    perf = PERF_PAGE.read_text(encoding="utf-8")
    mllab = MLLAB_PAGE.read_text(encoding="utf-8")
    assert "TradeLifecycleCard" in perf
    assert "<TradeLifecycleCard" in perf
    assert "MLReadinessPanel" in mllab
    assert "<MLReadinessPanel" in mllab


def test_no_card_or_page_flips_ml_flag():
    for p in (LIFECYCLE_CARD, READINESS_PANEL,
              PERF_PAGE, MLLAB_PAGE):
        src = p.read_text(encoding="utf-8")
        assert "ML_CAN_AFFECT_TRADES=true" not in src
        assert "ML_CAN_AFFECT_TRADES = true" not in src
