"""Phase 11Z — PortfolioTerminal data-source contract tests.

Source-grep checks (no React renderer):
  1. Page calls the executed (account-path) hooks.
  2. Page renders distinct sections for executed vs strategy-log data.
  3. "0 trades recorded" wording is replaced with "executed trades"
     fed by useExecutedSummary.
  4. Empty paper_trade_log no longer renders a "0 trades" headline —
     instead the strategy-log card says "No strategy logs yet".
  5. Replay rows can be toggled; replay chip is rendered when
     source === 'replay'.
"""

from __future__ import annotations

from pathlib import Path


PAGE = Path("apps/web/src/pages/PortfolioTerminal.tsx")
HOOKS = Path("apps/web/src/lib/operator/hooks.ts")


def test_page_imports_executed_hooks():
    src = PAGE.read_text(encoding="utf-8")
    for sym in ("useExecutedSummary", "useExecutedTrades",
                "useExecutedPositions"):
        assert sym in src, f"page must import {sym}"


def test_hooks_module_exports_executed_hooks():
    src = HOOKS.read_text(encoding="utf-8")
    for sym in ("useExecutedSummary", "useExecutedTrades",
                "useExecutedPositions"):
        assert f"export function {sym}" in src, (
            f"hooks module must export {sym}"
        )


def test_executed_hooks_call_paper_executed_routes():
    src = HOOKS.read_text(encoding="utf-8")
    assert "/paper/executed/summary" in src
    assert "/paper/executed/trades" in src
    assert "/paper/executed/positions" in src


def test_executed_hooks_default_include_replay_false():
    src = HOOKS.read_text(encoding="utf-8")
    # Each hook signature should default `includeReplay = false`.
    for sym in ("useExecutedSummary", "useExecutedTrades",
                "useExecutedPositions"):
        # Loose match — handles both `(includeReplay = false)` and
        # `(includeReplay = false, ...)`.
        assert f"{sym}(includeReplay = false" in src.replace(" :", ":") \
            or f"{sym}(\n  includeReplay = false" in src \
            or f"{sym}(includeReplay = false" in src.replace("\n", " "), (
                f"{sym} should default includeReplay=false"
            )


def test_old_zero_trades_headline_removed():
    src = PAGE.read_text(encoding="utf-8")
    # The old wording "{trades?.length ?? 0} total trades recorded"
    # must be replaced — that string was wrong because trades came
    # from paper_trade_log not paper_trade.
    forbidden_phrases = (
        "total trades recorded",
    )
    for f in forbidden_phrases:
        assert f not in src, (
            f"PortfolioTerminal still uses misleading wording: {f!r}"
        )


def test_page_renders_separate_executed_and_strategy_log_sections():
    src = PAGE.read_text(encoding="utf-8")
    assert "Executed Trades" in src
    assert "Strategy Logs" in src
    # Strategy Logs section must say "No strategy logs yet" not
    # "No trades" when paper_trade_log is empty.
    assert "No strategy logs yet" in src


def test_page_renders_replay_chip_when_source_replay():
    src = PAGE.read_text(encoding="utf-8")
    # "u-chip-warning" + "replay" rendering pinned.
    assert "source === \"replay\"" in src or 'source === "replay"' in src
    assert "Recovered replay" in src


def test_page_does_not_use_post():
    src = PAGE.read_text(encoding="utf-8")
    forbidden = ("apiPost", "useMutation", "POST")
    for f in forbidden:
        # Allow "POST" in comments/docs.
        for line in src.splitlines():
            stripped = line.lstrip()
            if (stripped.startswith("//") or stripped.startswith("/*")
                    or stripped.startswith("*")):
                continue
            assert f not in line or "POST" == f and ("//" in line), (
                f"PortfolioTerminal must not POST: {line.strip()}"
            )


def test_main_py_mounts_paper_executed_router():
    src = Path("apps/api/src/main.py").read_text(encoding="utf-8")
    assert "paper_executed_router" in src
    assert "from apps.api.src.api.paper_executed import router" in src


def test_header_shows_live_split_counts_not_filtered_total():
    """Header must surface live counts always — operators need to see
    `live=0, replay=18` simultaneously, not just whichever side the
    include_replay toggle picked."""
    src = PAGE.read_text(encoding="utf-8")
    assert "live_trades_count" in src, (
        "header must read live_trades_count from execSummary"
    )
    assert "live_open_positions_count" in src, (
        "header must read live_open_positions_count from execSummary"
    )
    # Old behaviour rendered execSummary.trades_total in the headline,
    # which silently flipped between live-only and live+replay when the
    # toggle changed. That ambiguity is why we made counts always-on.
    assert ("execSummary?.trades_total ?? 0} executed trades"
            not in src), (
        "header must not use trades_total in the headline (ambiguous)"
    )


def test_banner_shows_explicit_replay_counts():
    src = PAGE.read_text(encoding="utf-8")
    # Banner has to spell out the recovered counts so the operator
    # can see "18 recovered replay trades · 18 recovered open positions"
    # without flipping include_replay.
    assert "replay_trades_count" in src
    assert "replay_open_positions_count" in src
    assert "recovered replay trades" in src
    assert "NOT live trading activity" in src, (
        "banner must explicitly state these are not live trades"
    )


def test_toggle_label_is_show_recovered_replay_data():
    src = PAGE.read_text(encoding="utf-8")
    # Brief required wording: "Show recovered replay data"
    assert "Show recovered replay data" in src


def test_hooks_type_pins_split_counts():
    src = HOOKS.read_text(encoding="utf-8")
    for key in ("live_trades_count", "replay_trades_count",
                "live_open_positions_count", "replay_open_positions_count"):
        assert key in src, f"ExecutedSummary type missing {key}"
