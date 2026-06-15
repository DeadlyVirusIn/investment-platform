"""Phase Opt-B3a Phase 6b-1 — observational analytics SQL.

Pure SQL helpers backing /api/options/analytics/* endpoints. Every
function below is SELECT-only — no INSERT, UPDATE, DELETE, MERGE,
TRUNCATE. Verified by grep at module bottom + test
`test_analytics_queries_are_select_only`.

Read-only by construction: the only DB API touched is
`session.execute(text(...))` and `session.execute(text(...)).mappings()`.
No ORM `.add` / `.merge` / `.commit` / `.flush` calls.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_utc() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _coerce_int(v: Any, default: int) -> int:
    try:
        x = int(v)
        return x if x > 0 else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 1. Integrity 4-flag (extended to 5 per operator amendment D)
# ---------------------------------------------------------------------------

def integrity_status(
    session: Session, *,
    run_date: dt.date,
    production_providers: Iterable[str],
    max_age_hours: int,
    run_universe: Iterable[str],
    options_shadow_eval_enabled: bool,
) -> dict[str, Any]:
    """Compact dataset-integrity dashboard backing.

    Five booleans + their inputs:
      * coherent_batch_present
      * provider_homogeneous
      * universe_closure_pass
      * freshness_bound_pass
      * shadow_persistence_active   (per operator amendment D)
    """
    prov_list = list(production_providers)
    uni_list = list(run_universe)

    # Pick the active batch (mirrors shadow_evaluator._select_run_batch
    # without importing it — analytics layer must be independent).
    batch = session.execute(text(
        """
        SELECT snapshot_at_utc, provider, provider_version,
               EXTRACT(EPOCH FROM (NOW() - snapshot_at_utc))::int AS age_seconds
          FROM options_chain_snapshot
         WHERE provider = ANY(:provs)
           AND snapshot_at_utc::date <= :d
           AND (NOW() - snapshot_at_utc) <= make_interval(hours => :hrs)
         ORDER BY snapshot_at_utc DESC
         LIMIT 1
        """
    ), {"provs": prov_list, "d": run_date,
        "hrs": int(max_age_hours)}).mappings().first()

    today_underlyings_row = session.execute(text(
        """
        SELECT COUNT(DISTINCT underlying_symbol) AS n_under
          FROM options_shadow_decision_log
         WHERE run_date = :d
        """
    ), {"d": run_date}).mappings().first()
    n_underlyings = int(today_underlyings_row["n_under"]) if today_underlyings_row else 0

    out_of_uni_row = session.execute(text(
        """
        SELECT COUNT(*) AS n
          FROM options_shadow_decision_log
         WHERE run_date = :d
           AND underlying_symbol <> ALL(:uni)
        """
    ), {"d": run_date, "uni": uni_list}).mappings().first()
    out_of_universe_count = int(out_of_uni_row["n"]) if out_of_uni_row else 0

    prov_homo_row = session.execute(text(
        """
        SELECT COUNT(DISTINCT cs.provider_version) AS n_versions
          FROM options_shadow_decision_log sd
          JOIN options_chain_snapshot cs USING (option_symbol)
         WHERE sd.run_date = :d
        """
    ), {"d": run_date}).mappings().first()
    n_provider_versions = int(prov_homo_row["n_versions"]) if prov_homo_row else 0

    coherent = batch is not None
    freshness_pass = bool(batch and batch["age_seconds"] <= max_age_hours * 3600)
    universe_pass = (out_of_universe_count == 0)
    provider_homo = (n_provider_versions <= 1)

    return {
        "run_date":                 run_date.isoformat(),
        "coherent_batch_present":   coherent,
        "provider_homogeneous":     provider_homo,
        "universe_closure_pass":    universe_pass,
        "freshness_bound_pass":     freshness_pass,
        "shadow_persistence_active": bool(options_shadow_eval_enabled),
        "active_batch": (
            None if not batch else {
                "snapshot_at_utc":  batch["snapshot_at_utc"].isoformat(),
                "provider":         batch["provider"],
                "provider_version": batch["provider_version"],
                "age_seconds":      int(batch["age_seconds"]),
                "age_hours":        round(batch["age_seconds"] / 3600.0, 2),
            }
        ),
        "today_underlying_count":      n_underlyings,
        "today_out_of_universe_count": out_of_universe_count,
        "today_provider_version_count": n_provider_versions,
        "thresholds": {
            "max_run_chain_age_hours":     int(max_age_hours),
            "production_providers":        prov_list,
            "run_universe":                uni_list,
        },
    }


# ---------------------------------------------------------------------------
# 2. Daily counts (time series)
# ---------------------------------------------------------------------------

def daily_counts(
    session: Session, *, days: int = 14,
) -> list[dict[str, Any]]:
    """Time series of total/would_trade/blocked decisions per run_date."""
    n = _coerce_int(days, 14)
    rows = session.execute(text(
        """
        SELECT run_date,
               COUNT(*)                                  AS total,
               COUNT(*) FILTER (WHERE would_trade)       AS would_trade,
               COUNT(*) FILTER (WHERE NOT would_trade)   AS blocked,
               COUNT(DISTINCT underlying_symbol)         AS underlyings,
               COUNT(DISTINCT strategy_name)             AS strategies
          FROM options_shadow_decision_log
         WHERE run_date >= CURRENT_DATE - (:days || ' days')::interval
         GROUP BY run_date ORDER BY run_date DESC
        """
    ), {"days": n}).mappings().all()
    return [dict(r) | {"run_date": r["run_date"].isoformat()} for r in rows]


# ---------------------------------------------------------------------------
# 3. By-strategy breakdown (single date)
# ---------------------------------------------------------------------------

def by_strategy(
    session: Session, *, run_date: dt.date,
) -> list[dict[str, Any]]:
    rows = session.execute(text(
        """
        SELECT strategy_name,
               COUNT(*)                                AS total,
               COUNT(*) FILTER (WHERE would_trade)     AS would_trade,
               COUNT(*) FILTER (WHERE NOT would_trade) AS blocked,
               MODE() WITHIN GROUP (ORDER BY reason)
                 FILTER (WHERE NOT would_trade)        AS top_rejection_reason
          FROM options_shadow_decision_log
         WHERE run_date = :d
         GROUP BY strategy_name ORDER BY total DESC
        """
    ), {"d": run_date}).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 4. By-rejection histogram + day-over-day deltas
# ---------------------------------------------------------------------------

def by_rejection(
    session: Session, *, run_date: dt.date, days: int = 7,
) -> dict[str, Any]:
    n = _coerce_int(days, 7)
    today_rows = session.execute(text(
        """
        SELECT reason, COUNT(*) AS n
          FROM options_shadow_decision_log
         WHERE run_date = :d AND NOT would_trade
         GROUP BY reason ORDER BY n DESC
        """
    ), {"d": run_date}).mappings().all()
    today_map = {r["reason"]: int(r["n"]) for r in today_rows}

    # 7-day window AVG (excluding today, comparing yesterday backward)
    avg_rows = session.execute(text(
        """
        WITH per_day AS (
          SELECT run_date, reason, COUNT(*) AS n
            FROM options_shadow_decision_log
           WHERE NOT would_trade
             AND run_date >= :d - (:days || ' days')::interval
             AND run_date < :d
           GROUP BY run_date, reason
        )
        SELECT reason, ROUND(AVG(n), 1)::float AS avg_n
          FROM per_day GROUP BY reason
        """
    ), {"d": run_date, "days": n}).mappings().all()
    avg_map = {r["reason"]: float(r["avg_n"]) for r in avg_rows}

    out = []
    for reason, today_n in today_map.items():
        a = avg_map.get(reason, 0.0)
        delta_pct = ((today_n - a) / a * 100.0) if a > 0 else None
        out.append({
            "reason": reason,
            "today": today_n,
            "avg_prior_days": a,
            "delta_pct_vs_avg": (round(delta_pct, 1)
                                 if delta_pct is not None else None),
        })
    return {
        "run_date":   run_date.isoformat(),
        "window_days": n,
        "rejections": out,
    }


# ---------------------------------------------------------------------------
# 5. Provider mix (provider stability over time)
# ---------------------------------------------------------------------------

def provider_mix(
    session: Session, *, days: int = 14,
) -> list[dict[str, Any]]:
    n = _coerce_int(days, 14)
    rows = session.execute(text(
        """
        SELECT (cs.snapshot_at_utc::date) AS d,
               cs.provider, cs.provider_version,
               COUNT(*)                          AS rows_used,
               COUNT(DISTINCT sd.underlying_symbol) AS underlyings
          FROM options_shadow_decision_log sd
          JOIN options_chain_snapshot cs USING (option_symbol)
         WHERE sd.run_date >= CURRENT_DATE - (:days || ' days')::interval
         GROUP BY 1, 2, 3 ORDER BY 1 DESC, rows_used DESC
        """
    ), {"days": n}).mappings().all()
    return [dict(r) | {"d": r["d"].isoformat()} for r in rows]


# ---------------------------------------------------------------------------
# 6. Universe coverage (single date)
# ---------------------------------------------------------------------------

def universe_coverage(
    session: Session, *, run_date: dt.date,
    run_universe: Iterable[str],
) -> dict[str, Any]:
    expected = list(run_universe)
    rows = session.execute(text(
        """
        SELECT underlying_symbol, COUNT(*) AS decisions
          FROM options_shadow_decision_log
         WHERE run_date = :d
         GROUP BY underlying_symbol ORDER BY underlying_symbol
        """
    ), {"d": run_date}).mappings().all()
    observed = {r["underlying_symbol"]: int(r["decisions"]) for r in rows}
    expected_set = set(expected)
    observed_set = set(observed.keys())
    return {
        "run_date":   run_date.isoformat(),
        "expected":   sorted(expected_set),
        "observed":   sorted(observed_set),
        "unexpected": sorted(observed_set - expected_set),
        "missing":    sorted(expected_set - observed_set),
        "decisions_per_underlying": observed,
        "closure_pass": (not (observed_set - expected_set))
                        and (not (expected_set - observed_set)),
    }


# ---------------------------------------------------------------------------
# 7. Freshness (live age + percentiles)
# ---------------------------------------------------------------------------

def freshness(session: Session, *, max_age_hours: int) -> dict[str, Any]:
    latest = session.execute(text(
        """
        SELECT MAX(snapshot_at_utc) AS latest_ts,
               EXTRACT(EPOCH FROM (NOW() - MAX(snapshot_at_utc)))::int AS age_seconds
          FROM options_chain_snapshot
        """
    )).mappings().first()
    if not latest or latest["latest_ts"] is None:
        return {
            "latest_snapshot_at_utc": None,
            "age_seconds":  None,
            "age_hours":    None,
            "within_bound": None,
            "max_age_hours": int(max_age_hours),
            "quote_age_seconds_pXX": None,
        }

    pcts = session.execute(text(
        """
        SELECT
          percentile_disc(0.50) WITHIN GROUP (ORDER BY quote_age_seconds) AS p50,
          percentile_disc(0.90) WITHIN GROUP (ORDER BY quote_age_seconds) AS p90,
          percentile_disc(0.95) WITHIN GROUP (ORDER BY quote_age_seconds) AS p95
          FROM options_chain_snapshot
         WHERE snapshot_at_utc = :ts
        """
    ), {"ts": latest["latest_ts"]}).mappings().first()

    return {
        "latest_snapshot_at_utc": latest["latest_ts"].isoformat(),
        "age_seconds":  int(latest["age_seconds"]),
        "age_hours":    round(latest["age_seconds"] / 3600.0, 2),
        "within_bound": latest["age_seconds"] <= max_age_hours * 3600,
        "max_age_hours": int(max_age_hours),
        "quote_age_seconds_pXX": (
            None if not pcts else {
                "p50": int(pcts["p50"]) if pcts["p50"] is not None else None,
                "p90": int(pcts["p90"]) if pcts["p90"] is not None else None,
                "p95": int(pcts["p95"]) if pcts["p95"] is not None else None,
            }
        ),
    }


# ---------------------------------------------------------------------------
# 8. Learning readiness (extended gates)
# ---------------------------------------------------------------------------

def learning_readiness(
    session: Session, *,
    run_universe: Iterable[str],
) -> dict[str, Any]:
    """Phase 6b extended replacement for the existing /learning/summary
    gate. Adds 4 NEW gates layered on top of the original 4:
      * coherent-batch days
      * feature_daily coverage
      * provider stability window
      * universe consistency
    """
    THRESHOLD_TOTAL_CLOSED          = 30
    THRESHOLD_PER_STRATEGY          = 10
    THRESHOLD_DISTINCT_STRATEGIES   = 3
    THRESHOLD_TRADING_DAYS          = 30
    THRESHOLD_COHERENT_BATCH_DAYS   = 30
    THRESHOLD_FEATURE_COVERAGE_DAYS = 21
    THRESHOLD_PROVIDER_STABLE_DAYS  = 30

    closed_row = session.execute(text(
        """
        SELECT COUNT(*) AS n,
               COUNT(DISTINCT DATE(closed_at)) AS d
          FROM options_paper_trade
         WHERE status IN ('CLOSED','EXPIRED','ASSIGNED')
        """
    )).mappings().first()
    closed_total = int(closed_row["n"]) if closed_row else 0
    distinct_days = int(closed_row["d"]) if closed_row else 0

    per_strat = session.execute(text(
        """
        SELECT strategy_name, COUNT(*) AS n
          FROM options_paper_trade
         WHERE status IN ('CLOSED','EXPIRED','ASSIGNED')
         GROUP BY strategy_name ORDER BY n DESC
        """
    )).mappings().all()
    distinct_strats_meeting = sum(
        1 for r in per_strat if int(r["n"]) >= THRESHOLD_PER_STRATEGY)
    top_strat_count = int(per_strat[0]["n"]) if per_strat else 0

    coherent_batch_days = int(session.execute(text(
        """
        SELECT COUNT(DISTINCT run_date) AS d
          FROM options_shadow_decision_log
         WHERE run_date >= CURRENT_DATE - INTERVAL '60 days'
        """
    )).scalar() or 0)

    feature_days_row = session.execute(text(
        """
        SELECT COUNT(DISTINCT as_of_date) AS d
          FROM options_feature_daily
         WHERE as_of_date >= CURRENT_DATE - INTERVAL '60 days'
        """
    )).mappings().first()
    feature_days = int(feature_days_row["d"]) if feature_days_row else 0

    prov_window = session.execute(text(
        """
        SELECT COUNT(DISTINCT provider_version) AS n_versions,
               COUNT(DISTINCT (snapshot_at_utc::date)) AS n_days
          FROM options_chain_snapshot
         WHERE snapshot_at_utc >= NOW() - INTERVAL '30 days'
        """
    )).mappings().first()
    provider_versions_30d = int(prov_window["n_versions"]) if prov_window else 0
    provider_stable_days  = int(prov_window["n_days"])     if prov_window else 0

    uni_list = list(run_universe)
    uni_drift = int(session.execute(text(
        """
        SELECT COUNT(*) AS n
          FROM options_shadow_decision_log
         WHERE run_date >= CURRENT_DATE - INTERVAL '30 days'
           AND underlying_symbol <> ALL(:uni)
        """
    ), {"uni": uni_list}).scalar() or 0)

    # Composite readiness booleans
    closed_ok      = closed_total >= THRESHOLD_TOTAL_CLOSED
    per_strat_ok   = distinct_strats_meeting >= THRESHOLD_DISTINCT_STRATEGIES
    days_ok        = distinct_days >= THRESHOLD_TRADING_DAYS
    coherent_ok    = coherent_batch_days >= THRESHOLD_COHERENT_BATCH_DAYS
    feature_ok     = feature_days >= THRESHOLD_FEATURE_COVERAGE_DAYS
    provider_ok    = (provider_versions_30d <= 1) and (
                     provider_stable_days >= THRESHOLD_PROVIDER_STABLE_DAYS)
    universe_ok    = uni_drift == 0

    all_pass = (closed_ok and per_strat_ok and days_ok
                and coherent_ok and feature_ok and provider_ok and universe_ok)

    return {
        "all_gates_pass": all_pass,
        "gates": {
            "closed_trades": {
                "value": closed_total,
                "target": THRESHOLD_TOTAL_CLOSED, "pass": closed_ok,
            },
            "distinct_strategies_meeting_floor": {
                "value": distinct_strats_meeting,
                "target": THRESHOLD_DISTINCT_STRATEGIES,
                "pass": per_strat_ok,
                "per_strategy_target": THRESHOLD_PER_STRATEGY,
                "top_strategy_closed_count": top_strat_count,
            },
            "trading_days": {
                "value": distinct_days,
                "target": THRESHOLD_TRADING_DAYS, "pass": days_ok,
            },
            "coherent_batch_days": {
                "value": coherent_batch_days,
                "target": THRESHOLD_COHERENT_BATCH_DAYS,
                "pass": coherent_ok,
            },
            "feature_daily_coverage_days": {
                "value": feature_days,
                "target": THRESHOLD_FEATURE_COVERAGE_DAYS,
                "pass": feature_ok,
            },
            "provider_stability_window": {
                "provider_versions_in_30d": provider_versions_30d,
                "days_observed": provider_stable_days,
                "target_days": THRESHOLD_PROVIDER_STABLE_DAYS,
                "pass": provider_ok,
            },
            "universe_consistency": {
                "out_of_universe_rows_30d": uni_drift,
                "pass": universe_ok,
            },
        },
        "notice": (
            "Learning readiness is ADVISORY. All gates must pass AND "
            "ML_OPTIONS_LEARNING_ENABLED must be True for /learning/summary "
            "to enter the active state. Training is a SEPARATE explicit "
            "operator step."
        ),
    }


def scheduler_rows(session: Session) -> list[dict[str, Any]]:
    """Phase 6b-3-g — Ops · scheduler row read (SELECT-only).

    Returns options scheduler rows in name order, with cron + enabled
    + next/last fire timestamps. Pure SELECT.
    """
    rows = session.execute(text(
        """
        SELECT name, cron_expr, enabled, next_run_at, last_run_at,
               created_at
          FROM job_schedule
         WHERE name LIKE '%option%'
         ORDER BY name
        """
    )).mappings().all()
    return [
        {
            "name":         r["name"],
            "cron_expr":    r["cron_expr"],
            "enabled":      bool(r["enabled"]),
            "next_run_at":  r["next_run_at"].isoformat() if r["next_run_at"] else None,
            "last_run_at":  r["last_run_at"].isoformat() if r["last_run_at"] else None,
            "created_at":   r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


def job_runs(session: Session, *, limit: int = 10) -> list[dict[str, Any]]:
    """Phase 6b-3-g — Ops · recent job_run rows (SELECT-only).

    Returns recent runs across the options scheduler entries in
    started_at DESC order, capped at `limit`.
    """
    n = _coerce_int(limit, 10)
    rows = session.execute(text(
        """
        SELECT jr.id, js.name, jr.status, jr.started_at,
               jr.finished_at, jr.duration_seconds, jr.error_message
          FROM job_run jr
          JOIN job_schedule js ON jr.job_schedule_id = js.id
         WHERE js.name LIKE '%option%'
         ORDER BY jr.started_at DESC
         LIMIT :limit
        """
    ), {"limit": n}).mappings().all()
    return [
        {
            "id":               r["id"],
            "name":             r["name"],
            "status":           r["status"],
            "started_at":       r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at":      r["finished_at"].isoformat() if r["finished_at"] else None,
            "duration_seconds": (float(r["duration_seconds"])
                                 if r["duration_seconds"] is not None
                                 else None),
            "error_message":    r["error_message"],
        }
        for r in rows
    ]


def candidate_attribution(
    session: Session, *, limit: int = 200,
) -> list[dict[str, Any]]:
    """MP1A — proves the first closed outcome-feedback join (SELECT-only).

    Joins each executed options paper trade back to the strategy candidate
    that produced it, exposing the candidate's legacy `confidence` and its
    shadow `confidence_v2` (from diagnostics) alongside the trade's realized
    P&L and close time. Only rows with a stamped strategy_candidate_id appear
    (NULL/pre-MP1A trades are unattributable and excluded).
    """
    rows = session.execute(text(
        """
        SELECT t.id                                       AS trade_id,
               t.strategy_candidate_id                    AS candidate_id,
               c.confidence                               AS candidate_confidence,
               (c.diagnostics ->> 'confidence_v2')::numeric AS confidence_v2,
               t.status                                   AS status,
               t.realized_pnl_dollars                     AS realized_pnl_dollars,
               t.opened_at                                AS opened_at,
               t.closed_at                                AS closed_at
          FROM options_paper_trade t
          JOIN options_strategy_candidate c
            ON c.id = t.strategy_candidate_id
         WHERE t.strategy_candidate_id IS NOT NULL
         ORDER BY t.closed_at DESC NULLS LAST, t.id DESC
         LIMIT :limit
        """
    ), {"limit": _coerce_int(limit, 200)}).mappings().all()
    return [
        {
            "trade_id":             r["trade_id"],
            "candidate_id":         r["candidate_id"],
            "candidate_confidence": (float(r["candidate_confidence"])
                                     if r["candidate_confidence"] is not None
                                     else None),
            "confidence_v2":        (float(r["confidence_v2"])
                                     if r["confidence_v2"] is not None
                                     else None),
            "status":               r["status"],
            "realized_pnl_dollars": (float(r["realized_pnl_dollars"])
                                     if r["realized_pnl_dollars"] is not None
                                     else None),
            "opened_at":            r["opened_at"].isoformat() if r["opened_at"] else None,
            "closed_at":            r["closed_at"].isoformat() if r["closed_at"] else None,
        }
        for r in rows
    ]


__all__ = [
    "integrity_status",
    "daily_counts",
    "by_strategy",
    "by_rejection",
    "provider_mix",
    "universe_coverage",
    "freshness",
    "learning_readiness",
    "scheduler_rows",
    "job_runs",
    "candidate_attribution",
]
