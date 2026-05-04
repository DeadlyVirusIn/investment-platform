"""Unrealized PnL + Exit Tracking — read-only safety + behavior pins.

Covers:
  * /api/performance/paper/open-positions
  * /api/performance/paper/unrealized
  * /api/performance/paper/exit-tracking

Plus the three frontend cards mounted on Performance.tsx.

Hard rules verified:
  1. All three endpoints are GET-only.
  2. No INSERT/UPDATE/DELETE in the endpoint source for the new
     functions.
  3. Computes unrealized PnL from latest price_bar without writing.
  4. Missing price → unrealized_status='unavailable'; never zeroed.
  5. Replay rows reported separately; never silently mixed.
  6. Exit-tracking has no action language anywhere — vocabulary is
     locked to the diagnostic set.
  7. Frontend cards have no `<button`, `onClick=`, `useMutation`,
     `apiPost/Put/Patch/Delete`, or trading verbs.
  8. ML_CAN_AFFECT_TRADES not set true anywhere in changed files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PERF = Path("apps/api/src/api/performance_paper.py")
CARDS = [
    Path("apps/web/src/components/personal/OpenPositionsPnLCard.tsx"),
    Path("apps/web/src/components/personal/OpenPositionsTable.tsx"),
    Path("apps/web/src/components/personal/ExitTrackingPanel.tsx"),
]
PERF_PAGE = Path("apps/web/src/pages/Performance.tsx")


# ---------------------------------------------------------------------------
# Source-grep safety pins
# ---------------------------------------------------------------------------
def test_perf_router_get_only():
    src = PERF.read_text(encoding="utf-8")
    forbidden = ("@router.post", "@router.put", "@router.patch",
                 "@router.delete")
    for f in forbidden:
        assert f not in src, f"{PERF.name}: forbidden HTTP verb {f}"


def test_perf_router_no_db_writes():
    src = PERF.read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        stripped = line.lstrip()
        if (stripped.startswith("#") or stripped.startswith('"')
                or stripped.startswith("'") or stripped.startswith("*")):
            continue
        for pat in write_patterns:
            assert not pat.search(line), (
                f"{PERF.name}: write found in read-only endpoint: "
                f"{line.strip()}"
            )


def test_perf_router_paths_pinned():
    """Module-level grep so the three new paths cannot silently
    disappear."""
    src = PERF.read_text(encoding="utf-8")
    assert '"/open-positions"' in src
    assert '"/unrealized"' in src
    assert '"/exit-tracking"' in src


def test_exit_tracking_has_no_action_language():
    """Diagnostic-only — must not contain trading-verb output the UI
    could render as an action affordance."""
    src = PERF.read_text(encoding="utf-8")
    # Find the exit_tracking function body and inspect strings.
    m = re.search(
        r"def exit_tracking\(.*?\) -> dict\[.*?\]:\s*\"\"\".*?(?=\n\n|\Z)",
        src, re.DOTALL,
    )
    assert m, "could not locate exit_tracking function"
    body = m.group(0)
    # These verbs must not appear as standalone diagnostic labels in
    # the function body or its returned vocabulary.
    forbidden = (
        '"sell"', '"close"', '"exit now"', '"take profit"',
        '"stop loss"', '"buy now"', '"trade now"', '"execute"',
    )
    for f in forbidden:
        assert f.lower() not in body.lower(), (
            f"exit_tracking exposes action verb: {f}"
        )


def test_no_ml_can_affect_trades_set_true_in_router():
    src = PERF.read_text(encoding="utf-8")
    assert not re.search(
        r"ML_CAN_AFFECT_TRADES\s*=\s*True", src
    ), "must not flip ML_CAN_AFFECT_TRADES"


# ---------------------------------------------------------------------------
# In-process behavior pins via TestClient
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


def test_open_positions_default_excludes_replay(client):
    r = client.get("/api/performance/paper/open-positions")
    assert r.status_code == 200
    body = r.json()
    assert body["include_replay"] is False
    # Live + replay split present even at zero.
    assert "live_count" in body
    assert "replay_count" in body
    # Each row carries the contract fields.
    for p in body["positions"]:
        for k in (
            "symbol", "source", "is_replay",
            "entry_date", "entry_price", "quantity",
            "latest_price", "latest_price_date",
            "unrealized_pnl_usd", "unrealized_return_pct",
            "unrealized_status",
            "days_open", "outcome_status", "data_quality",
        ):
            assert k in p, f"open-positions row missing key: {k}"
        assert p["outcome_status"] == "open_pending"


def test_open_positions_include_replay_returns_replay_rows(client):
    r = client.get(
        "/api/performance/paper/open-positions?include_replay=true"
    )
    body = r.json()
    if body["count"] > 0:
        # When rows exist, the contract fields must be honored. If any
        # are replay-tagged they must be flagged.
        replay_rows = [p for p in body["positions"] if p["is_replay"]]
        for p in replay_rows:
            assert p["source"] in ("replay", "test")


def test_open_positions_handles_missing_price_safely(client):
    """Rows without a price_bar must surface
    `unrealized_status='unavailable'`, never zero."""
    r = client.get(
        "/api/performance/paper/open-positions?include_replay=true"
    )
    body = r.json()
    for p in body["positions"]:
        if not p["data_quality"]["latest_price_available"]:
            assert p["unrealized_pnl_usd"] is None
            assert p["unrealized_return_pct"] is None
            assert p["unrealized_status"] == "unavailable"


def test_unrealized_summary_split_buckets(client):
    r = client.get("/api/performance/paper/unrealized")
    assert r.status_code == 200
    body = r.json()
    # Headline + live + replay buckets always returned.
    for k in ("headline", "live", "replay"):
        assert k in body
        bucket = body[k]
        for inner in ("n_positions", "n_with_price",
                      "n_unavailable",
                      "total_unrealized_pnl_usd",
                      "avg_unrealized_return_pct",
                      "best", "worst"):
            assert inner in bucket
    # Live invariant: when no live positions exist, total_pnl is null
    # not 0 — never silently mix replay into live headline.
    if body["live"]["n_positions"] == 0:
        assert body["live"]["total_unrealized_pnl_usd"] is None
        assert body["live"]["best"] is None
        assert body["live"]["worst"] is None


def test_unrealized_all_replay_flag_set_when_live_zero(client):
    r = client.get("/api/performance/paper/unrealized")
    body = r.json()
    if body["replay"]["n_positions"] > 0 and body["live"]["n_positions"] == 0:
        assert body["all_positions_are_replay"] is True


def test_exit_tracking_vocabulary_locked_and_no_action_words(client):
    r = client.get(
        "/api/performance/paper/exit-tracking?include_replay=true"
    )
    assert r.status_code == 200
    body = r.json()
    vocab = body["vocabulary"]
    forbidden = {
        "Sell", "Close", "Exit now", "Take profit",
        "Stop loss", "Buy", "Buy now", "Execute", "Submit",
    }
    for v in vocab:
        assert v not in forbidden, f"vocab contains action verb: {v}"
    # Per-row labels must come from the same vocabulary set.
    allowed = set(vocab)
    for p in body["positions"]:
        for label in p["diagnostic_labels"]:
            assert label in allowed, (
                f"row diagnostic label outside vocabulary: {label}"
            )
        # Exit rule defaults to unavailable until persisted config exists.
        assert p["exit_rule_status"] in ("unavailable", "available")
        if p["exit_rule_status"] == "unavailable":
            assert p["exit_rule"] is None


def test_exit_tracking_does_not_close_or_label_positions(client):
    """outcome_status must remain open_pending; endpoint must never
    silently flip a row to closed."""
    r = client.get(
        "/api/performance/paper/exit-tracking?include_replay=true"
    )
    body = r.json()
    for p in body["positions"]:
        assert p["outcome_status"] == "open_pending"


# ---------------------------------------------------------------------------
# Frontend safety pins
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("p", CARDS)
def test_card_has_no_post_or_mutation(p: Path):
    src = p.read_text(encoding="utf-8")
    forbidden = (
        "apiPost", "apiPut", "apiPatch", "apiDelete", "useMutation",
        "<button",
        "onClick=",
    )
    for f in forbidden:
        assert f not in src, f"{p.name}: forbidden control surface {f}"


@pytest.mark.parametrize("p", CARDS)
def test_card_has_no_action_verbs(p: Path):
    """Block trading-verb action affordances. Plain copy that mentions
    rules in the past tense is fine; control-affordance phrasing is not."""
    src = p.read_text(encoding="utf-8")
    forbidden = (
        ">Sell<", ">Buy<", ">Close<", ">Execute<",
        ">Take profit<", ">Stop loss<", ">Exit now<",
        ">Submit<", ">Trade now<",
    )
    for f in forbidden:
        assert f not in src, f"{p.name}: action affordance {f}"


def test_card_files_exist_and_mounted():
    for c in CARDS:
        assert c.exists(), f"missing card: {c}"
    page = PERF_PAGE.read_text(encoding="utf-8")
    for name in (
        "OpenPositionsPnLCard",
        "OpenPositionsTable",
        "ExitTrackingPanel",
    ):
        assert name in page, f"Performance.tsx missing import/use: {name}"
        assert f"<{name}" in page, f"Performance.tsx missing JSX: {name}"


def test_open_positions_table_has_replay_chip_label():
    src = Path(
        "apps/web/src/components/personal/OpenPositionsTable.tsx"
    ).read_text(encoding="utf-8")
    assert "Recovered replay — not live trading activity" in src
    assert 'data-test="replay-row-chip"' in src


def test_exit_tracking_panel_pins_disclaimer():
    src = Path(
        "apps/web/src/components/personal/ExitTrackingPanel.tsx"
    ).read_text(encoding="utf-8")
    assert 'data-test="exit-tracking-disclaimer"' in src
    assert "NO action recommendation" in src
    # Cards must use the API vocabulary; "Exit rule unavailable" must
    # be rendered when status is unavailable.
    assert "Exit rule unavailable" in src


def test_no_card_contains_ml_can_affect_true():
    for p in CARDS + [PERF_PAGE]:
        src = p.read_text(encoding="utf-8")
        assert "ML_CAN_AFFECT_TRADES=true" not in src
        assert "ML_CAN_AFFECT_TRADES = true" not in src
