"""Phase 11Z — Stock Paper Trading visibility contract.

Source-grep checks (no React renderer) covering the three legacy /
canonical paper-trading surfaces:

  1. /portfolio              -> PortfolioTerminal.tsx (canonical)
  2. /legacy/paper-portfolio -> PaperPortfolio.tsx
  3. /legacy/paper-operator  -> PaperOperator.tsx

Pinned guarantees:

  * Each page consumes the account-path /paper/executed/* endpoints
    for executed-trade counts, NOT the legacy
    /paper/portfolios/:id/trades nor /paper/trades (selector log).
  * include_replay defaults to false; toggle wires include_replay=true
    through the hook, which appends ?include_replay=true to the URL.
  * Replay-availability banner appears when the summary reports
    has_replay_recovered_rows=true.
  * Replay rows are labelled "Recovered replay — not live trading
    activity"; never called "live trades".
  * No POST/mutation hooks added on these pages.
  * Old endpoint surface removed from the executed-trade rendering
    path (paper_trade_log + /paper/portfolios/:id/trades may still
    appear in supporting components, but must NOT drive the headline
    executed-trade count on these pages).
"""

from __future__ import annotations

from pathlib import Path


TERMINAL = Path("apps/web/src/pages/PortfolioTerminal.tsx")
PAPER_PORTFOLIO = Path("apps/web/src/pages/PaperPortfolio.tsx")
PAPER_OPERATOR = Path("apps/web/src/pages/PaperOperator.tsx")
HOOKS = Path("apps/web/src/lib/operator/hooks.ts")


def _read(p: Path) -> str:
    assert p.exists(), f"missing {p}"
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# PortfolioTerminal.tsx — canonical Stock Paper Trading page
# ---------------------------------------------------------------------------
def test_terminal_uses_executed_endpoints_for_counts():
    src = _read(TERMINAL)
    for sym in ("useExecutedSummary", "useExecutedTrades",
                "useExecutedPositions"):
        assert sym in src, f"PortfolioTerminal must use {sym}"
    # Headline must NOT bind to trades_total alone (which silently
    # flips between live-only and live+replay with the toggle).
    assert "live_trades_count" in src
    assert "live_open_positions_count" in src


def test_terminal_toggle_label_pinned():
    src = _read(TERMINAL)
    assert "Show recovered replay data" in src


def test_terminal_replay_chip_pinned():
    src = _read(TERMINAL)
    assert "Recovered replay" in src


# ---------------------------------------------------------------------------
# PaperPortfolio.tsx — /legacy/paper-portfolio
# ---------------------------------------------------------------------------
def test_paper_portfolio_uses_executed_endpoints():
    src = _read(PAPER_PORTFOLIO)
    for sym in ("useExecutedSummary", "useExecutedTrades"):
        assert sym in src, f"PaperPortfolio must use {sym}"
    # Trade-table data source must come from execTradesQ now, not the
    # legacy hook that mixed replay rows in silently.
    assert "execTradesQ.data" in src
    assert "tradesQ.data" not in src, (
        "Legacy /paper/portfolios/:id/trades hook must not feed the "
        "executed trade table"
    )


def test_paper_portfolio_strip_renders_split_counts():
    src = _read(PAPER_PORTFOLIO)
    assert 'data-test="paper-portfolio-executed-strip"' in src
    for label in (
        "Live executed trades",
        "Live open positions",
        "Recovered replay trades",
        "Recovered replay positions",
    ):
        assert label in src, f"executed strip missing label: {label}"


def test_paper_portfolio_replay_banner_pinned():
    src = _read(PAPER_PORTFOLIO)
    assert 'data-test="paper-portfolio-replay-banner"' in src
    assert "NOT live trading activity" in src
    # Toggle wording pinned per spec.
    assert "Show recovered replay data" in src


def test_paper_portfolio_trade_row_labels_replay_explicitly():
    src = _read(PAPER_PORTFOLIO)
    assert "Recovered replay — not live trading activity" in src
    # Conditional must guard on the source field returned by the
    # /paper/executed/trades endpoint.
    assert "r.source === 'replay'" in src or 'r.source === "replay"' in src


def test_paper_portfolio_has_no_post_or_mutation():
    src = _read(PAPER_PORTFOLIO)
    forbidden = ("apiPost", "apiPut", "apiDelete", "apiPatch", "useMutation")
    for f in forbidden:
        assert f not in src, f"PaperPortfolio must remain GET-only: {f}"


# ---------------------------------------------------------------------------
# PaperOperator.tsx — /legacy/paper-operator
# ---------------------------------------------------------------------------
def test_paper_operator_surfaces_executed_summary():
    src = _read(PAPER_OPERATOR)
    assert "useExecutedSummary" in src
    assert "live_trades_count" in src
    assert "replay_trades_count" in src


def test_paper_operator_data_streams_strip_pinned():
    src = _read(PAPER_OPERATOR)
    assert 'data-test="paper-operator-data-streams"' in src
    # JSX splits the strip labels across whitespace; collapse runs of
    # whitespace before substring check so the assertion is robust to
    # formatter line wrapping.
    flat = " ".join(src.split())
    assert "live executed trades" in flat
    assert "recovered replay trades" in flat
    assert "recovered open positions" in flat


def test_paper_operator_links_to_paper_terminal_for_toggle():
    src = _read(PAPER_OPERATOR)
    assert 'href="/portfolio"' in src
    assert "Open Paper Trading Terminal" in src


def test_paper_operator_replay_note_when_recovered():
    src = _read(PAPER_OPERATOR)
    assert 'data-test="paper-operator-replay-note"' in src
    assert "NOT live trading activity" in src


def test_paper_operator_has_no_mutation():
    src = _read(PAPER_OPERATOR)
    forbidden = ("apiPost", "apiPut", "apiDelete", "apiPatch", "useMutation")
    for f in forbidden:
        assert f not in src, f"PaperOperator must remain GET-only: {f}"


# ---------------------------------------------------------------------------
# Hook contract
# ---------------------------------------------------------------------------
def test_executed_hooks_pass_include_replay_query_param():
    """When the toggle is on, the URL must carry include_replay=true."""
    src = _read(HOOKS)
    assert "include_replay=true" in src or 'set("include_replay"' in src
    # Default-off semantics must still be present (no qs when false).
    assert "includeReplay = false" in src


def test_executed_hooks_accept_portfolio_id_filter():
    """PaperPortfolio passes the active portfolio so per-portfolio
    counts/trades stay correct when multiple portfolios exist."""
    src = _read(HOOKS)
    assert "portfolioId" in src, (
        "useExecutedTrades / useExecutedPositions must accept portfolio_id"
    )
    assert 'set("portfolio_id"' in src
