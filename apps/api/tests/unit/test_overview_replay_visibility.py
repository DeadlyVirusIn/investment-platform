"""Phase 11Z — Overview page replay-visibility contract.

Source-grep checks (no React renderer). Pins:
  1. Overview imports useExecutedSummary (account-path source).
  2. Headline "Trades" StatCell renders live_trades_count, NOT
     paper_trade_log length — the latter silently shows 0 while
     replay rows exist.
  3. When live=0 and replay>0, an explicit availability badge with
     data-test="overview-replay-availability" renders.
  4. The badge labels recovered rows as "NOT live trading activity"
     and links to /portfolio (Paper Trading Terminal).
  5. Recent Activity zero-state surfaces replay availability instead
     of silently saying "No trades yet".
  6. No POST/mutation hooks added.
"""

from __future__ import annotations

from pathlib import Path


PAGE = Path("apps/web/src/pages/Overview.tsx")
HOOKS = Path("apps/web/src/lib/operator/hooks.ts")


def test_overview_imports_executed_summary_hook():
    src = PAGE.read_text(encoding="utf-8")
    assert "useExecutedSummary" in src, (
        "Overview must consume the account-path executed-summary hook"
    )


def test_overview_renders_live_count_in_headline_trades_stat():
    src = PAGE.read_text(encoding="utf-8")
    # Pin variable name + StatCell binding so future refactors keep
    # the live-vs-replay split.
    assert "liveTradeCount" in src
    assert "live_trades_count" in src
    assert 'value={String(liveTradeCount)}' in src, (
        "headline Trades StatCell must render liveTradeCount"
    )
    # The old behaviour rendered totalTrades (paper_trade_log length).
    # Acceptable to keep totalTrades as the strategy-log count, but
    # it must NOT be the headline value.
    assert 'value={String(totalTrades)}' not in src, (
        "headline must not display strategy-log length"
    )


def test_overview_shows_replay_availability_badge_when_live_zero():
    src = PAGE.read_text(encoding="utf-8")
    # data-test hook so QA / e2e can identify the rendered state.
    assert 'data-test="overview-replay-availability"' in src
    # Must guard on both flags so the badge appears only when there
    # actually is replay context to surface.
    assert "hasReplayRecovered" in src
    assert "liveTradeCount === 0" in src


def test_replay_badge_labels_rows_as_not_live():
    src = PAGE.read_text(encoding="utf-8")
    assert "NOT live trading activity" in src
    assert "Recovered replay" in src


def test_replay_badge_links_to_paper_trading_terminal():
    src = PAGE.read_text(encoding="utf-8")
    assert 'href="/portfolio"' in src, (
        "badge must link operator to PortfolioTerminal where toggle lives"
    )
    assert "Paper Trading Terminal" in src


def test_recent_activity_zero_state_mentions_replay_when_available():
    src = PAGE.read_text(encoding="utf-8")
    # Old text: "No trades yet — regime has not triggered entry."
    # New text when replay exists must surface the replay rows so the
    # operator does not assume the system has nothing to show.
    assert "recovered replay rows available" in src.lower()
    # Old fallback wording remains for the no-replay case.
    assert "No trades yet" in src


def test_overview_uses_only_get_endpoints():
    src = PAGE.read_text(encoding="utf-8")
    forbidden = ("apiPost", "apiPut", "apiDelete", "apiPatch", "useMutation")
    for f in forbidden:
        assert f not in src, f"Overview must remain GET-only: {f}"


def test_executed_summary_hook_pins_live_replay_split():
    """The hook contract is the source of truth; if the type drops the
    split fields, Overview's typing breaks before runtime."""
    src = HOOKS.read_text(encoding="utf-8")
    for k in ("live_trades_count", "replay_trades_count",
              "replay_open_positions_count",
              "has_replay_recovered_rows"):
        assert k in src, f"ExecutedSummary type missing {k}"
