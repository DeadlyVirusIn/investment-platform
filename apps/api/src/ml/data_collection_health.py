"""Phase 11V - data collection health diagnostic.

Read-only inspection of data freshness across the pipeline. NEVER
writes to DB. Reports on:
  - price_bar coverage: latest ts per active asset
  - context_daily coverage: latest as_of_date per gate name
  - recommendation throughput: counts per day in lookback window
  - candidate_idea throughput: counts per day in lookback window
  - job_run health: most recent run + status per registered job

Intent: surface stale or missing data that would silently block the
T+1 fill cycle. NEVER changes data, schedules, or job code.

Frozen constants:
  REPORT_VERSION = "data-health-v1.0.0"
  STALE_PRICE_DAYS = 5    # weekday-only window
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    JobRun,
    JobSchedule,
    PriceBar,
    Recommendation,
)


REPORT_VERSION = "data-health-v1.0.0"
STALE_PRICE_DAYS = 5
PRODUCTION_GATE_NAMES: tuple[str, ...] = (
    "rates_calm", "vrp_supportive",
    "credit_stable", "liquidity_expanding",
)


def price_bar_health(
    session: Session, *, as_of: dt.datetime,
) -> dict[str, Any]:
    """For every active asset, return the latest price_bar.ts and
    flag assets that are stale (>= STALE_PRICE_DAYS calendar days
    behind as_of). Read-only."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be tz-aware")

    rows = session.execute(
        select(
            Asset.id, Asset.symbol,
            func.max(PriceBar.ts).label("latest_ts"),
        )
        .join(PriceBar, PriceBar.asset_id == Asset.id, isouter=True)
        .where(Asset.is_active.is_(True))
        .group_by(Asset.id, Asset.symbol)
    ).all()

    cutoff = as_of - dt.timedelta(days=STALE_PRICE_DAYS)
    fresh: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for asset_id, symbol, latest_ts in rows:
        entry = {
            "asset_id": asset_id,
            "symbol": symbol,
            "latest_ts": (
                latest_ts.isoformat() if latest_ts else None
            ),
        }
        if latest_ts is None:
            missing.append(entry)
        elif latest_ts < cutoff:
            stale.append({
                **entry,
                "lag_days": (as_of - latest_ts).days,
            })
        else:
            fresh.append(entry)
    return {
        "as_of": as_of.isoformat(),
        "stale_threshold_days": STALE_PRICE_DAYS,
        "fresh_count": len(fresh),
        "stale_count": len(stale),
        "missing_count": len(missing),
        "stale_assets": stale,
        "missing_assets": missing,
    }


def context_daily_health(
    session: Session, *, as_of: dt.date,
) -> dict[str, Any]:
    """For each production gate name, return latest as_of_date row
    in context_daily and flag any gate with no row at or before
    as_of. Read-only."""
    out: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "gate_names": list(PRODUCTION_GATE_NAMES),
        "latest_per_gate": {},
        "missing_gates": [],
    }
    for name in PRODUCTION_GATE_NAMES:
        row = session.execute(text(
            """
            SELECT as_of_date, value_bool, logic_version
            FROM context_daily
            WHERE context_name = :name
              AND as_of_date <= :as_of
            ORDER BY as_of_date DESC
            LIMIT 1
            """
        ), {"name": name, "as_of": as_of}).first()
        if row is None:
            out["missing_gates"].append(name)
            out["latest_per_gate"][name] = None
        else:
            as_of_date, value_bool, logic_version = row
            out["latest_per_gate"][name] = {
                "as_of_date": as_of_date.isoformat(),
                "value_bool": bool(value_bool),
                "logic_version": logic_version,
                "lag_days": (as_of - as_of_date).days,
            }
    out["all_present"] = len(out["missing_gates"]) == 0
    return out


def recommendation_throughput(
    session: Session,
    *,
    as_of: dt.datetime,
    lookback_days: int,
) -> dict[str, Any]:
    """Count recommendations by action across the lookback window.
    Read-only."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be tz-aware")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be > 0")

    start = as_of - dt.timedelta(days=lookback_days)
    rows = session.execute(
        select(Recommendation.action, func.count(Recommendation.id))
        .where(
            Recommendation.generated_at >= start,
            Recommendation.generated_at <= as_of,
        )
        .group_by(Recommendation.action)
    ).all()
    counts = {action: int(n) for action, n in rows}
    total = sum(counts.values())
    return {
        "lookback_days": lookback_days,
        "start": start.isoformat(),
        "end": as_of.isoformat(),
        "total": total,
        "by_action": counts,
    }


def candidate_idea_throughput(
    session: Session,
    *,
    as_of: dt.datetime,
    lookback_days: int,
) -> dict[str, Any]:
    """Count candidate_idea rows across the lookback window.
    Read-only."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be tz-aware")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be > 0")

    start_d = (as_of - dt.timedelta(days=lookback_days)).date()
    end_d = as_of.date()
    rows = session.execute(
        select(CandidateIdea.as_of_date, func.count(CandidateIdea.id))
        .where(
            CandidateIdea.as_of_date >= start_d,
            CandidateIdea.as_of_date <= end_d,
        )
        .group_by(CandidateIdea.as_of_date)
        .order_by(CandidateIdea.as_of_date)
    ).all()
    counts = {d.isoformat(): int(n) for d, n in rows}
    total = sum(counts.values())
    return {
        "lookback_days": lookback_days,
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "total": total,
        "days_with_data": len(counts),
        "by_date": counts,
    }


def job_run_health(
    session: Session, *, as_of: dt.datetime,
) -> dict[str, Any]:
    """Latest job_run per registered job. Returns status, finished_at,
    age in hours. Read-only."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be tz-aware")

    schedules = session.scalars(select(JobSchedule)).all()
    out: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "by_job": {},
    }
    for sched in schedules:
        latest = session.execute(
            select(
                JobRun.id, JobRun.status, JobRun.finished_at,
                JobRun.started_at,
            )
            .where(JobRun.job_schedule_id == sched.id)
            .order_by(JobRun.started_at.desc())
            .limit(1)
        ).first()
        if latest is None:
            out["by_job"][sched.name] = {
                "status": None,
                "finished_at": None,
                "age_hours": None,
            }
            continue
        _id, status, finished_at, started_at = latest
        anchor = finished_at or started_at
        age_hours: float | None = None
        if anchor is not None:
            age_hours = round(
                (as_of - anchor).total_seconds() / 3600.0, 2,
            )
        out["by_job"][sched.name] = {
            "status": status,
            "finished_at": (
                finished_at.isoformat() if finished_at else None
            ),
            "age_hours": age_hours,
        }
    return out


def health_summary(
    session: Session,
    *,
    as_of: dt.datetime,
    lookback_days: int,
) -> dict[str, Any]:
    """Top-level aggregator combining all sub-checks. Pure read."""
    return {
        "report_version": REPORT_VERSION,
        "as_of": as_of.isoformat(),
        "lookback_days": lookback_days,
        "price_bar": price_bar_health(session, as_of=as_of),
        "context_daily": context_daily_health(
            session, as_of=as_of.date(),
        ),
        "recommendations": recommendation_throughput(
            session, as_of=as_of, lookback_days=lookback_days,
        ),
        "candidate_ideas": candidate_idea_throughput(
            session, as_of=as_of, lookback_days=lookback_days,
        ),
        "job_runs": job_run_health(session, as_of=as_of),
    }
