"""Phase Opt-C2 Pre-Canary 0.2 — options execution funnel writer.

Single insert helper for `options_execution_funnel`. Writers MUST
call this; never INSERT directly elsewhere. Idempotent on
(run_date, portfolio_id) via DB unique constraint.

Read helpers below back the three GET endpoints in routes.py.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class FunnelCounts:
    candidates_total: int = 0
    candidates_after_universe: int = 0
    candidates_after_strategy: int = 0
    promoted: int = 0
    filled: int = 0
    closed_today: int = 0
    skip_canary_disabled: int = 0
    skip_slot_full: int = 0
    skip_over_capital_cap: int = 0
    skip_dte_outside_window: int = 0
    skip_no_chain_for_proposal: int = 0
    skip_proposal_duplicate: int = 0
    skip_other: int = 0


@dataclass
class FunnelSnapshot:
    open_at_start: int
    open_at_end: int
    cash_at_start: Decimal
    cash_at_end: Decimal


def upsert_funnel_row(
    session: Session,
    *,
    run_date: dt.date,
    portfolio_id: str,
    counts: FunnelCounts,
    snapshot: FunnelSnapshot,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert or update one funnel row per (run_date, portfolio_id).
    UPSERT semantics: re-running on same date overwrites counts."""
    payload: dict[str, Any] = {
        "run_date": run_date,
        "portfolio_id": portfolio_id,
        **asdict(counts),
        "open_at_start": snapshot.open_at_start,
        "open_at_end": snapshot.open_at_end,
        "cash_at_start": str(snapshot.cash_at_start),
        "cash_at_end": str(snapshot.cash_at_end),
        "details_json": json.dumps(details or {}),
    }
    session.execute(
        text(
            """
            INSERT INTO options_execution_funnel
              (run_date, portfolio_id,
               candidates_total, candidates_after_universe,
               candidates_after_strategy,
               promoted, filled, closed_today,
               skip_canary_disabled, skip_slot_full,
               skip_over_capital_cap, skip_dte_outside_window,
               skip_no_chain_for_proposal, skip_proposal_duplicate,
               skip_other,
               open_at_start, open_at_end,
               cash_at_start, cash_at_end,
               details_json)
            VALUES
              (:run_date, :portfolio_id,
               :candidates_total, :candidates_after_universe,
               :candidates_after_strategy,
               :promoted, :filled, :closed_today,
               :skip_canary_disabled, :skip_slot_full,
               :skip_over_capital_cap, :skip_dte_outside_window,
               :skip_no_chain_for_proposal, :skip_proposal_duplicate,
               :skip_other,
               :open_at_start, :open_at_end,
               :cash_at_start, :cash_at_end,
               CAST(:details_json AS jsonb))
            ON CONFLICT ON CONSTRAINT ux_opt_funnel_run_portfolio
            DO UPDATE SET
              candidates_total          = EXCLUDED.candidates_total,
              candidates_after_universe = EXCLUDED.candidates_after_universe,
              candidates_after_strategy = EXCLUDED.candidates_after_strategy,
              promoted                  = EXCLUDED.promoted,
              filled                    = EXCLUDED.filled,
              closed_today              = EXCLUDED.closed_today,
              skip_canary_disabled      = EXCLUDED.skip_canary_disabled,
              skip_slot_full            = EXCLUDED.skip_slot_full,
              skip_over_capital_cap     = EXCLUDED.skip_over_capital_cap,
              skip_dte_outside_window   = EXCLUDED.skip_dte_outside_window,
              skip_no_chain_for_proposal= EXCLUDED.skip_no_chain_for_proposal,
              skip_proposal_duplicate   = EXCLUDED.skip_proposal_duplicate,
              skip_other                = EXCLUDED.skip_other,
              open_at_end               = EXCLUDED.open_at_end,
              cash_at_end               = EXCLUDED.cash_at_end,
              details_json              = EXCLUDED.details_json
            """
        ),
        payload,
    )


