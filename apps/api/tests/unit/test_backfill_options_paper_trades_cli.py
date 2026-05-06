"""CLI guard tests for the options paper-trade backfill script.

Pure argparse / env validation — no DB.
"""

from __future__ import annotations

import os

import pytest


def test_bad_from_refused(monkeypatch):
    monkeypatch.delenv("OPTIONS_PAPER_EXEC_CONFIRM", raising=False)
    from scripts.backfill_options_paper_trades import main
    rc = main(["--from", "not-a-date", "--to", "2026-05-05"])
    assert rc == 2


def test_bad_to_refused(monkeypatch):
    from scripts.backfill_options_paper_trades import main
    rc = main(["--from", "2026-04-20", "--to", "not-a-date"])
    assert rc == 2


def test_inverted_range_refused(monkeypatch):
    from scripts.backfill_options_paper_trades import main
    rc = main(["--from", "2026-05-05", "--to", "2026-04-20"])
    assert rc == 2


def test_commit_without_confirm_refused(monkeypatch):
    monkeypatch.delenv("OPTIONS_PAPER_EXEC_CONFIRM", raising=False)
    from scripts.backfill_options_paper_trades import main
    rc = main([
        "--from", "2026-04-20", "--to", "2026-05-05", "--commit",
    ])
    assert rc == 2


def test_commit_with_wrong_confirm_value_refused(monkeypatch):
    monkeypatch.setenv("OPTIONS_PAPER_EXEC_CONFIRM", "anything-else")
    from scripts.backfill_options_paper_trades import main
    rc = main([
        "--from", "2026-04-20", "--to", "2026-05-05", "--commit",
    ])
    assert rc == 2


def test_limit_per_day_out_of_range(monkeypatch):
    from scripts.backfill_options_paper_trades import main
    rc = main([
        "--from", "2026-04-20", "--to", "2026-05-05",
        "--limit-per-day", "0",
    ])
    assert rc == 2

    rc = main([
        "--from", "2026-04-20", "--to", "2026-05-05",
        "--limit-per-day", "11",
    ])
    assert rc == 2


def test_qty_out_of_range(monkeypatch):
    from scripts.backfill_options_paper_trades import main
    rc = main([
        "--from", "2026-04-20", "--to", "2026-05-05",
        "--qty", "0",
    ])
    assert rc == 2
    rc = main([
        "--from", "2026-04-20", "--to", "2026-05-05",
        "--qty", "11",
    ])
    assert rc == 2
