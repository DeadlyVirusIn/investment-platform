"""Strategy diagnostics aggregator (Phase 11G).

Pure read over options_chain_snapshot + options_feature_daily +
options_expiration_event + options_assignment_event. Produces counts
of data-quality failures over a lookback window so operators can see
WHY an observation might have been made or missed.

NEVER writes. NEVER produces recommendations.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


DEFAULT_LOOKBACK_DAYS = 30


def get_diagnostics(
    session: Session,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    underlying: str | None = None,
) -> dict[str, Any]:
    """Aggregate diagnostics over `lookback_days`.

    Counts that surface to the WebUI:
      * Chain rows missing IV / Greeks (raw chain rows post-ingest;
        ingest already filtered hard rejects, but missing model fields
        still mean reduced downstream usability)
      * Feature-engine flag occurrences (NO_PRICE_HISTORY, etc.)
      * Expiration-event classifications (PIN_RISK / MISSING_DATA)
      * Assignment events (paper-only simplified-exit warnings)
      * Naive-GEX warnings (feature rows lacking OI base data)
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=int(lookback_days))
    params: dict[str, Any] = {"cutoff": cutoff}
    where_chain = ["snapshot_at_utc::date >= :cutoff"]
    where_feat  = ["as_of_date >= :cutoff"]
    if underlying is not None:
        where_chain.append("underlying = :underlying")
        where_feat.append("underlying = :underlying")
        params["underlying"] = underlying
    chain_where = " AND ".join(where_chain)
    feat_where  = " AND ".join(where_feat)

    chain_totals = session.execute(text(
        f"""
        SELECT COUNT(*)                                AS n_rows,
               COUNT(*) FILTER (WHERE iv IS NULL)      AS n_missing_iv,
               COUNT(*) FILTER (WHERE delta IS NULL
                              OR gamma IS NULL
                              OR theta IS NULL
                              OR vega  IS NULL)        AS n_missing_greeks
        FROM options_chain_snapshot
        WHERE {chain_where}
        """
    ), params).first()

    feature_flags_rows = session.execute(text(
        f"""
        SELECT data_quality_flags
        FROM options_feature_daily
        WHERE {feat_where}
        """
    ), params).all()

    flag_counts: dict[str, int] = {}
    n_naive_gex_warnings = 0
    for r in feature_flags_rows:
        for tok in (r.data_quality_flags or []):
            flag_counts[tok] = flag_counts.get(tok, 0) + 1
            if tok in ("NO_OPEN_INTEREST", "NO_QUOTES"):
                n_naive_gex_warnings += 1

    expiration_breakdown = session.execute(text(
        """
        SELECT classification, COUNT(*) AS n
        FROM options_expiration_event
        WHERE event_at_utc::date >= :cutoff
        GROUP BY classification
        ORDER BY classification
        """
    ), {"cutoff": cutoff}).all()

    n_pin_risk = sum(int(r.n) for r in expiration_breakdown
                     if r.classification == "PIN_RISK")
    n_missing  = sum(int(r.n) for r in expiration_breakdown
                     if r.classification == "MISSING_DATA")

    n_assignment_events = session.execute(text(
        "SELECT COUNT(*) FROM options_assignment_event "
        "WHERE event_at_utc::date >= :cutoff"
    ), {"cutoff": cutoff}).scalar_one()

    return {
        "lookback_days": int(lookback_days),
        "lookback_cutoff": cutoff.isoformat(),
        "chain": {
            "n_rows": int(chain_totals.n_rows or 0) if chain_totals else 0,
            "n_missing_iv": int(chain_totals.n_missing_iv or 0) if chain_totals else 0,
            "n_missing_greeks": int(chain_totals.n_missing_greeks or 0) if chain_totals else 0,
        },
        "features": {
            "n_rows": len(feature_flags_rows),
            "flag_counts": flag_counts,
            "n_naive_gex_warnings": int(n_naive_gex_warnings),
            "n_insufficient_iv_history":
                int(flag_counts.get("INSUFFICIENT_IV_HISTORY", 0)),
            "n_no_price_history":
                int(flag_counts.get("NO_PRICE_HISTORY", 0)),
            "n_insufficient_volume_history":
                int(flag_counts.get("INSUFFICIENT_VOLUME_HISTORY", 0)),
        },
        "expirations": {
            "by_classification": [
                {"classification": r.classification, "n": int(r.n)}
                for r in expiration_breakdown
            ],
            "n_pin_risk": int(n_pin_risk),
            "n_missing_settlement": int(n_missing),
        },
        "assignments": {
            "n_events": int(n_assignment_events),
        },
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
        "naive_gex_label":
            "Naive gamma exposure proxy — not dealer GEX",
    }