# ---------------------------------------------------------------------------
# Read helpers (back the API endpoints — SELECT-only)
# ---------------------------------------------------------------------------


def recent_rows(
    session: Session, *, days: int = 14,
) -> list[dict[str, Any]]:
    """Per-day totals across all canary portfolios for the last `days`."""
    rows = session.execute(
        text(
            """
            SELECT run_date,
                   SUM(candidates_total)        AS candidates_total,
                   SUM(promoted)                AS promoted,
                   SUM(filled)                  AS filled,
                   SUM(closed_today)            AS closed_today,
                   SUM(skip_canary_disabled)    AS skip_canary_disabled,
                   SUM(skip_slot_full)          AS skip_slot_full,
                   SUM(skip_over_capital_cap)   AS skip_over_capital_cap,
                   SUM(skip_dte_outside_window) AS skip_dte_outside_window,
                   SUM(skip_no_chain_for_proposal) AS skip_no_chain_for_proposal,
                   SUM(skip_proposal_duplicate) AS skip_proposal_duplicate,
                   SUM(skip_other)              AS skip_other
              FROM options_execution_funnel
             WHERE run_date >= CURRENT_DATE - (:days)::int
             GROUP BY run_date ORDER BY run_date DESC
            """
        ),
        {"days": days},
    ).mappings().all()
    return [dict(r) for r in rows]


def by_portfolio(
    session: Session, *, portfolio_id: str, days: int = 14,
) -> list[dict[str, Any]]:
    """Per-day rows for ONE portfolio."""
    rows = session.execute(
        text(
            """
            SELECT run_date, candidates_total, promoted, filled,
                   closed_today, skip_slot_full, skip_over_capital_cap,
                   skip_dte_outside_window, skip_no_chain_for_proposal,
                   skip_proposal_duplicate, skip_other,
                   open_at_start, open_at_end,
                   cash_at_start, cash_at_end
              FROM options_execution_funnel
             WHERE portfolio_id = :pid
               AND run_date >= CURRENT_DATE - (:days)::int
             ORDER BY run_date DESC
            """
        ),
        {"pid": portfolio_id, "days": days},
    ).mappings().all()
    return [dict(r) for r in rows]


def reason_distribution(
    session: Session, *, days: int = 14,
) -> dict[str, int]:
    """Total counts per skip-reason code over the last `days`."""
    row = session.execute(
        text(
            """
            SELECT
              SUM(skip_canary_disabled)       AS canary_disabled,
              SUM(skip_slot_full)             AS slot_full,
              SUM(skip_over_capital_cap)      AS over_capital_cap,
              SUM(skip_dte_outside_window)    AS dte_outside_window,
              SUM(skip_no_chain_for_proposal) AS no_chain_for_proposal,
              SUM(skip_proposal_duplicate)    AS proposal_duplicate,
              SUM(skip_other)                 AS other
              FROM options_execution_funnel
             WHERE run_date >= CURRENT_DATE - (:days)::int
            """
        ),
        {"days": days},
    ).mappings().one()
    return {k: int(v or 0) for k, v in dict(row).items()}


def list_portfolios(session: Session) -> list[dict[str, Any]]:
    """Lightweight list of all options paper portfolios with live
    open-trade count + cash state."""
    rows = session.execute(
        text(
            """
            SELECT pp.id, pp.name, pp.cash_initial, pp.cash_current,
                   pp.max_open_trades, pp.max_capital_per_trade,
                   pp.active, pp.universe, pp.strategy_family,
                   COALESCE(oc.open_count, 0) AS open_count,
                   pp.created_at, pp.updated_at
              FROM options_paper_portfolio pp
              LEFT JOIN (
                SELECT portfolio_id, COUNT(*) AS open_count
                  FROM options_paper_position
                 WHERE released_at IS NULL
                 GROUP BY portfolio_id
              ) oc ON oc.portfolio_id = pp.id
             ORDER BY pp.created_at
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]
