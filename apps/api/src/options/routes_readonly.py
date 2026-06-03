"""Read-only Options FastAPI router (Phase 11F).

ALL endpoints are GET. The module is statically scanned by tests for the
absence of POST/PUT/PATCH/DELETE decorators. There is intentionally no
mutation surface here.

NEVER imports V2 / equity / governance / ML / paper engine internals.
The only imports allowed are from `apps.api.src.options.service_readonly`
plus FastAPI + db.get_session.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options import service_readonly as svc
from apps.api.src.options.observatory import diagnostics as obs_diagnostics
from apps.api.src.options.observatory import observations as obs_observations
from apps.api.src.options.observatory import performance as obs_performance
from apps.api.src.options.observatory import replay as obs_replay
from apps.api.src.options.observatory import rules as obs_rules
from apps.api.src.options.evaluation import score_service as eval_service
from apps.api.src.options.decision_support import diagnostics as ds_diagnostics
from apps.api.src.options.decision_support import review_queue as ds_review_queue
from apps.api.src.options.decision_framing import framing_service as df_service
from apps.api.src.options.interpretation_guardrails import (
    guardrail_service as ig_service,
)


from apps.api.src.options.portfolio import service as portfolio_service

router = APIRouter(prefix="/options", tags=["options"])


PAPER_ONLY_NOTICE = "Options are paper-trading only"


@router.get("/health")
def options_health() -> dict[str, Any]:
    """Lightweight metadata endpoint — used by the WebUI banner."""
    return {
        "status": "ok",
        "paper_only": True,
        "ml_can_affect_trades": False,
        "notice": PAPER_ONLY_NOTICE,
    }


@router.get("/pipeline-status")
def options_pipeline_status(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Honest read-only diagnostic for the options daily pipeline.

    Phase 11W (incident fix): the WebUI must NOT show options as
    silently running. Phase Opt-A (2026-05-12): extended to power
    the new options Brief view + Engine State Banner. Returns
    everything the page needs to render the truth without
    further DB queries.
    """
    from sqlalchemy import text

    from apps.api.src.config import settings
    from apps.api.src.options.data_provider.thetadata_adapter import (
        classify_thetadata_preflight,
    )

    row = session.execute(text(
        """
        SELECT
          (SELECT count(*) FROM options_chain_snapshot)
            AS chain_snapshots,
          (SELECT max(snapshot_at_utc)::date FROM options_chain_snapshot)
            AS chain_max_date,
          (SELECT max(snapshot_at_utc) FROM options_chain_snapshot)
            AS chain_max_ts,
          (SELECT count(*) FROM options_feature_daily)
            AS features,
          (SELECT max(as_of_date) FROM options_feature_daily)
            AS feature_max_date,
          (SELECT count(*) FROM options_paper_trade)
            AS paper_trades,
          (SELECT max(coalesce(opened_at, created_at))::date
             FROM options_paper_trade)
            AS paper_trade_max_date,
          (SELECT max(coalesce(opened_at, created_at))
             FROM options_paper_trade)
            AS paper_trade_max_ts,
          -- Phase Opt-A extensions: shadow + outcome + scheduler counts
          (SELECT count(*) FROM options_shadow_decision_log)
            AS shadow_decisions,
          (SELECT max(run_date) FROM options_shadow_decision_log)
            AS shadow_max_date,
          (SELECT count(DISTINCT run_date)
             FROM options_shadow_decision_log)
            AS shadow_distinct_runs,
          (SELECT count(*) FROM options_strategy_outcome)
            AS outcome_rows,
          (SELECT max(computed_at_utc) FROM options_strategy_outcome)
            AS outcome_max_ts,
          (SELECT count(*) FROM job_schedule
             WHERE name LIKE '%option%')
            AS scheduler_jobs
        """
    )).mappings().first()

    # Lifecycle state for the Brief view
    chain_count = int(row["chain_snapshots"])
    shadow_count = int(row["shadow_decisions"])
    paper_count = int(row["paper_trades"])
    scheduler_jobs = int(row["scheduler_jobs"])

    # Phase Opt-B1 — ThetaData pre-flight (5-state classifier)
    thetadata_health = classify_thetadata_preflight(settings)

    # Options-viz P0d — additive read-only fields for the V2 Options
    # Visibility page. Pure SELECTs, no mutation. Mirrors the engine's
    # frozen defined-risk contract so the UI can split the candidate
    # universe into engine-compatible vs incompatible structures.
    SUPPORTED_STRATEGIES = (
        "SHORT_PUT_CREDIT_SPREAD",
        "SHORT_CALL_CREDIT_SPREAD",
        "IRON_CONDOR",
    )
    prov_row = session.execute(text(
        """
        SELECT provider, provider_version
        FROM options_chain_snapshot
        ORDER BY snapshot_at_utc DESC
        LIMIT 1
        """
    )).mappings().first()
    chain_provider = prov_row["provider"] if prov_row else None
    chain_provider_version = (
        prov_row["provider_version"] if prov_row else None
    )

    ingest_row = session.execute(text(
        """
        SELECT started_at, finished_at, provider, rows_inserted,
               rows_filtered_out, n_symbols_ok, classification
        FROM options_chain_ingest_run
        ORDER BY started_at DESC
        LIMIT 1
        """
    )).mappings().first()
    latest_ingest_run = (
        {
            "started_at": (
                ingest_row["started_at"].isoformat()
                if ingest_row["started_at"] else None
            ),
            "finished_at": (
                ingest_row["finished_at"].isoformat()
                if ingest_row["finished_at"] else None
            ),
            "provider": ingest_row["provider"],
            "rows_inserted": (
                int(ingest_row["rows_inserted"])
                if ingest_row["rows_inserted"] is not None else None
            ),
            "rows_filtered_out": (
                int(ingest_row["rows_filtered_out"])
                if ingest_row["rows_filtered_out"] is not None else None
            ),
            "n_symbols_ok": (
                int(ingest_row["n_symbols_ok"])
                if ingest_row["n_symbols_ok"] is not None else None
            ),
            "classification": ingest_row["classification"],
        }
        if ingest_row else None
    )

    chain_health_rows = session.execute(text(
        """
        SELECT underlying AS symbol,
               count(*) AS rows,
               count(*) FILTER (WHERE bid > 0 AND ask > bid)
                 AS valid_bid_ask,
               max(snapshot_at_utc) AS latest_snapshot_at
        FROM options_chain_snapshot
        WHERE underlying IN ('SPY', 'QQQ')
        GROUP BY underlying
        ORDER BY underlying
        """
    )).mappings().all()
    chain_health = [
        {
            "symbol": r["symbol"],
            "rows": int(r["rows"]),
            "valid_bid_ask": int(r["valid_bid_ask"]),
            "latest_snapshot_at": (
                r["latest_snapshot_at"].isoformat()
                if r["latest_snapshot_at"] else None
            ),
        }
        for r in chain_health_rows
    ]

    # Candidate universe split by engine compatibility. The candidate's
    # structure lives in options_strategy_candidate.rule_id (e.g.
    # LONG_CALL, BULL_CALL_SPREAD) — the paper engine only opens the
    # three defined-risk credit/IC structures above.
    # Opt-B — date-scope to the latest run_date so engine-compatible counts
    # reflect TODAY's generator output, not the all-time history (which
    # mixes legacy directional candidates with current credit/IC ones).
    cand_rows = session.execute(text(
        """
        SELECT rule_id AS structure, count(*) AS n
        FROM options_strategy_candidate
        WHERE run_date = (SELECT max(run_date) FROM options_strategy_candidate)
        GROUP BY rule_id
        ORDER BY n DESC
        """
    )).mappings().all()
    candidate_by_structure = [
        {
            "structure": r["structure"],
            "count": int(r["n"]),
            "engine_compatible": r["structure"] in SUPPORTED_STRATEGIES,
        }
        for r in cand_rows
    ]
    candidate_total = sum(c["count"] for c in candidate_by_structure)
    candidate_compatible = sum(
        c["count"] for c in candidate_by_structure if c["engine_compatible"]
    )

    # Truthful single-sentence engine-state line for the banner
    if not settings.OPTIONS_ENABLED:
        engine_state = "dormant"
        engine_state_sentence = (
            "Options engine is dormant — OPTIONS_ENABLED is off. "
            "No chain ingest, shadow eval, or paper exec is running."
        )
    elif scheduler_jobs == 0:
        engine_state = "unscheduled"
        engine_state_sentence = (
            "Options flag is on but no daily jobs are scheduled — "
            "manual scripts only."
        )
    elif shadow_count == 0:
        engine_state = "starting"
        engine_state_sentence = (
            "Options pipeline is scheduled — collection in progress, "
            "no shadow decisions yet."
        )
    else:
        engine_state = "active"
        engine_state_sentence = (
            f"Options engine is active — {shadow_count} shadow decisions, "
            f"{paper_count} paper trades, "
            f"{chain_count} chain snapshots."
        )

    return {
        "active": False,  # back-compat field; preserved
        "last_run": None,  # back-compat field; preserved
        "reason": (
            "options evaluator not scheduled / not implemented. "
            "No daily options job exists in worker registry, scheduler, "
            "or run_daily_loop.sh. Existing rows are manual seeds only."
        ),
        # Engine state — single source of truth for the banner
        "engine_state": engine_state,
        "engine_state_sentence": engine_state_sentence,
        # Flag truths (so the UI can show exactly what's gated where)
        "options_enabled": bool(settings.OPTIONS_ENABLED),
        "options_paper_only": bool(getattr(settings, "OPTIONS_PAPER_ONLY", True)),
        "options_shadow_eval_enabled": bool(
            getattr(settings, "OPTIONS_SHADOW_EVAL_ENABLED", False)
        ),
        "options_ml_can_affect_trades": bool(
            getattr(settings, "OPTIONS_ML_CAN_AFFECT_TRADES", False)
        ),
        # Scheduler wiring count (job_schedule rows where name LIKE '%option%')
        "scheduler_jobs_count": scheduler_jobs,
        # Existing chain + feature + paper-trade counts (back-compat)
        "options_chain_snapshot_count": chain_count,
        "options_chain_snapshot_max_date": (
            row["chain_max_date"].isoformat()
            if row["chain_max_date"] else None
        ),
        "options_chain_snapshot_max_ts": (
            row["chain_max_ts"].isoformat()
            if row["chain_max_ts"] else None
        ),
        "options_feature_daily_count": int(row["features"]),
        "options_feature_daily_max_date": (
            row["feature_max_date"].isoformat()
            if row["feature_max_date"] else None
        ),
        "options_paper_trade_count": paper_count,
        "options_paper_trade_max_date": (
            row["paper_trade_max_date"].isoformat()
            if row["paper_trade_max_date"] else None
        ),
        "options_paper_trade_max_ts": (
            row["paper_trade_max_ts"].isoformat()
            if row["paper_trade_max_ts"] else None
        ),
        # Phase Opt-A extensions
        "options_shadow_decision_count": shadow_count,
        "options_shadow_decision_max_date": (
            row["shadow_max_date"].isoformat()
            if row["shadow_max_date"] else None
        ),
        "options_shadow_distinct_runs": int(row["shadow_distinct_runs"]),
        "options_strategy_outcome_count": int(row["outcome_rows"]),
        "options_strategy_outcome_max_ts": (
            row["outcome_max_ts"].isoformat()
            if row["outcome_max_ts"] else None
        ),
        # Phase Opt-B1 — ThetaData pre-flight 5-state classifier
        "thetadata_health": thetadata_health,
        # Options-viz P0d — additive read-only visibility fields
        "chain_provider": chain_provider,
        "chain_provider_version": chain_provider_version,
        "latest_ingest_run": latest_ingest_run,
        "chain_health": chain_health,
        "supported_strategies": list(SUPPORTED_STRATEGIES),
        "candidate_universe": {
            "total": candidate_total,
            "engine_compatible": candidate_compatible,
            "engine_incompatible": candidate_total - candidate_compatible,
            "by_structure": candidate_by_structure,
        },
        "next_phase_required": (
            "Phase Options-Daily — separate scope; not in stock "
            "incident fix. Requires: ThetaData ingest scheduling, "
            "options feature pipeline scheduling, options paper "
            "evaluator runner, options run-log writer."
        ),
        "notice": PAPER_ONLY_NOTICE,
    }


