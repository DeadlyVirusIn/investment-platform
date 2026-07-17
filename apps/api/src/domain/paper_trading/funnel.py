"""Phase 2 stock fix Phase 4 — paper execution funnel writer + readers.

Single insert helper for `paper_execution_funnel`. Idempotent on
(run_date, portfolio_id) via DB unique constraint. Read helpers
back the new GET endpoints in apps.api.src.api.paper_funnel.

Lives at the auto_trader boundary — called from the worker job
`run_paper_trading` after a portfolio is processed.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Skip-code keys we explicitly persist as columns. Anything else
# rolls up under skip_unknown_reason.
KNOWN_SKIP_CODES: tuple[str, ...] = (
    "portfolio_full",
    "duplicate_holding",
    "pending_sell_same_asset",
    "sizing_below_threshold",
    "position_too_small",
    "cash_constraint",
    "execution_failure",
)


@dataclass
class PaperFunnelCounts:
    buy_candidates_total: int = 0
    buys_executed: int = 0
    sells_executed: int = 0
    skip_portfolio_full: int = 0
    skip_duplicate_holding: int = 0
    skip_pending_sell_same_asset: int = 0
    skip_sizing_below_threshold: int = 0
    skip_position_too_small: int = 0
    skip_cash_constraint: int = 0
    skip_execution_failure: int = 0
    skip_unknown_reason: int = 0


@dataclass
class PaperFunnelSnapshot:
    open_positions_at_start: int
    max_open_positions: int
    cash_at_start: Decimal
    equity_at_start: Decimal


def counts_from_buy_skips(
    buy_skips: list[dict[str, Any]] | None,
) -> Counter:
    """Roll up auto_trader.AutoTradeRunResult.buy_skips into per-reason
    integer counts. Unknown reasons funnel to 'unknown_reason'."""
    out: Counter = Counter()
    for s in buy_skips or []:
        reason = str(s.get("reason") or "")
        if reason in KNOWN_SKIP_CODES:
            out[reason] += 1
        else:
            out["unknown_reason"] += 1
    return out


def upsert_funnel_row(
    session: Session,
    *,
    run_date: dt.date,
    portfolio_id: str,
    counts: PaperFunnelCounts,
    snapshot: PaperFunnelSnapshot,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert or update one row per (run_date, portfolio_id)."""
    payload: dict[str, Any] = {
        "run_date": run_date,
        "portfolio_id": portfolio_id,
        **asdict(counts),
        "open_positions_at_start": snapshot.open_positions_at_start,
        "max_open_positions": snapshot.max_open_positions,
        "cash_at_start": str(snapshot.cash_at_start),
        "equity_at_start": str(snapshot.equity_at_start),
        "details_json": json.dumps(details or {}),
    }
    session.execute(
        text(
            """
            INSERT INTO paper_execution_funnel
              (run_date, portfolio_id,
               buy_candidates_total, buys_executed, sells_executed,
               skip_portfolio_full, skip_duplicate_holding,
               skip_pending_sell_same_asset, skip_sizing_below_threshold,
               skip_position_too_small, skip_cash_constraint,
               skip_execution_failure, skip_unknown_reason,
               open_positions_at_start, max_open_positions,
               cash_at_start, equity_at_start, details_json)
            VALUES
              (:run_date, :portfolio_id,
               :buy_candidates_total, :buys_executed, :sells_executed,
               :skip_portfolio_full, :skip_duplicate_holding,
               :skip_pending_sell_same_asset, :skip_sizing_below_threshold,
               :skip_position_too_small, :skip_cash_constraint,
               :skip_execution_failure, :skip_unknown_reason,
               :open_positions_at_start, :max_open_positions,
               :cash_at_start, :equity_at_start,
               CAST(:details_json AS jsonb))
            ON CONFLICT ON CONSTRAINT ux_paper_funnel_run_portfolio
            DO UPDATE SET
              buy_candidates_total         = EXCLUDED.buy_candidates_total,
              buys_executed                = EXCLUDED.buys_executed,
              sells_executed               = EXCLUDED.sells_executed,
              skip_portfolio_full          = EXCLUDED.skip_portfolio_full,
              skip_duplicate_holding       = EXCLUDED.skip_duplicate_holding,
              skip_pending_sell_same_asset = EXCLUDED.skip_pending_sell_same_asset,
              skip_sizing_below_threshold  = EXCLUDED.skip_sizing_below_threshold,
              skip_position_too_small      = EXCLUDED.skip_position_too_small,
              skip_cash_constraint         = EXCLUDED.skip_cash_constraint,
              skip_execution_failure       = EXCLUDED.skip_execution_failure,
              skip_unknown_reason          = EXCLUDED.skip_unknown_reason,
              details_json                 = EXCLUDED.details_json
            """
        ),
        payload,
    )


# ---------------------------------------------------------------------------
# Read helpers — SELECT-only, back the GET endpoints
# ---------------------------------------------------------------------------


