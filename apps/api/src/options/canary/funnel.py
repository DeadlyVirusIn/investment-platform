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
    # P6D.36C — selector-stage skip split (previously invisible or folded
    # into skip_other / only re-derived read-side by the promotion audit).
    skip_stale_quotes: int = 0            # P6D.34D promotion freshness gate
    skip_uneconomic: int = 0              # P6D.33A economic viability gate
    skip_confidence_below_gate: int = 0   # OPTIONS_CANARY_MIN_CONFIDENCE
    # P6D.36D — enforced portfolio risk-control rejections (promote_one).
    skip_underlying_cap: int = 0          # OPTIONS_CANARY_MAX_PER_UNDERLYING
    skip_daily_cap: int = 0               # OPTIONS_CANARY_MAX_PROMOTIONS_PER_DAY
    skip_cash_floor: int = 0              # OPTIONS_CANARY_MIN_CASH_FLOOR_DOLLARS
    skip_aggregate_loss_cap: int = 0      # OPTIONS_CANARY_MAX_AGGREGATE_LOSS_DOLLARS


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

    P6D.36C merge semantics (same-day reruns must not erase history):
      * counters (candidates_total, promoted, filled, skip_*) — ADDITIVE:
        each rerun's counts are added to the stored row, so a 23:00 run's
        promoted=1 survives a later same-day rerun that promotes nothing.
      * end-state (open_at_end, cash_at_end, details_json) — last writer
        wins (they describe "now", not the run).
      * start-state (open_at_start, cash_at_start) — first writer wins
        (set on insert, never updated on conflict).
    """
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
               skip_stale_quotes, skip_uneconomic,
               skip_confidence_below_gate,
               skip_underlying_cap, skip_daily_cap,
               skip_cash_floor, skip_aggregate_loss_cap,
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
               :skip_stale_quotes, :skip_uneconomic,
               :skip_confidence_below_gate,
               :skip_underlying_cap, :skip_daily_cap,
               :skip_cash_floor, :skip_aggregate_loss_cap,
               :open_at_start, :open_at_end,
               :cash_at_start, :cash_at_end,
               CAST(:details_json AS jsonb))
            ON CONFLICT ON CONSTRAINT ux_opt_funnel_run_portfolio
            DO UPDATE SET
              -- P6D.36C: counters are ADDITIVE across same-day reruns
              -- (COALESCE: pre-095 rows may hold NULL in the new columns).
              candidates_total          = options_execution_funnel.candidates_total + EXCLUDED.candidates_total,
              candidates_after_universe = options_execution_funnel.candidates_after_universe + EXCLUDED.candidates_after_universe,
              candidates_after_strategy = options_execution_funnel.candidates_after_strategy + EXCLUDED.candidates_after_strategy,
              promoted                  = options_execution_funnel.promoted + EXCLUDED.promoted,
              filled                    = options_execution_funnel.filled + EXCLUDED.filled,
              closed_today              = options_execution_funnel.closed_today + EXCLUDED.closed_today,
              skip_canary_disabled      = options_execution_funnel.skip_canary_disabled + EXCLUDED.skip_canary_disabled,
              skip_slot_full            = options_execution_funnel.skip_slot_full + EXCLUDED.skip_slot_full,
              skip_over_capital_cap     = options_execution_funnel.skip_over_capital_cap + EXCLUDED.skip_over_capital_cap,
              skip_dte_outside_window   = options_execution_funnel.skip_dte_outside_window + EXCLUDED.skip_dte_outside_window,
              skip_no_chain_for_proposal= options_execution_funnel.skip_no_chain_for_proposal + EXCLUDED.skip_no_chain_for_proposal,
              skip_proposal_duplicate   = options_execution_funnel.skip_proposal_duplicate + EXCLUDED.skip_proposal_duplicate,
              skip_other                = options_execution_funnel.skip_other + EXCLUDED.skip_other,
              skip_stale_quotes         = COALESCE(options_execution_funnel.skip_stale_quotes, 0) + EXCLUDED.skip_stale_quotes,
              skip_uneconomic           = COALESCE(options_execution_funnel.skip_uneconomic, 0) + EXCLUDED.skip_uneconomic,
              skip_confidence_below_gate= COALESCE(options_execution_funnel.skip_confidence_below_gate, 0) + EXCLUDED.skip_confidence_below_gate,
              skip_underlying_cap       = COALESCE(options_execution_funnel.skip_underlying_cap, 0) + EXCLUDED.skip_underlying_cap,
              skip_daily_cap            = COALESCE(options_execution_funnel.skip_daily_cap, 0) + EXCLUDED.skip_daily_cap,
              skip_cash_floor           = COALESCE(options_execution_funnel.skip_cash_floor, 0) + EXCLUDED.skip_cash_floor,
              skip_aggregate_loss_cap   = COALESCE(options_execution_funnel.skip_aggregate_loss_cap, 0) + EXCLUDED.skip_aggregate_loss_cap,
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
                   SUM(skip_other)              AS skip_other,
                   COALESCE(SUM(skip_stale_quotes), 0) AS skip_stale_quotes,
                   COALESCE(SUM(skip_uneconomic), 0)   AS skip_uneconomic,
                   COALESCE(SUM(skip_confidence_below_gate), 0)
                       AS skip_confidence_below_gate,
                   COALESCE(SUM(skip_underlying_cap), 0) AS skip_underlying_cap,
                   COALESCE(SUM(skip_daily_cap), 0)      AS skip_daily_cap,
                   COALESCE(SUM(skip_cash_floor), 0)     AS skip_cash_floor,
                   COALESCE(SUM(skip_aggregate_loss_cap), 0)
                       AS skip_aggregate_loss_cap
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
                   COALESCE(skip_stale_quotes, 0)  AS skip_stale_quotes,
                   COALESCE(skip_uneconomic, 0)    AS skip_uneconomic,
                   COALESCE(skip_confidence_below_gate, 0)
                       AS skip_confidence_below_gate,
                   COALESCE(skip_underlying_cap, 0) AS skip_underlying_cap,
                   COALESCE(skip_daily_cap, 0)      AS skip_daily_cap,
                   COALESCE(skip_cash_floor, 0)     AS skip_cash_floor,
                   COALESCE(skip_aggregate_loss_cap, 0)
                       AS skip_aggregate_loss_cap,
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
              SUM(skip_other)                 AS other,
              COALESCE(SUM(skip_stale_quotes), 0) AS stale_quotes,
              COALESCE(SUM(skip_uneconomic), 0)   AS uneconomic,
              COALESCE(SUM(skip_confidence_below_gate), 0)
                  AS confidence_below_gate,
              COALESCE(SUM(skip_underlying_cap), 0) AS underlying_cap,
              COALESCE(SUM(skip_daily_cap), 0)      AS daily_cap,
              COALESCE(SUM(skip_cash_floor), 0)     AS cash_floor,
              COALESCE(SUM(skip_aggregate_loss_cap), 0)
                  AS aggregate_loss_cap
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
