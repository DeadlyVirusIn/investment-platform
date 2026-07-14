"""SQL-first drift monitor (Elite ArthOS Priority 4).

Lightweight, service-free drift detection over data ArthOS already has:
no Evidently, no MLflow, no Redis — plain SQL aggregation plus a small
amount of pure-Python math, emitting bounded JSON-safe reports shaped for
the Trust Center (same honesty-label discipline: below the sample gate a
check says ``insufficient_data`` instead of inventing a verdict).

Checks:
  * feature PSI            — population stability index of a numeric
                             column between a reference and a current
                             window (historical_label features).
  * score distribution     — PSI on recommendation conviction.
  * missingness drift      — NULL-rate delta per monitored column.
  * provider freshness     — age of the newest 1d price bar per provider
                             vs a weekday budget.
  * schema/version drift   — engine model_version churn in the current
                             window vs reference.

All functions take a Session and pure parameters; nothing here writes to
the database.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_SAMPLE = 100          # below this a check reports insufficient_data
PSI_WARN = 0.10           # conventional PSI thresholds
PSI_ALERT = 0.25
_BINS = 10
_MAX_ITEMS = 25           # bounded reports — Trust Center consumption


@dataclass
class DriftCheck:
    name: str
    status: str            # ok | warn | alert | insufficient_data | unavailable
    value: float | None = None
    detail: str = ""
    n_reference: int = 0
    n_current: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "status": self.status, "value": self.value,
            "detail": self.detail[:300],
            "n_reference": self.n_reference, "n_current": self.n_current,
        }


@dataclass
class DriftReport:
    generated_at: str
    reference_window: str
    current_window: str
    checks: list[DriftCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        worst = "ok"
        order = {"ok": 0, "insufficient_data": 1, "unavailable": 1,
                 "warn": 2, "alert": 3}
        for c in self.checks:
            if order.get(c.status, 0) > order.get(worst, 0):
                worst = c.status
        return {
            "generated_at": self.generated_at,
            "reference_window": self.reference_window,
            "current_window": self.current_window,
            "overall": worst,
            "checks": [c.to_dict() for c in self.checks[:_MAX_ITEMS]],
            "checks_truncated": max(0, len(self.checks) - _MAX_ITEMS),
        }


def psi(reference: list[float], current: list[float], bins: int = _BINS) -> float | None:
    """Population stability index with reference-quantile bins. Returns
    None when either side is empty or reference has no spread."""
    if not reference or not current:
        return None
    ref = sorted(reference)
    if ref[0] == ref[-1]:
        return None
    edges = [ref[int(len(ref) * i / bins)] for i in range(1, bins)]

    def bucket_fracs(vals: list[float]) -> list[float]:
        counts = [0] * bins
        for v in vals:
            i = 0
            while i < len(edges) and v > edges[i]:
                i += 1
            counts[i] += 1
        n = len(vals)
        # Laplace smoothing keeps log defined for empty buckets.
        return [(c + 0.5) / (n + 0.5 * bins) for c in counts]

    r, c = bucket_fracs(reference), bucket_fracs(current)
    return float(sum((ci - ri) * math.log(ci / ri) for ri, ci in zip(r, c)))


def _status_for_psi(v: float | None, n_ref: int, n_cur: int) -> str:
    if n_ref < MIN_SAMPLE or n_cur < MIN_SAMPLE:
        return "insufficient_data"
    if v is None:
        return "unavailable"
    if v >= PSI_ALERT:
        return "alert"
    if v >= PSI_WARN:
        return "warn"
    return "ok"


def _column_values(
    session: Session, table: str, column: str, date_col: str,
    start: dt.date, end: dt.date, extra_where: str = "",
) -> list[float]:
    # table/column names come from the monitored-column allowlists below,
    # never from user input — safe to interpolate.
    rows = session.execute(text(
        f"SELECT {column} FROM {table} "
        f"WHERE {date_col} >= :s AND {date_col} < :e "
        f"AND {column} IS NOT NULL {extra_where} LIMIT 50000"
    ), {"s": start, "e": end}).scalars().all()
    return [float(v) for v in rows]


MONITORED_FEATURES = (
    "residual_momentum_20d", "trend_strength_20d", "atr_percent_14",
    "realized_vol_20d", "price_vs_200sma",
)


def feature_psi_checks(
    session: Session, ref_start: dt.date, ref_end: dt.date,
    cur_start: dt.date, cur_end: dt.date,
) -> list[DriftCheck]:
    out = []
    for col in MONITORED_FEATURES:
        try:
            ref = _column_values(session, "historical_label", col,
                                 "as_of_date", ref_start, ref_end)
            cur = _column_values(session, "historical_label", col,
                                 "as_of_date", cur_start, cur_end)
        except Exception as exc:  # noqa: BLE001 — absent table/column: visible
            out.append(DriftCheck(f"feature_psi:{col}", "unavailable",
                                  detail=str(exc)[:120]))
            continue
        v = psi(ref, cur)
        out.append(DriftCheck(
            f"feature_psi:{col}", _status_for_psi(v, len(ref), len(cur)),
            value=v, n_reference=len(ref), n_current=len(cur),
        ))
    return out


def score_distribution_check(
    session: Session, ref_start: dt.date, ref_end: dt.date,
    cur_start: dt.date, cur_end: dt.date,
) -> DriftCheck:
    where = " AND model_version NOT LIKE '%+replay:%'"
    ref = _column_values(session, "recommendation", "conviction",
                         "generated_at", ref_start, ref_end, where)
    cur = _column_values(session, "recommendation", "conviction",
                         "generated_at", cur_start, cur_end, where)
    v = psi(ref, cur)
    return DriftCheck("score_distribution_psi",
                      _status_for_psi(v, len(ref), len(cur)),
                      value=v, n_reference=len(ref), n_current=len(cur))


def missingness_checks(
    session: Session, ref_start: dt.date, ref_end: dt.date,
    cur_start: dt.date, cur_end: dt.date,
) -> list[DriftCheck]:
    out = []
    for col in MONITORED_FEATURES:
        row = session.execute(text(
            f"SELECT "
            f"(SELECT count(*) FROM historical_label WHERE as_of_date >= :rs AND as_of_date < :re) AS ref_n, "
            f"(SELECT count(*) FROM historical_label WHERE as_of_date >= :rs AND as_of_date < :re AND {col} IS NULL) AS ref_null, "
            f"(SELECT count(*) FROM historical_label WHERE as_of_date >= :cs AND as_of_date < :ce) AS cur_n, "
            f"(SELECT count(*) FROM historical_label WHERE as_of_date >= :cs AND as_of_date < :ce AND {col} IS NULL) AS cur_null"
        ), {"rs": ref_start, "re": ref_end, "cs": cur_start, "ce": cur_end}
        ).mappings().one()
        if row["ref_n"] < MIN_SAMPLE or row["cur_n"] < MIN_SAMPLE:
            out.append(DriftCheck(f"missingness:{col}", "insufficient_data",
                                  n_reference=row["ref_n"], n_current=row["cur_n"]))
            continue
        delta = row["cur_null"] / row["cur_n"] - row["ref_null"] / row["ref_n"]
        status = "alert" if abs(delta) >= 0.20 else ("warn" if abs(delta) >= 0.05 else "ok")
        out.append(DriftCheck(f"missingness:{col}", status, value=float(delta),
                              n_reference=row["ref_n"], n_current=row["cur_n"]))
    return out


def provider_freshness_checks(
    session: Session, now: dt.datetime, budget_weekdays: int = 3,
) -> list[DriftCheck]:
    rows = session.execute(text(
        "SELECT provider, max(ts) AS newest FROM price_bar "
        "WHERE timeframe = '1d' GROUP BY provider"
    )).mappings().all()
    out = []
    for r in rows:
        newest = r["newest"]
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=dt.timezone.utc)
        age_days = 0
        cur = newest.date()
        while cur < now.date():
            cur += dt.timedelta(days=1)
            if cur.weekday() < 5:
                age_days += 1
        status = "alert" if age_days > 2 * budget_weekdays else (
            "warn" if age_days > budget_weekdays else "ok")
        out.append(DriftCheck(f"provider_freshness:{r['provider']}", status,
                              value=float(age_days),
                              detail=f"newest bar {newest.date().isoformat()}"))
    if not rows:
        out.append(DriftCheck("provider_freshness", "unavailable",
                              detail="no 1d price bars"))
    return out


def schema_version_check(
    session: Session, ref_start: dt.date, ref_end: dt.date,
    cur_start: dt.date, cur_end: dt.date,
) -> DriftCheck:
    q = ("SELECT count(DISTINCT model_version) FROM recommendation "
         "WHERE generated_at >= :s AND generated_at < :e "
         "AND model_version NOT LIKE '%+replay:%'")
    ref_n = session.execute(text(q), {"s": ref_start, "e": ref_end}).scalar() or 0
    cur_n = session.execute(text(q), {"s": cur_start, "e": cur_end}).scalar() or 0
    status = "ok"
    detail = f"{ref_n} reference vs {cur_n} current engine versions"
    if cur_n > 1:
        status = "warn"
        detail += " — mixed engine versions in the current window"
    return DriftCheck("engine_version_churn", status,
                      value=float(cur_n), detail=detail,
                      n_reference=ref_n, n_current=cur_n)


def run_drift_report(
    session: Session, *, now: dt.datetime,
    reference_days: int = 90, current_days: int = 14,
) -> DriftReport:
    cur_end = now.date() + dt.timedelta(days=1)
    cur_start = cur_end - dt.timedelta(days=current_days)
    ref_end = cur_start
    ref_start = ref_end - dt.timedelta(days=reference_days)

    report = DriftReport(
        generated_at=now.isoformat(),
        reference_window=f"{ref_start.isoformat()}..{ref_end.isoformat()}",
        current_window=f"{cur_start.isoformat()}..{cur_end.isoformat()}",
    )
    report.checks.extend(feature_psi_checks(session, ref_start, ref_end,
                                            cur_start, cur_end))
    report.checks.append(score_distribution_check(session, ref_start, ref_end,
                                                  cur_start, cur_end))
    report.checks.extend(missingness_checks(session, ref_start, ref_end,
                                            cur_start, cur_end))
    report.checks.extend(provider_freshness_checks(session, now))
    report.checks.append(schema_version_check(session, ref_start, ref_end,
                                              cur_start, cur_end))
    return report