def recent_rows(
    session: Session, *, days: int = 14, include_user_books: bool = False,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT run_date,
                   SUM(buy_candidates_total)         AS buy_candidates_total,
                   SUM(buys_executed)                AS buys_executed,
                   SUM(sells_executed)               AS sells_executed,
                   SUM(skip_portfolio_full)          AS skip_portfolio_full,
                   SUM(skip_duplicate_holding)       AS skip_duplicate_holding,
                   SUM(skip_pending_sell_same_asset) AS skip_pending_sell_same_asset,
                   SUM(skip_sizing_below_threshold)  AS skip_sizing_below_threshold,
                   SUM(skip_position_too_small)      AS skip_position_too_small,
                   SUM(skip_cash_constraint)         AS skip_cash_constraint,
                   SUM(skip_execution_failure)       AS skip_execution_failure,
                   SUM(skip_unknown_reason)          AS skip_unknown_reason
              FROM paper_execution_funnel f
              JOIN paper_portfolio p ON p.id = f.portfolio_id
             WHERE run_date >= CURRENT_DATE - (:days)::int
               AND (:include_user_books OR p.name NOT LIKE 'user:%')
             GROUP BY run_date ORDER BY run_date DESC
            """
        ),
        {"days": days, "include_user_books": include_user_books},
    ).mappings().all()
    return [dict(r) for r in rows]


def by_portfolio(
    session: Session, *, portfolio_id: str, days: int = 14,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT run_date, buy_candidates_total, buys_executed,
                   sells_executed,
                   skip_portfolio_full, skip_duplicate_holding,
                   skip_pending_sell_same_asset,
                   skip_sizing_below_threshold, skip_position_too_small,
                   skip_cash_constraint, skip_execution_failure,
                   skip_unknown_reason,
                   open_positions_at_start, max_open_positions,
                   cash_at_start, equity_at_start
              FROM paper_execution_funnel
             WHERE portfolio_id = :pid
               AND run_date >= CURRENT_DATE - (:days)::int
             ORDER BY run_date DESC
            """
        ),
        {"pid": portfolio_id, "days": days},
    ).mappings().all()
    return [dict(r) for r in rows]


def reason_distribution(
    session: Session, *, days: int = 14, include_user_books: bool = False,
) -> dict[str, int]:
    row = session.execute(
        text(
            """
            SELECT
              SUM(skip_portfolio_full)          AS portfolio_full,
              SUM(skip_duplicate_holding)       AS duplicate_holding,
              SUM(skip_pending_sell_same_asset) AS pending_sell_same_asset,
              SUM(skip_sizing_below_threshold)  AS sizing_below_threshold,
              SUM(skip_position_too_small)      AS position_too_small,
              SUM(skip_cash_constraint)         AS cash_constraint,
              SUM(skip_execution_failure)       AS execution_failure,
              SUM(skip_unknown_reason)          AS unknown_reason
              FROM paper_execution_funnel f
              JOIN paper_portfolio p ON p.id = f.portfolio_id
             WHERE run_date >= CURRENT_DATE - (:days)::int
               AND (:include_user_books OR p.name NOT LIKE 'user:%')
            """
        ),
        {"days": days, "include_user_books": include_user_books},
    ).mappings().one()
    return {k: int(v or 0) for k, v in dict(row).items()}


def saturation_snapshot(session: Session, *, include_user_books: bool = False) -> list[dict[str, Any]]:
    """Latest saturation state per portfolio. Reads from the most
    recent funnel row + live position count + cash."""
    rows = session.execute(
        text(
            """
            WITH latest AS (
              SELECT DISTINCT ON (portfolio_id) *
                FROM paper_execution_funnel
               ORDER BY portfolio_id, run_date DESC
            ),
            oc AS (
              SELECT portfolio_id, COUNT(*) AS open_count
                FROM paper_position WHERE is_open=true
               GROUP BY portfolio_id
            )
            SELECT pp.id, pp.name, pp.cash::numeric(20,2) AS cash,
                   COALESCE(oc.open_count, 0) AS open_count,
                   COALESCE(
                     ((pp.config_json::jsonb)->>'max_open_positions')::int,
                     30
                   ) AS max_open,
                   l.run_date AS last_funnel_run,
                   l.buy_candidates_total AS last_candidates,
                   (l.skip_portfolio_full
                    + l.skip_duplicate_holding
                    + l.skip_pending_sell_same_asset
                    + l.skip_sizing_below_threshold
                    + l.skip_position_too_small
                    + l.skip_cash_constraint
                    + l.skip_execution_failure
                    + l.skip_unknown_reason) AS last_total_skips
              FROM paper_portfolio pp
              LEFT JOIN oc ON oc.portfolio_id = pp.id
              LEFT JOIN latest l ON l.portfolio_id = pp.id
             WHERE (:include_user_books OR pp.name NOT LIKE 'user:%')
             ORDER BY pp.created_at
            """
        ), {"include_user_books": include_user_books}
    ).mappings().all()
    return [dict(r) for r in rows]
