"""Trust Center v1 — owner-only, read-only aggregation (Honest Numbers).

Per docs/architecture/TRUST_CENTER_V1_SPEC.md: every section is fed by an
EXISTING read-only source and carries one of six honesty labels — sections
without production evidence say so instead of inventing a number. The
dev-database calibration study (2026-07-09) is referenced with its
`preliminary` label and is NEVER presented as a production statistic.

Zero migrations, zero writes. Mounted under the owner guard; non-owners
get the admin 404 posture. Not linked from any user-facing navigation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.build_provenance import get_build_provenance
from apps.api.src.config import settings
from apps.api.src.db import get_session

router = APIRouter(
    prefix="/admin/trust-center",
    tags=["admin"],
    dependencies=[Depends(require_owner)],
)

LABELS = ("proven", "preliminary", "insufficient_data",
          "not_yet_evaluated", "degraded", "unavailable")


def _section(title: str, label: str, body: str,
             data: dict[str, Any] | None = None) -> dict[str, Any]:
    assert label in LABELS
    return {"title": title, "label": label, "body": body, "data": data or {}}


@router.get("")
def trust_center(db: Session = Depends(get_session)) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    sections: list[dict[str, Any]] = []

    # -- system status: scheduler health from job_schedule (P0-5B posture) --
    stuck = db.execute(text(
        "SELECT count(*) FROM job_schedule WHERE enabled AND next_run_at IS NULL"
    )).scalar()
    overdue = db.execute(text(
        "SELECT count(*) FROM job_schedule WHERE enabled "
        "AND next_run_at < now() - interval '26 hours'"
    )).scalar()
    sections.append(_section(
        "System status",
        "degraded" if (stuck or overdue) else "preliminary",
        "Scheduler uses atomic exactly-once claims with NULL self-heal. "
        "Beta software.",
        {"stuck_null_schedules": stuck, "overdue_jobs": overdue},
    ))

    # -- data freshness: newest daily bar age ------------------------------
    newest_bar = db.execute(text(
        "SELECT max(ts) FROM price_bar WHERE timeframe = '1d'"
    )).scalar()
    age_h = ((now - newest_bar).total_seconds() / 3600) if newest_bar else None
    sections.append(_section(
        "Data freshness",
        "unavailable" if age_h is None
        else ("degraded" if age_h > 96 else "preliminary"),
        "Age of the newest ingested daily price bar.",
        {"newest_bar_ts": str(newest_bar), "age_hours": round(age_h, 1) if age_h else None},
    ))

    # -- model version: build provenance (always real) ---------------------
    prov = get_build_provenance()
    sections.append(_section(
        "Model version",
        "proven" if prov.get("git_sha") not in (None, "unknown") else "degraded",
        "Exact git commit baked into the running image; recommendations "
        "additionally carry engine-version and snapshot hashes.",
        prov,
    ))

    # -- feature schema version --------------------------------------------
    sections.append(_section(
        "Feature schema version",
        "not_yet_evaluated",
        "Ordered feature-schema hashing exists in the attribution prototype; "
        "not yet stamped by any production model (no persisted artifact).",
    ))

    # -- sample sizes + resolved/unresolved (THIS database, labeled) -------
    recs = db.execute(text(
        "SELECT count(*) FROM recommendation "
        "WHERE model_version NOT LIKE '%+replay:%'"
    )).scalar()
    resolved = db.execute(text(
        "SELECT count(*) FROM recommendation_outcome WHERE barrier_label IS NOT NULL"
    )).scalar()
    unresolved = db.execute(text(
        "SELECT count(*) FROM recommendation_outcome WHERE barrier_label IS NULL"
    )).scalar()
    sections.append(_section(
        "Recommendation sample size",
        "preliminary" if resolved and resolved >= 10 else "insufficient_data",
        "Counts from THIS environment's database. Outcome accuracy publishes "
        "only at >= 10 resolved outcomes.",
        {"live_recommendations": recs, "resolved_outcomes": resolved,
         "unresolved_outcomes": unresolved},
    ))

    # -- confidence calibration: study reference, never a prod stat --------
    sections.append(_section(
        "Confidence calibration",
        "preliminary",
        "First offline study (2026-07-09, research data — NOT a production "
        "statistic): High-band Buys resolved below the level the label "
        "implies and Medium outperformed High; discrimination weak "
        "(AUC 0.52). Owner decision recorded: collapse High/Medium to "
        "'Meets the buy bar' (copy change not yet applied). Details: "
        "docs/research/CONFIDENCE_CALIBRATION_REPORT.md.",
    ))

    # -- paper record: canonical live snapshot ------------------------------
    snap = db.execute(text(
        "SELECT total_equity, snapshot_date FROM paper_equity_snapshot s "
        "JOIN paper_portfolio p ON p.id = s.portfolio_id "
        "WHERE s.source = 'live' AND p.name NOT LIKE 'user:%' AND p.is_active "
        "ORDER BY s.snapshot_date DESC, s.recorded_at DESC LIMIT 1"
    )).first()
    sections.append(_section(
        "Paper record",
        "preliminary" if snap else "unavailable",
        "Latest live engine-book equity snapshot. Every idea is tracked to "
        "resolution; wins and losses both count.",
        {"latest_equity": float(snap[0]) if snap else None,
         "as_of": str(snap[1]) if snap else None},
    ))

    # -- benchmark comparison ------------------------------------------------
    sections.append(_section(
        "Benchmark comparison",
        "not_yet_evaluated",
        "Buy-and-hold and momentum benchmarks land with the Experiment Lab "
        "(see ELITE_ARTHOS_ROADMAP.md).",
    ))

    # -- known limitations ----------------------------------------------------
    sections.append(_section(
        "Known limitations",
        "proven",
        "Paper-only, no live trading. Confidence granularity under review "
        "(weak discrimination in first study). Nightly paper fills carry no "
        "commission/slippage yet. Advisory output is never a guarantee.",
    ))

    # -- incidents (honest, curated) -----------------------------------------
    sections.append(_section(
        "Recent incidents",
        "proven",
        "2026-07-08: nightly engine jobs traded user practice books (all "
        "drained to $0). Root-caused and fixed same day; 52 books restored "
        "by ledger reconstruction; guards and pinned tests added.",
    ))

    # -- change log ------------------------------------------------------------
    sections.append(_section(
        "Model / research change log",
        "preliminary",
        "2026-07-09: scheduler NULL self-heal deployed; attribution and "
        "calibration studies completed (research). Durable registry-backed "
        "log arrives with research_run (migration 109, pending approval).",
    ))

    # -- promoted experiments ----------------------------------------------------
    sections.append(_section(
        "Promoted experiment history",
        "not_yet_evaluated",
        "No experiment has ever been promoted to production. Promotion "
        "gates are specified in RESEARCH_RUN_REGISTRY_SPEC.md.",
    ))

    # -- feature flags (safe, curated subset — never raw env) -----------------
    sections.append(_section(
        "Current feature flags",
        "proven",
        "Safety-relevant flags as the API process sees them.",
        {
            "options_enabled": bool(getattr(settings, "OPTIONS_ENABLED", False)),
            "ml_can_affect_trades": bool(getattr(settings, "ML_CAN_AFFECT_TRADES", False)),
            "ingest_contracts_enabled": bool(settings.INGEST_CONTRACTS_ENABLED),
            "demo_device_mode": bool(settings.DEMO_DEVICE_MODE),
        },
    ))

    return {
        "generated_at": now.isoformat(),
        "audience": "owner",
        "labels": list(LABELS),
        "sections": sections,
    }