@router.get("/symbols")
def get_symbols(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {
        "notice": PAPER_ONLY_NOTICE,
        "symbols": svc.list_symbols(session),
    }


@router.get("/expiries")
def get_expiries(
    symbol: str = Query(..., min_length=1, max_length=12),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return {
        "notice": PAPER_ONLY_NOTICE,
        "symbol": symbol,
        "expiries": svc.list_expiries(session, symbol=symbol),
    }


@router.get("/chain")
def get_chain(
    symbol: str = Query(..., min_length=1, max_length=12),
    expiry: str = Query(..., min_length=10, max_length=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = svc.get_chain(session, symbol=symbol, expiry=expiry)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/features")
def get_features(
    symbol: str = Query(..., min_length=1, max_length=12),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = svc.get_latest_features(session, symbol=symbol)
    return {
        "notice": PAPER_ONLY_NOTICE,
        "symbol": symbol,
        "features": row,        # may be None when not yet computed
        "gamma_exposure_label": (
            "Naive gamma exposure proxy — not dealer GEX"
        ),
    }


@router.get("/paper-trades")
def list_paper_trades(
    status: str | None = Query(default=None, max_length=24),
    underlying: str | None = Query(default=None, max_length=12),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    trades = svc.list_paper_trades(
        session, status=status, underlying=underlying, limit=limit,
    )
    return {
        "notice": PAPER_ONLY_NOTICE,
        "count": len(trades),
        "trades": trades,
    }


@router.get("/paper-trades/{trade_id}")
def get_paper_trade(
    trade_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    detail = svc.get_trade_detail(session, trade_id=trade_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="trade not found")
    detail["notice"] = PAPER_ONLY_NOTICE
    return detail


@router.get("/risk-summary")
def get_risk_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    summary = svc.get_risk_summary(session)
    summary["notice"] = PAPER_ONLY_NOTICE
    return summary


@router.get("/portfolio")
def get_options_portfolio(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Phase G1 — read-only options portfolio aggregate over OPEN positions
    (released_at IS NULL). Honest empty when none. No mutation/fill."""
    result = portfolio_service.get_portfolio(session, portfolio_id)
    result["notice"] = PAPER_ONLY_NOTICE
    return result


# ---------------------------------------------------------------------------
# Phase 11G — Strategy Observatory (read-only, observation only)
# ---------------------------------------------------------------------------


OBSERVATION_ONLY_NOTICE = (
    "Observation only — not investment advice or execution guidance"
)


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    """Frozen v1 rule registry — names, summaries, criteria + descriptions."""
    return {
        "notice": PAPER_ONLY_NOTICE,
        "observation_only_notice": OBSERVATION_ONLY_NOTICE,
        "strategies": obs_rules.list_rule_defs(),
    }


@router.get("/strategy-observations")
def list_strategy_observations(
    underlying: str | None = Query(default=None, max_length=12),
    qualified_only: bool = Query(default=False),
    rule_id: str | None = Query(default=None, max_length=64),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_observations.list_observations(
        session,
        underlying=underlying,
        qualified_only=qualified_only,
        rule_id=rule_id,
        lookback_days=lookback_days,
        limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/strategy-observations/{observation_id}")
def get_strategy_observation(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_observations.get_observation(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="observation not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/performance-summary")
def performance_summary(
    underlying: str | None = Query(default=None, max_length=12),
    strategy_name: str | None = Query(default=None, max_length=64),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_performance.get_performance_summary(
        session, underlying=underlying, strategy_name=strategy_name,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/diagnostics")
def diagnostics(
    lookback_days: int = Query(default=30, ge=1, le=180),
    underlying: str | None = Query(default=None, max_length=12),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = obs_diagnostics.get_diagnostics(
        session, lookback_days=lookback_days, underlying=underlying,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/scenario-replay")
def scenario_replay(
    symbol: str = Query(..., min_length=1, max_length=12),
    as_of: str = Query(..., min_length=10, max_length=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    import datetime as _dt
    try:
        as_of_d = _dt.date.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid as_of date")
    out = obs_replay.replay(session, symbol=symbol, as_of_date=as_of_d)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase 11H — Controlled Strategy Evaluation Layer (read-only, paper-only)
# ---------------------------------------------------------------------------

EVALUATION_DISCLAIMER = (
    "Evaluation scores are fixed rule-based paper analytics. "
    "They are not trade recommendations."
)


@router.get("/evaluation/summary")
def evaluation_summary(
    underlying: str | None = Query(default=None, max_length=12),
    strategy: str | None = Query(default=None, max_length=64),
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_summary(
        session, underlying=underlying, strategy=strategy,
        lookback_days=lookback_days,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/scores")
def evaluation_scores(
    strategy: str | None = Query(default=None, max_length=64),
    underlying: str | None = Query(default=None, max_length=12),
    min_score: int | None = Query(default=None, ge=0, le=100),
    qualified_only: bool = Query(default=False),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.list_scores(
        session,
        strategy=strategy,
        underlying=underlying,
        min_score=min_score,
        qualified_only=qualified_only,
        lookback_days=lookback_days,
        limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/scores/{observation_id}")
def evaluation_score_detail(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_score_detail(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="evaluation score not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/distribution")
def evaluation_distribution(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_distribution(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/evaluation/diagnostics")
def evaluation_diagnostics(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = eval_service.get_diagnostics(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase 11I — Decision Support Layer (read-only, paper-only)
# ---------------------------------------------------------------------------


@router.get("/decision-support/summary")
def decision_support_summary(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_summary(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/review-queue")
def decision_support_review_queue(
    strategy: str | None = Query(default=None, max_length=64),
    underlying: str | None = Query(default=None, max_length=12),
    min_score: int | None = Query(default=None, ge=0, le=100),
    qualified_only: bool = Query(default=False),
    exclude_severe_flags: bool = Query(default=False),
    bucket: str | None = Query(default=None, max_length=64),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_review_queue(
        session,
        strategy=strategy,
        underlying=underlying,
        min_score=min_score,
        qualified_only=qualified_only,
        exclude_severe_flags=exclude_severe_flags,
        bucket=bucket,
        lookback_days=lookback_days,
        limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/review-queue/{observation_id}")
def decision_support_review_detail(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_review_detail(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(
            status_code=404, detail="review queue entry not found",
        )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/buckets")
def decision_support_buckets(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_review_queue.get_buckets(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-support/diagnostics")
def decision_support_diagnostics(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ds_diagnostics.get_diagnostics(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase 11J — Assisted Decision Framing (read-only, paper-only)
# ---------------------------------------------------------------------------


@router.get("/decision-framing/summary")
def decision_framing_summary(
    lookback_days: int = Query(default=14, ge=1, le=120),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = df_service.get_summary(session, lookback_days=lookback_days)
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-framing/narratives")
def decision_framing_narratives(
    bucket: str | None = Query(default=None, max_length=64),
    strategy: str | None = Query(default=None, max_length=64),
    underlying: str | None = Query(default=None, max_length=12),
    lookback_days: int = Query(default=14, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = df_service.list_narratives(
        session,
        bucket=bucket, strategy=strategy, underlying=underlying,
        lookback_days=lookback_days, limit=limit,
    )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-framing/narratives/{observation_id}")
def decision_framing_narrative_detail(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = df_service.get_narrative_detail(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="narrative not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-framing/compare")
def decision_framing_compare(
    observation_id_a: str = Query(..., min_length=1, max_length=200),
    observation_id_b: str = Query(..., min_length=1, max_length=200),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = df_service.compare_two(
        session,
        observation_id_a=observation_id_a,
        observation_id_b=observation_id_b,
    )
    if out is None:
        raise HTTPException(
            status_code=404,
            detail="one or both observation ids not found",
        )
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-framing/checklist/{observation_id}")
def decision_framing_checklist(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = df_service.get_checklist(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="checklist not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/decision-framing/context/{observation_id}")
def decision_framing_context(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = df_service.get_context(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="context not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase 11K — Cognitive Guardrails Layer (read-only, paper-only)
# ---------------------------------------------------------------------------


@router.get("/interpretation-guardrails/score/{observation_id}")
def interpretation_guardrails_score(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ig_service.get_score_interpretation(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="observation not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/interpretation-guardrails/bucket/{observation_id}")
def interpretation_guardrails_bucket(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ig_service.get_bucket_interpretation(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="observation not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/interpretation-guardrails/ranking/{observation_id}")
def interpretation_guardrails_ranking(
    observation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    out = ig_service.get_ranking_interpretation(
        session, observation_id=observation_id,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="observation not found")
    out["notice"] = PAPER_ONLY_NOTICE
    return out


@router.get("/interpretation-guardrails/page-context")
def interpretation_guardrails_page_context() -> dict[str, Any]:
    """Static page-level guardrails. No DB read required.
    Returns frozen text + universal "does not mean" block."""
    out = ig_service.get_page_context()
    out["notice"] = PAPER_ONLY_NOTICE
    return out


# ---------------------------------------------------------------------------
# Phase Opt-C1 Step 11 — Lifecycle timeline read-only endpoint.
# Reads options_trade_lifecycle_event written by Opt-B2 sole-writer.
# ---------------------------------------------------------------------------


@router.get("/learning/summary")
def options_learning_summary(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Phase Opt-C1 Step 13 — gated learning insights.

    Hard thresholds (see docs/research/OPTIONS_OPT_C1_REFINEMENT.md §8):
      - ≥30 total CLOSED paper trades
      - ≥10 CLOSED per strategy in ≥3 distinct strategies
      - ≥30 distinct trading days of CLOSED coverage
      - ML_OPTIONS_LEARNING_ENABLED env flag (operator master switch)

    Below thresholds: returns gate progress only. Above: aggregates
    with Wilson 95% CI. Currently always below threshold (zero CLOSED
    trades exist; engine dormant).
    """
    from sqlalchemy import text

    from apps.api.src.config import settings

    THRESHOLD_TOTAL_CLOSED = 30
    THRESHOLD_PER_STRATEGY = 10
    THRESHOLD_DISTINCT_STRATEGIES = 3
    THRESHOLD_TRADING_DAYS = 30

    counts = session.execute(text(
        """
        SELECT
          (SELECT COUNT(*) FROM options_paper_trade
             WHERE status IN ('CLOSED','EXPIRED','ASSIGNED'))
            AS closed_total,
          (SELECT COUNT(DISTINCT DATE(closed_at))
             FROM options_paper_trade
             WHERE closed_at IS NOT NULL)
            AS distinct_days
        """
    )).mappings().first()

    closed_total = int(counts["closed_total"]) if counts else 0
    distinct_days = int(counts["distinct_days"]) if counts else 0

    # Per-strategy CLOSED counts
    per_strategy_rows = session.execute(text(
        """
        SELECT strategy_name, COUNT(*) AS n
        FROM options_paper_trade
        WHERE status IN ('CLOSED','EXPIRED','ASSIGNED')
        GROUP BY strategy_name
        ORDER BY n DESC
        """
    )).mappings().all()
    per_strategy = [
        {"strategy_name": str(r["strategy_name"]), "closed_count": int(r["n"])}
        for r in per_strategy_rows
    ]
    distinct_strategies_meeting_floor = sum(
        1 for r in per_strategy if r["closed_count"] >= THRESHOLD_PER_STRATEGY
    )
    top_strategy_count = per_strategy[0]["closed_count"] if per_strategy else 0

    flag_on = bool(getattr(settings, "ML_OPTIONS_LEARNING_ENABLED", False))
    all_data_gates_pass = (
        closed_total >= THRESHOLD_TOTAL_CLOSED
        and distinct_strategies_meeting_floor >= THRESHOLD_DISTINCT_STRATEGIES
        and distinct_days >= THRESHOLD_TRADING_DAYS
    )
    enabled = flag_on and all_data_gates_pass

    if enabled:
        # Phase Opt-C1 ships the gate logic only. Aggregate computation
        # (Wilson CI, calibration bins) lands in a separate operator-
        # approved phase once gates actually trip. Until then this
        # branch is unreachable in practice.
        # The shape is reserved here for forward-compat.
        return {
            "enabled": True,
            "ml_options_learning_enabled": flag_on,
            "thresholds_met": True,
            "win_rate_by_strategy": [],
            "calibration": [],
            "best_worst": [],
            "rejection_history": [],
            "notice": PAPER_ONLY_NOTICE,
            "computed_at_utc": (
                __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
            ),
        }

    return {
        "enabled": False,
        "ml_options_learning_enabled": flag_on,
        "thresholds_met": all_data_gates_pass,
        "gate": {
            "closed_trades": closed_total,
            "closed_trades_target": THRESHOLD_TOTAL_CLOSED,
            "distinct_strategies_meeting_floor":
                distinct_strategies_meeting_floor,
            "distinct_strategies_target": THRESHOLD_DISTINCT_STRATEGIES,
            "top_strategy_closed_count": top_strategy_count,
            "per_strategy_target": THRESHOLD_PER_STRATEGY,
            "trading_days": distinct_days,
            "trading_days_target": THRESHOLD_TRADING_DAYS,
        },
        "per_strategy_breakdown": per_strategy,
        "reason": (
            "Learning insights unlock when all data gates pass AND the "
            "ML_OPTIONS_LEARNING_ENABLED flag is True. Currently "
            f"{'data gates would pass' if all_data_gates_pass else 'data thresholds not met'}; "
            f"flag is {'on' if flag_on else 'off'}."
        ),
        "notice": PAPER_ONLY_NOTICE,
    }


@router.get("/trades/{trade_id}/lifecycle")
def options_trade_lifecycle(
    trade_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Read-only event log for one paper-trade. Powers the lifecycle
    timeline UI (Opt-C1 Step 11). Sole writer of the underlying table
    is apps/api/src/options/lifecycle.py (Opt-B2)."""
    from sqlalchemy import text

    trade_row = session.execute(text(
        """
        SELECT id, status, opened_at, closed_at, underlying,
               strategy_name, strategy_version,
               proposal_hash
        FROM options_paper_trade
        WHERE id = :tid
        """
    ), {"tid": trade_id}).mappings().first()
    if trade_row is None:
        return {
            "trade_id": trade_id,
            "found": False,
            "current_status": None,
            "events": [],
            "notice": PAPER_ONLY_NOTICE,
        }

    events = session.execute(text(
        """
        SELECT id, event_type, event_at_utc, triggered_by, payload_json
        FROM options_trade_lifecycle_event
        WHERE trade_id = :tid
        ORDER BY event_at_utc ASC, id ASC
        """
    ), {"tid": trade_id}).mappings().all()

    return {
        "trade_id": trade_id,
        "found": True,
        "current_status": str(trade_row["status"]),
        "underlying": str(trade_row["underlying"]),
        "strategy_name": str(trade_row["strategy_name"]),
        "strategy_version": str(trade_row["strategy_version"]),
        "opened_at": (
            trade_row["opened_at"].isoformat()
            if trade_row["opened_at"] else None
        ),
        "closed_at": (
            trade_row["closed_at"].isoformat()
            if trade_row["closed_at"] else None
        ),
        "proposal_hash": (
            str(trade_row["proposal_hash"])
            if trade_row["proposal_hash"] else None
        ),
        "events": [
            {
                "id": int(e["id"]),
                "event_type": str(e["event_type"]),
                "event_at_utc": (
                    e["event_at_utc"].isoformat()
                    if e["event_at_utc"] else None
                ),
                "triggered_by": str(e["triggered_by"]),
                "payload": e["payload_json"] or {},
            }
            for e in events
        ],
        "notice": PAPER_ONLY_NOTICE,
    }
