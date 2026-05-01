"""Phase 11W (Phase B + Phase F) — Research Intelligence read-only API.

GET-only. NO POST/PUT/PATCH/DELETE handlers — Phase B + F ship
read-only safety scaffolding only. The router is mounted from
`apps/api/src/main.py` ONLY when `settings.RESEARCH_RO_ENABLED` is
True (production default False). When the flag is off, the router
is not mounted and every `/api/research/*` path returns 404.

NEVER imports `feature_engine`, `recommendation_engine`,
`shadow_scorer`, `drift_monitor`, `auto_trader`, `paper_execution`,
or any execution-mutating module. Enforced by an architectural CI
test (`test_research_no_execution_imports`).

Phase F additions over Phase B:
  * Endpoints now read real `research_ro.research_run` + agent_output
    rows when present.
  * Bodies are run through the server-side safety filter
    (`assert_no_action_language`) before being returned. Bodies that
    fail the filter are stripped and replaced with a sanitized
    `{"safety_status": "unsafe"}` payload — the raw body NEVER
    leaves the server.
  * Adds `/api/research/usage` and `/api/research/audit` for
    operator visibility (read-only).

All Phase F endpoints remain GET-only and reject any unsafe content
fail-closed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from apps.api.src.db import SessionLocal


router = APIRouter(prefix="/research", tags=["research"])


# ---------------------------------------------------------------------------
# Safety wrapper — server-side fail-closed
# ---------------------------------------------------------------------------


def _safe_body_or_blank(body: str | None) -> tuple[str | None, str]:
    """Run the server-side forbidden-token check. Returns
    `(rendered_body, safety_status)` where:
      * `safety_status='safe'` → return body verbatim
      * `safety_status='unsafe'` → return None (caller renders the
        client-side fail-closed block)
    """
    if not body:
        return None, "empty"
    try:
        from apps.api.src.research.safety import (
            assert_no_action_language,
        )
        assert_no_action_language(body)
        return body, "safe"
    except Exception:  # noqa: BLE001
        return None, "unsafe"


def _row_to_run_payload(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "symbol": r["symbol"],
        "as_of": r["as_of"].isoformat() if r["as_of"] else None,
        "provider": r["provider"],
        "model_id": r["model_id"],
        "model_version": r["model_version"],
        "prompt_hash": r["prompt_hash"],
        "tokens_in": int(r["tokens_in"] or 0),
        "tokens_out": int(r["tokens_out"] or 0),
        "cost_usd": float(r["cost_usd"] or 0.0),
        "status": r["status"],
        "started_at": (
            r["started_at"].isoformat() if r["started_at"] else None
        ),
        "finished_at": (
            r["finished_at"].isoformat() if r["finished_at"] else None
        ),
        "operator_id": r["operator_id"],
        "triggered_by": r["triggered_by"],
        "decision_id": r.get("decision_id"),
    }


def _agent_output_to_payload(r: dict[str, Any]) -> dict[str, Any]:
    body = r.get("body")
    safe_body, safety_status = _safe_body_or_blank(body)
    return {
        "id": str(r["id"]),
        "agent_role": r["agent_role"],
        "sequence_no": int(r["sequence_no"]),
        "provider": r["provider"],
        "model_id": r["model_id"],
        "model_version": r["model_version"],
        "prompt_hash": r["prompt_hash"],
        "tokens_in": int(r["tokens_in"] or 0),
        "tokens_out": int(r["tokens_out"] or 0),
        "cost_usd": float(r["cost_usd"] or 0.0),
        "status": r["status"],
        "created_at": (
            r["created_at"].isoformat() if r.get("created_at") else None
        ),
        "safety_status": safety_status,
        "body": safe_body,  # None when unsafe; UI renders SafetyFailure
    }


# ---------------------------------------------------------------------------
# Read-only endpoints
# ---------------------------------------------------------------------------


@router.get("/runs")
def list_runs(
    cursor: str | None = None,
    limit: int = 20,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Read recent research_run rows. When the table is empty (Phase
    B / no orchestration enabled), returns the documented empty
    shape so existing UI consumers continue to work."""
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be 1..200")
    with SessionLocal() as s:
        params: dict[str, Any] = {"lim": limit}
        where = ""
        if symbol:
            where = "WHERE symbol = :sym"
            params["sym"] = symbol.upper()
        rows = s.execute(text(
            f"""
            SELECT id, symbol, as_of, provider, model_id, model_version,
                   prompt_hash, tokens_in, tokens_out, cost_usd,
                   status, started_at, finished_at, operator_id,
                   triggered_by, decision_id
            FROM research_ro.research_run
            {where}
            ORDER BY started_at DESC
            LIMIT :lim
            """
        ), params).mappings().all()
    return {
        "runs": [_row_to_run_payload(dict(r)) for r in rows],
        "next_cursor": None,
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """Detail view: run + its agent outputs. Each output body is
    safety-filtered before return."""
    try:
        # uuid sanity: research_run.id is a uuid; the DB cast will
        # 400 otherwise. Pre-validate to avoid leaking SQL errors.
        import uuid as _uuid
        _uuid.UUID(run_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"invalid run_id: {exc}") from exc

    with SessionLocal() as s:
        run_row = s.execute(text(
            """
            SELECT id, symbol, as_of, provider, model_id, model_version,
                   prompt_hash, tokens_in, tokens_out, cost_usd,
                   status, started_at, finished_at, operator_id,
                   triggered_by, decision_id
            FROM research_ro.research_run
            WHERE id = CAST(:id AS uuid)
            """
        ), {"id": run_id}).mappings().first()
        if run_row is None:
            raise HTTPException(404, "research run not found")
        outputs = s.execute(text(
            """
            SELECT id, agent_role, sequence_no, body,
                   provider, model_id, model_version, prompt_hash,
                   tokens_in, tokens_out, cost_usd, status, created_at
            FROM research_ro.research_agent_output
            WHERE run_id = CAST(:id AS uuid)
            ORDER BY sequence_no ASC
            """
        ), {"id": run_id}).mappings().all()
    return {
        "run": _row_to_run_payload(dict(run_row)),
        "outputs": [_agent_output_to_payload(dict(o)) for o in outputs],
    }


@router.get("/ticker/{symbol}/latest")
def latest_run_for_ticker(symbol: str) -> dict[str, Any]:
    """Latest research_run for a ticker. Returns `{run: null}` when
    there is no row — UI uses this to show its empty state."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    with SessionLocal() as s:
        row = s.execute(text(
            """
            SELECT id, symbol, as_of, provider, model_id, model_version,
                   prompt_hash, tokens_in, tokens_out, cost_usd,
                   status, started_at, finished_at, operator_id,
                   triggered_by, decision_id
            FROM research_ro.research_run
            WHERE symbol = :sym
            ORDER BY as_of DESC, started_at DESC
            LIMIT 1
            """
        ), {"sym": sym}).mappings().first()
    if row is None:
        return {"symbol": sym, "run": None}
    return {"symbol": sym, "run": _row_to_run_payload(dict(row))}


@router.get("/decision/{decision_id}")
def runs_for_decision(decision_id: str) -> dict[str, Any]:
    """All runs tagged with a given decision_id."""
    with SessionLocal() as s:
        rows = s.execute(text(
            """
            SELECT id, symbol, as_of, provider, model_id, model_version,
                   prompt_hash, tokens_in, tokens_out, cost_usd,
                   status, started_at, finished_at, operator_id,
                   triggered_by, decision_id
            FROM research_ro.research_run
            WHERE decision_id = :did
            ORDER BY started_at DESC
            """
        ), {"did": decision_id}).mappings().all()
    return {
        "decision_id": decision_id,
        "runs": [_row_to_run_payload(dict(r)) for r in rows],
    }


# ---------------------------------------------------------------------------
# Phase F additions — usage + audit (read-only)
# ---------------------------------------------------------------------------


@router.get("/usage")
def get_usage(operator_id: str | None = None) -> dict[str, Any]:
    """Phase F: usage rollup, optionally scoped to a single operator.
    Reads `research_manual_run_audit` and `research_run`. Counts
    runs/rejections today; never returns raw bodies."""
    today_filter = (
        "(created_at AT TIME ZONE 'UTC')::date "
        "= (now() AT TIME ZONE 'UTC')::date"
    )
    where_op = "AND operator_id = :op" if operator_id else ""
    params: dict[str, Any] = {}
    if operator_id:
        params["op"] = operator_id
    with SessionLocal() as s:
        try:
            rows = s.execute(text(
                f"""
                SELECT
                  count(*) FILTER (WHERE status='accepted')   AS accepted,
                  count(*) FILTER (WHERE status='duplicate')  AS duplicate,
                  count(*) FILTER (WHERE status='rejected')   AS rejected,
                  count(*) FILTER (WHERE status='in_flight')  AS in_flight,
                  count(*) FILTER (WHERE status='error')      AS errored,
                  COALESCE(SUM(actual_cost_usd), 0)::float8   AS cost_usd_today
                FROM research_ro.research_manual_run_audit
                WHERE {today_filter} {where_op}
                """
            ), params).mappings().first()
        except Exception:  # noqa: BLE001
            return {
                "operator_id": operator_id,
                "audit_table": "absent",
                "summary": {
                    "accepted": 0, "duplicate": 0, "rejected": 0,
                    "in_flight": 0, "errored": 0, "cost_usd_today": 0.0,
                },
            }
    return {
        "operator_id": operator_id,
        "audit_table": "present",
        "summary": {
            "accepted": int(rows["accepted"] or 0),
            "duplicate": int(rows["duplicate"] or 0),
            "rejected": int(rows["rejected"] or 0),
            "in_flight": int(rows["in_flight"] or 0),
            "errored": int(rows["errored"] or 0),
            "cost_usd_today": float(rows["cost_usd_today"] or 0.0),
        },
    }


@router.get("/audit")
def list_audit(limit: int = 50) -> dict[str, Any]:
    """Phase F: recent audit rows for operator visibility. Returns
    metadata only — never the prompt or the body."""
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be 1..500")
    with SessionLocal() as s:
        try:
            rows = s.execute(text(
                """
                SELECT id, created_at, operator_id, symbol, as_of,
                       provider, model_id, request_source, status,
                       rejection_reason, anomaly_flags,
                       research_run_id, request_id,
                       actual_cost_usd, estimated_cost_usd
                FROM research_ro.research_manual_run_audit
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ), {"lim": limit}).mappings().all()
        except Exception:  # noqa: BLE001
            return {"audit_table": "absent", "rows": []}
    return {
        "audit_table": "present",
        "rows": [
            {
                "id": str(r["id"]),
                "created_at": (
                    r["created_at"].isoformat() if r["created_at"] else None
                ),
                "operator_id": r["operator_id"],
                "symbol": r["symbol"],
                "as_of": r["as_of"].isoformat() if r["as_of"] else None,
                "provider": r["provider"],
                "model_id": r["model_id"],
                "request_source": r["request_source"],
                "status": r["status"],
                "rejection_reason": r["rejection_reason"],
                "anomaly_flags": r["anomaly_flags"],
                "research_run_id": (
                    str(r["research_run_id"]) if r["research_run_id"] else None
                ),
                "request_id": r["request_id"],
                "actual_cost_usd": (
                    float(r["actual_cost_usd"])
                    if r["actual_cost_usd"] is not None else None
                ),
                "estimated_cost_usd": (
                    float(r["estimated_cost_usd"])
                    if r["estimated_cost_usd"] is not None else None
                ),
            }
            for r in rows
        ],
    }
