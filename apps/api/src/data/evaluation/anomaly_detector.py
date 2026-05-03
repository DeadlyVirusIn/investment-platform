"""Phase MON1 — anomaly detection layer.

Read-only. Runs AFTER strategy has executed. Never mutates decisions.

Rules are simple heuristics with fixed conservative thresholds. No ML.
Rule set is documented in the RULES dict below.

Categories:
  decision | trade | regime | data | shadow

Severities:
  info | warning | critical
"""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
from dataclasses import dataclass, field, asdict
from typing import Literal

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

Category = Literal["decision", "trade", "regime", "data", "shadow"]
Severity = Literal["info", "warning", "critical"]


# ---------------------------------------------------------------------------
# Rule catalogue (explainable, fixed thresholds)
# ---------------------------------------------------------------------------
RULES = {
    # Decision anomalies
    "no_trade_streak_directional_5": {
        "category": "decision", "severity": "warning",
        "description": (
            "5+ consecutive directional-regime days with no Engine B fire — "
            "credit_stable AND rates_calm should have aligned at least once."
        ),
    },
    "no_trade_streak_stress_10": {
        "category": "decision", "severity": "info",
        "description": "10+ consecutive stress-regime days with no P15 entry.",
    },
    "engine_blocked_repeatedly": {
        "category": "decision", "severity": "warning",
        "description": "Decision blocked_by populated 2+ days in past 5.",
    },
    # Trade anomalies
    "slippage_excess": {
        "category": "trade", "severity": "warning",
        "description": (
            "Realized slippage > 2x rolling 20-trade median for this engine."
        ),
    },
    "large_loss": {
        "category": "trade", "severity": "warning",
        "description": "Trade net return below 5th percentile of engine history.",
    },
    "short_hold_engine_a": {
        "category": "trade", "severity": "info",
        "description": "Engine A position closed <5 bars (normal hold is 10).",
    },
    "consecutive_losers": {
        "category": "trade", "severity": "warning",
        "description": "3+ consecutive losing trades in same engine.",
    },
    # Regime anomalies
    "long_stress_streak_20": {
        "category": "regime", "severity": "warning",
        "description": "20+ consecutive bars in stress regime.",
    },
    "regime_flip_burst": {
        "category": "regime", "severity": "warning",
        "description": "More than 3 regime flips in past 5 trading days.",
    },
    # Data anomalies
    "fred_timeout_streak": {
        "category": "data", "severity": "critical",
        "description": (
            "FRED ingestion warned/failed 3+ consecutive daily runs."
        ),
    },
    "missing_decision_log": {
        "category": "data", "severity": "critical",
        "description": (
            "Trading day has no decision_log row — strategy did not execute."
        ),
    },
    "stale_feature": {
        "category": "data", "severity": "warning",
        "description": "Production feature row is >1 trading day old.",
    },
    "pit_violation": {
        "category": "data", "severity": "critical",
        "description": (
            "Decision inputs_used contains value with published_at > "
            "decision timestamp."
        ),
    },
    # Shadow / diagnostic anomalies — NEVER AFFECT DECISIONS
    "gex_cluster_losses": {
        "category": "shadow", "severity": "info",
        "description": (
            "3+ recent losing trades occurred on NEG_GEX days "
            "(diagnostic observation only)."
        ),
    },
    "diag_disagree_streak": {
        "category": "shadow", "severity": "info",
        "description": (
            "Candidate overlay would have diverged from production for "
            "5+ consecutive days (diagnostic only)."
        ),
    },
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class AnomalyEvent:
    as_of_date: dt.date
    category: Category
    severity: Severity
    rule_key: str
    title: str
    description: str
    related_engine: str | None = None
    related_trade_id: str | None = None
    related_decision_id: str | None = None
    metrics_snapshot: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detection entry
# ---------------------------------------------------------------------------
def detect_anomalies(
    session: Session, as_of_date: dt.date,
) -> list[AnomalyEvent]:
    """Run all anomaly checks for a given trading day. Returns list of events."""
    results: list[AnomalyEvent] = []

    results.extend(_detect_decision_anomalies(session, as_of_date))
    results.extend(_detect_trade_anomalies(session, as_of_date))
    results.extend(_detect_regime_anomalies(session, as_of_date))
    results.extend(_detect_data_anomalies(session, as_of_date))
    results.extend(_detect_shadow_anomalies(session, as_of_date))

    logger.info("[mon1] detected {} anomalies for {}", len(results), as_of_date)
    return results


# ---------------------------------------------------------------------------
# Decision anomalies
# ---------------------------------------------------------------------------
def _detect_decision_anomalies(
    session: Session, as_of: dt.date,
) -> list[AnomalyEvent]:
    out: list[AnomalyEvent] = []

    # Streak of no-fire days in directional regime
    rows = session.execute(text("""
        SELECT as_of_date, engine, action
        FROM decision_log
        WHERE as_of_date <= :d
        ORDER BY as_of_date DESC LIMIT 10
    """), {"d": as_of}).fetchall()

    dir_no_fire_streak = 0
    stress_no_fire_streak = 0
    blocked_count = 0
    for r in rows:
        if r.engine == "A" and r.action == "enter_long":
            break
        # Use decision engine field: no_fire = engine='none' OR action != enter_long
        if r.action != "enter_long":
            # Need context from context_daily to know regime
            ctx = _get_regime(session, r.as_of_date)
            if ctx == "directional":
                dir_no_fire_streak += 1
                if dir_no_fire_streak >= 5:
                    continue
            elif ctx == "stress":
                stress_no_fire_streak += 1
        else:
            break
    if dir_no_fire_streak >= 5:
        rule = RULES["no_trade_streak_directional_5"]
        out.append(AnomalyEvent(
            as_of_date=as_of, category="decision", severity="warning",
            rule_key="no_trade_streak_directional_5",
            title=f"{dir_no_fire_streak} directional days without Engine B fire",
            description=rule["description"],
            metrics_snapshot={"streak_days": dir_no_fire_streak},
        ))
    if stress_no_fire_streak >= 10:
        out.append(AnomalyEvent(
            as_of_date=as_of, category="decision", severity="info",
            rule_key="no_trade_streak_stress_10",
            title=f"{stress_no_fire_streak} stress days without P15 entry",
            description=RULES["no_trade_streak_stress_10"]["description"],
            metrics_snapshot={"streak_days": stress_no_fire_streak},
        ))

    # blocked_by in past 5 days
    row = session.execute(text("""
        SELECT COUNT(*) AS n
        FROM decision_log
        WHERE as_of_date BETWEEN :start AND :end
          AND blocked_by IS NOT NULL AND blocked_by != ''
    """), {"start": as_of - dt.timedelta(days=5), "end": as_of}).fetchone()
    if row and (row.n or 0) >= 2:
        out.append(AnomalyEvent(
            as_of_date=as_of, category="decision", severity="warning",
            rule_key="engine_blocked_repeatedly",
            title=f"{row.n} blocked decisions in past 5 days",
            description=RULES["engine_blocked_repeatedly"]["description"],
            metrics_snapshot={"blocked_count_5d": int(row.n)},
        ))
    return out


def _get_regime(session: Session, d: dt.date) -> str:
    """Return 'stress' | 'directional' | 'none' from production context."""
    rows = session.execute(text("""
        SELECT context_name, value_bool
        FROM context_daily
        WHERE as_of_date = :d AND status = 'production'
    """), {"d": d}).fetchall()
    stress = False; directional = False
    for r in rows:
        if r.context_name == "stress_regime": stress = bool(r.value_bool)
        if r.context_name == "directional_regime": directional = bool(r.value_bool)
    return "stress" if stress else "directional" if directional else "none"


# ---------------------------------------------------------------------------
# Trade anomalies
# ---------------------------------------------------------------------------
def _detect_trade_anomalies(
    session: Session, as_of: dt.date,
) -> list[AnomalyEvent]:
    out: list[AnomalyEvent] = []

    # Trades closed on as_of_date
    recent = session.execute(text("""
        SELECT id, engine, entry_date, exit_date, entry_price, exit_price,
               net_ret_pct, slippage_bps_assumed, regime_at_entry
        FROM paper_trade_log
        WHERE exit_date = :d AND status = 'closed'
    """), {"d": as_of}).fetchall()

    for t in recent:
        engine = t.engine
        net = float(t.net_ret_pct) if t.net_ret_pct is not None else None

        # Baseline: historical net returns for this engine (exclude today)
        hist_rows = session.execute(text("""
            SELECT net_ret_pct FROM paper_trade_log
            WHERE engine = :e AND status = 'closed' AND exit_date < :d
              AND net_ret_pct IS NOT NULL
            ORDER BY exit_date DESC LIMIT 40
        """), {"e": engine, "d": as_of}).fetchall()
        hist = [float(r.net_ret_pct) for r in hist_rows]

        # short_hold_engine_a
        if engine == "A" and t.entry_date and t.exit_date:
            days = (t.exit_date - t.entry_date).days
            if days < 5:
                out.append(AnomalyEvent(
                    as_of_date=as_of, category="trade", severity="info",
                    rule_key="short_hold_engine_a",
                    title=f"Engine A closed in {days}d (expected ~10)",
                    description=RULES["short_hold_engine_a"]["description"],
                    related_engine="A", related_trade_id=str(t.id),
                    metrics_snapshot={"bars_held": days},
                ))

        # large_loss vs 5th percentile
        if hist and len(hist) >= 10 and net is not None:
            sorted_h = sorted(hist)
            p05 = sorted_h[max(0, int(0.05 * len(sorted_h)) - 1)]
            if net < p05:
                out.append(AnomalyEvent(
                    as_of_date=as_of, category="trade", severity="warning",
                    rule_key="large_loss",
                    title=f"{engine} loss {net:.3f}% below p5 ({p05:.3f}%)",
                    description=RULES["large_loss"]["description"],
                    related_engine=engine, related_trade_id=str(t.id),
                    metrics_snapshot={
                        "net_pct": net, "p05_pct": p05,
                        "hist_n": len(hist),
                    },
                ))

    # Consecutive losers
    last_rows = session.execute(text("""
        SELECT engine, net_ret_pct, exit_date
        FROM paper_trade_log
        WHERE status = 'closed' AND exit_date <= :d
          AND net_ret_pct IS NOT NULL
        ORDER BY exit_date DESC LIMIT 5
    """), {"d": as_of}).fetchall()
    by_engine_losses: dict[str, int] = {"A": 0, "B": 0}
    by_engine_last_seen: dict[str, bool] = {"A": True, "B": True}
    for r in last_rows:
        if not by_engine_last_seen[r.engine]: continue
        if float(r.net_ret_pct) < 0:
            by_engine_losses[r.engine] += 1
        else:
            by_engine_last_seen[r.engine] = False
    for eng, n in by_engine_losses.items():
        if n >= 3:
            out.append(AnomalyEvent(
                as_of_date=as_of, category="trade", severity="warning",
                rule_key="consecutive_losers",
                title=f"Engine {eng}: {n} consecutive losing trades",
                description=RULES["consecutive_losers"]["description"],
                related_engine=eng,
                metrics_snapshot={"streak": n},
            ))
    return out


# ---------------------------------------------------------------------------
# Regime anomalies
# ---------------------------------------------------------------------------
def _detect_regime_anomalies(
    session: Session, as_of: dt.date,
) -> list[AnomalyEvent]:
    out: list[AnomalyEvent] = []

    # Long stress streak
    rows = session.execute(text("""
        SELECT as_of_date, value_bool FROM context_daily
        WHERE context_name = 'stress_regime' AND status = 'production'
          AND as_of_date <= :d
        ORDER BY as_of_date DESC LIMIT 30
    """), {"d": as_of}).fetchall()
    streak = 0
    for r in rows:
        if bool(r.value_bool): streak += 1
        else: break
    if streak >= 20:
        out.append(AnomalyEvent(
            as_of_date=as_of, category="regime", severity="warning",
            rule_key="long_stress_streak_20",
            title=f"{streak} consecutive stress-regime days",
            description=RULES["long_stress_streak_20"]["description"],
            metrics_snapshot={"streak_days": streak},
        ))

    # Flip burst
    flip_rows = session.execute(text("""
        SELECT as_of_date, value_bool FROM context_daily
        WHERE context_name = 'stress_regime' AND status = 'production'
          AND as_of_date BETWEEN :start AND :end
        ORDER BY as_of_date ASC
    """), {"start": as_of - dt.timedelta(days=5), "end": as_of}).fetchall()
    flips = sum(
        1 for i in range(1, len(flip_rows))
        if bool(flip_rows[i].value_bool) != bool(flip_rows[i - 1].value_bool)
    )
    if flips > 3:
        out.append(AnomalyEvent(
            as_of_date=as_of, category="regime", severity="warning",
            rule_key="regime_flip_burst",
            title=f"{flips} regime flips in past 5 days",
            description=RULES["regime_flip_burst"]["description"],
            metrics_snapshot={"flips_5d": flips},
        ))
    return out


# ---------------------------------------------------------------------------
# Data anomalies
# ---------------------------------------------------------------------------
def _detect_data_anomalies(
    session: Session, as_of: dt.date,
) -> list[AnomalyEvent]:
    out: list[AnomalyEvent] = []

    # Missing decision_log row for a valid trading day (weekday)
    if as_of.weekday() < 5:   # Mon-Fri
        exists = session.execute(text("""
            SELECT 1 FROM decision_log WHERE as_of_date = :d LIMIT 1
        """), {"d": as_of}).fetchone()
        if not exists:
            out.append(AnomalyEvent(
                as_of_date=as_of, category="data", severity="critical",
                rule_key="missing_decision_log",
                title=f"No decision_log entry for trading day {as_of}",
                description=RULES["missing_decision_log"]["description"],
            ))

    # Stale feature: production feature computed >1 trading day ago
    # (approximated by date-gap check)
    stale_rows = session.execute(text("""
        SELECT feature_name, MAX(as_of_date) AS latest
        FROM features_daily
        WHERE feature_name IN ('d10y_5d', 'rates_calm', 'credit_stable',
                                'vrp_supportive', 'liquidity_expanding')
        GROUP BY feature_name
    """)).fetchall()
    for r in stale_rows:
        if r.latest is None: continue
        gap = (as_of - r.latest).days
        if gap > 3:   # more than 1 trading day including weekends
            out.append(AnomalyEvent(
                as_of_date=as_of, category="data", severity="warning",
                rule_key="stale_feature",
                title=f"Feature '{r.feature_name}' stale ({gap}d old)",
                description=RULES["stale_feature"]["description"],
                metrics_snapshot={
                    "feature_name": r.feature_name, "age_days": gap,
                },
            ))
    return out


# ---------------------------------------------------------------------------
# Shadow / diagnostic anomalies (NEVER AFFECT DECISIONS)
# ---------------------------------------------------------------------------
def _detect_shadow_anomalies(
    session: Session, as_of: dt.date,
) -> list[AnomalyEvent]:
    out: list[AnomalyEvent] = []

    # GEX cluster with losses: check if 3+ recent closed losers occurred
    # on days where gex_context_flag (diagnostic) was True.
    rows = session.execute(text("""
        SELECT t.id, t.entry_date, t.net_ret_pct,
               (SELECT value_bool FROM context_daily cd
                 WHERE cd.as_of_date = t.entry_date
                   AND cd.context_name = 'gex_context_flag'
                   AND cd.status = 'diagnostic'
                 LIMIT 1) AS gex_neg
        FROM paper_trade_log t
        WHERE t.status = 'closed' AND t.exit_date <= :d
          AND t.net_ret_pct < 0
        ORDER BY t.exit_date DESC LIMIT 10
    """), {"d": as_of}).fetchall()
    cluster = sum(1 for r in rows if r.gex_neg)
    if cluster >= 3:
        out.append(AnomalyEvent(
            as_of_date=as_of, category="shadow", severity="info",
            rule_key="gex_cluster_losses",
            title=(
                f"{cluster} losing trades occurred during NEG_GEX "
                f"(diagnostic — not used in production)"
            ),
            description=RULES["gex_cluster_losses"]["description"],
            metrics_snapshot={"losses_in_neg_gex": cluster,
                              "sample_window": 10},
        ))
    return out


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def persist_anomalies(
    session: Session, events: list[AnomalyEvent],
) -> int:
    """Upsert by (as_of_date, rule_key, related_trade_id). Returns rows written."""
    n = 0
    for e in events:
        r = session.execute(text("""
            INSERT INTO anomaly_event
              (as_of_date, category, severity, rule_key, title, description,
               related_engine, related_trade_id, related_decision_id,
               metrics_snapshot, status)
            VALUES
              (:d, :cat, :sev, :rk, :ti, :desc,
               :eng, CAST(:tid AS uuid), CAST(:did AS uuid),
               CAST(:ms AS jsonb), 'open')
            ON CONFLICT (as_of_date, rule_key, related_trade_id) DO NOTHING
        """), {
            "d": e.as_of_date, "cat": e.category, "sev": e.severity,
            "rk": e.rule_key, "ti": e.title, "desc": e.description,
            "eng": e.related_engine,
            "tid": e.related_trade_id, "did": e.related_decision_id,
            "ms": json.dumps(e.metrics_snapshot, default=str),
        })
        n += r.rowcount or 0
    session.commit()
    return n


def summarize(events: list[AnomalyEvent]) -> dict:
    by_sev: dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    by_cat: dict[str, int] = {}
    for e in events:
        by_sev[e.severity] = by_sev.get(e.severity, 0) + 1
        by_cat[e.category] = by_cat.get(e.category, 0) + 1
    top3 = sorted(
        events,
        key=lambda e: {"critical": 0, "warning": 1, "info": 2}[e.severity],
    )[:3]
    return {
        "total": len(events),
        "by_severity": by_sev,
        "by_category": by_cat,
        "top_3": [asdict(e) for e in top3],
    }
