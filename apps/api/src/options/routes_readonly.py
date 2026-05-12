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
