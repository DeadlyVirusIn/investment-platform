"""Phase 11W (Phase D.3) — research observability helpers.

Read-only aggregations over `research_ro.*`. NEVER returns body
text. NEVER reads from public execution tables. NEVER computes
trading performance. NEVER ranks providers by quality. NEVER uses
recommendation language in output keys.

Three public functions:
  * `get_provider_metrics(session, start_date, end_date)`
  * `get_provider_comparison(session, symbol, as_of)`
  * `get_recent_research_provider_runs(session, limit=50)`

All return JSON-serializable lists of dicts. Status counts and
cost / latency / token aggregates are present; body text is not.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Allowed source tables — observability functions are restricted to
# research_ro.* by convention + tested by source-grep.
# ---------------------------------------------------------------------------

_ALLOWED_SOURCE_TABLES: tuple[str, ...] = (
    "research_ro.research_run",
    "research_ro.research_agent_output",
)


def get_provider_metrics(
    session: Session,
    start_date: dt.date,
    end_date: dt.date,
) -> list[dict[str, Any]]:
    """Aggregate per-(provider, model_id) metrics over the inclusive
    date range. Read-only — issues a single SELECT against
    research_ro.research_run. Returns one row per
    (provider, model_id) combination active in the window.
    """
    if not isinstance(start_date, dt.date):
        raise ValueError("start_date must be a datetime.date")
    if not isinstance(end_date, dt.date):
        raise ValueError("end_date must be a datetime.date")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")

    rows = session.execute(
        text(
            """
            SELECT
                provider,
                model_id,
                COUNT(*)                                AS run_count,
                SUM(CASE WHEN status='succeeded'        THEN 1 ELSE 0 END) AS succeeded_count,
                SUM(CASE WHEN status='failed'           THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN status='token_violation'  THEN 1 ELSE 0 END) AS token_violation_count,
                SUM(CASE WHEN status='provider_error'   THEN 1 ELSE 0 END) AS provider_error_count,
                SUM(CASE WHEN status='cost_exceeded'    THEN 1 ELSE 0 END) AS cost_exceeded_count,
                COALESCE(SUM(cost_usd), 0)              AS total_cost_usd,
                COALESCE(AVG(cost_usd), 0)              AS avg_cost_usd,
                COALESCE(SUM(tokens_in), 0)             AS total_tokens_in,
                COALESCE(SUM(tokens_out), 0)            AS total_tokens_out
            FROM research_ro.research_run
            WHERE as_of BETWEEN :start AND :end
            GROUP BY provider, model_id
            ORDER BY provider, model_id
            """
        ),
        {"start": start_date, "end": end_date},
    ).mappings().all()

    # Latency lives on agent_output rows (per-call), not run rows.
    # Pull avg_latency_ms separately to keep the per-provider join
    # simple. Read-only.
    latency_rows = session.execute(
        text(
            """
            SELECT
                ao.provider,
                ao.model_id,
                COALESCE(AVG(ao.latency_ms), 0) AS avg_latency_ms
            FROM research_ro.research_agent_output ao
            JOIN research_ro.research_run rr ON rr.id = ao.run_id
            WHERE rr.as_of BETWEEN :start AND :end
            GROUP BY ao.provider, ao.model_id
            """
        ),
        {"start": start_date, "end": end_date},
    ).mappings().all()
    latency_by_key = {
        (r["provider"], r["model_id"]): float(r["avg_latency_ms"])
        for r in latency_rows
    }

    out: list[dict[str, Any]] = []
    for r in rows:
        key = (r["provider"], r["model_id"])
        out.append({
            "provider": r["provider"],
            "model_id": r["model_id"],
            "run_count": int(r["run_count"]),
            "succeeded_count": int(r["succeeded_count"] or 0),
            "failed_count": int(r["failed_count"] or 0),
            "token_violation_count": int(r["token_violation_count"] or 0),
            "provider_error_count": int(r["provider_error_count"] or 0),
            "cost_exceeded_count": int(r["cost_exceeded_count"] or 0),
            "total_cost_usd": float(r["total_cost_usd"] or 0),
            "avg_cost_usd": float(r["avg_cost_usd"] or 0),
            "total_tokens_in": int(r["total_tokens_in"] or 0),
            "total_tokens_out": int(r["total_tokens_out"] or 0),
            "avg_latency_ms": float(latency_by_key.get(key, 0.0)),
        })
    return out


def get_provider_comparison(
    session: Session,
    symbol: str,
    as_of: dt.date,
) -> list[dict[str, Any]]:
    """Per-(provider, model_id) comparison rows for the same symbol /
    as_of. Returns metadata only — never body text. One row per
    research_run; if a successful agent_output exists, its body_hash
    is included for provenance (NOT the body itself)."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol must be a non-empty str")
    if not isinstance(as_of, dt.date):
        raise ValueError("as_of must be a datetime.date")

    rows = session.execute(
        text(
            """
            SELECT
                rr.provider,
                rr.model_id,
                rr.status,
                rr.prompt_hash,
                rr.input_snapshot_hash,
                rr.cost_usd,
                rr.tokens_in,
                rr.tokens_out,
                rr.started_at,
                ao.body_hash AS agent_body_hash,
                ao.latency_ms AS agent_latency_ms
            FROM research_ro.research_run rr
            LEFT JOIN research_ro.research_agent_output ao
              ON ao.run_id = rr.id
            WHERE rr.symbol = :symbol AND rr.as_of = :as_of
            ORDER BY rr.provider, rr.model_id, rr.started_at
            """
        ),
        {"symbol": symbol, "as_of": as_of},
    ).mappings().all()
    return [
        {
            "provider": r["provider"],
            "model_id": r["model_id"],
            "status": r["status"],
            "prompt_hash": r["prompt_hash"],
            "input_snapshot_hash": r["input_snapshot_hash"],
            "body_hash": r["agent_body_hash"],
            "cost_usd": float(r["cost_usd"] or 0),
            "tokens_in": int(r["tokens_in"] or 0),
            "tokens_out": int(r["tokens_out"] or 0),
            "latency_ms": (
                int(r["agent_latency_ms"])
                if r["agent_latency_ms"] is not None
                else None
            ),
            "created_at": (
                r["started_at"].isoformat()
                if r["started_at"] is not None
                else None
            ),
        }
        for r in rows
    ]


def get_recent_research_provider_runs(
    session: Session,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Most-recent N research_run rows (metadata only). NEVER
    returns body text. Default 50; capped at 500 to bound payload."""
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive int")
    capped = min(limit, 500)
    rows = session.execute(
        text(
            """
            SELECT
                id, symbol, as_of, provider, model_id, model_version,
                status, prompt_hash, input_snapshot_hash,
                tokens_in, tokens_out, cost_usd,
                triggered_by, operator_id, started_at, finished_at
            FROM research_ro.research_run
            ORDER BY started_at DESC
            LIMIT :lim
            """
        ),
        {"lim": capped},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "symbol": r["symbol"],
            "as_of": r["as_of"].isoformat(),
            "provider": r["provider"],
            "model_id": r["model_id"],
            "model_version": r["model_version"],
            "status": r["status"],
            "prompt_hash": r["prompt_hash"],
            "input_snapshot_hash": r["input_snapshot_hash"],
            "tokens_in": int(r["tokens_in"] or 0),
            "tokens_out": int(r["tokens_out"] or 0),
            "cost_usd": float(r["cost_usd"] or 0),
            "triggered_by": r["triggered_by"],
            "operator_id": r["operator_id"],
            "started_at": (
                r["started_at"].isoformat()
                if r["started_at"] is not None
                else None
            ),
            "finished_at": (
                r["finished_at"].isoformat()
                if r["finished_at"] is not None
                else None
            ),
        }
        for r in rows
    ]
