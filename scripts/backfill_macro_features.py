"""Phase 11P.2 - Manual macro-feature backfill CLI.

Pulls FRED series, persists them append-only into `features_daily`,
recomputes the 4 production gate booleans per business day, and writes
them append-only into `context_daily` tagged with a frozen logic
version.

Hard guarantees:
  * Default mode is --dry-run; no writes.
  * --commit requires --confirm-commit YES.
  * Append-only writes (ON CONFLICT DO NOTHING) on natural keys.
  * NEVER changes any compute_* function in
    apps/api/src/data/features/*.
  * NEVER touches strict engine code (engine_a / engine_b / selector /
    production.py).
  * NEVER imports broker / live / execution modules.
  * NEVER schedules itself. Manual operator invocation only.

Exit codes (mirroring 11O scheme):
  0  success
  2  precondition / safety / config failure
  3  fetch failure
  4  zero rows produced
  9  internal error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from sqlalchemy import text

from apps.api.src.config import settings as default_settings
from apps.api.src.data.features.credit import (
    compute_credit_stable,
    FEATURE_VERSION as CREDIT_FV,
)
from apps.api.src.data.features.liquidity import (
    compute_liquidity_expanding,
    FEATURE_VERSION as LIQ_FV,
)
from apps.api.src.data.features.rates import (
    compute_rates_calm,
    FEATURE_VERSION as RATES_FV,
)
from apps.api.src.data.features.vol import (
    compute_vrp_supportive,
    FEATURE_VERSION as VOL_FV,
)
from apps.api.src.data.macro.fred_adapter import (
    FredAPIError,
    FredAdapter,
    FredConfigError,
    FredUnavailable,
)
from apps.api.src.db import SessionLocal


LOGIC_VERSION = "v1.0.0"
SOURCE_TAG = "backfill_macro_features"
JSONL_LOG_DIR = Path("logs")
JSONL_LOG_PREFIX = "macro_backfill_"

DEFAULT_SERIES = ("DGS10", "VIXCLS", "BAMLH0A0HYM2",
                  "WALCL", "WTREGEN", "RRPONTSYD")

# Phase 11Z — wide-window fetch defaults.
# Per-day reruns must fetch enough history for every gate compute fn:
#   rates_calm:          6 DGS10 obs (5d Δ)
#   credit_stable:       21 HYOAS obs
#   vrp_supportive:      52+ SPY days (21-day rolling RV → ≥30 valid VRP)
#   liquidity_expanding: WALCL/WTREGEN/RRP at as_of AND as_of−20d
# 120 calendar days covers ≥80 business days for daily series, the
# 52-business-day vrp_supportive requirement (with safety margin),
# and ≥15 weekly observations for WALCL/WTREGEN.
DEFAULT_LOOKBACK_DAYS = 120

# Per-series staleness tolerance (calendar days). If the latest
# observation in the fetched window is older than this relative to
# `as_of`, the gate is recorded as `stale_data` rather than computed.
STALE_TOLERANCE_DAYS: dict[str, int] = {
    "DGS10":        5,
    "VIXCLS":       5,
    "BAMLH0A0HYM2": 5,
    "WALCL":       14,   # weekly Wed series
    "WTREGEN":     14,   # weekly Wed series
    "RRPONTSYD":    5,
    "SPY":          5,
}

# Diagnostic status enum (matches migration 055
# `ck_context_daily_status` updated values).
STATUS_PRODUCTION       = "production"
STATUS_INSUFFICIENT     = "insufficient_data"
STATUS_MISSING          = "missing_data"
STATUS_STALE            = "stale_data"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BackfillConfig:
    start: dt.date
    end: dt.date
    series: tuple[str, ...]
    dry_run: bool
    commit: bool
    logic_version: str
    explain: bool
    lookback_days: int = DEFAULT_LOOKBACK_DAYS

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError(
                "dry_run and commit are mutually exclusive"
            )
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if not self.series:
            raise ValueError("series must be non-empty")
        if self.lookback_days < 0:
            raise ValueError("lookback_days must be >= 0")

    @property
    def fetch_start(self) -> dt.date:
        """Phase 11Z — fetch window starts `lookback_days` calendar
        days before the persistence window, so single-day reruns
        still pull enough history for every gate compute fn."""
        return self.start - dt.timedelta(days=int(self.lookback_days))


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backfill_macro_features",
        description=(
            "Manual macro feature backfill (FRED). Default: dry-run. "
            "No scheduler. No automation. No live execution."
        ),
    )
    p.add_argument(
        "--start", type=lambda s: dt.date.fromisoformat(s),
        default=dt.date.today() - dt.timedelta(days=365 * 5),
    )
    p.add_argument(
        "--end", type=lambda s: dt.date.fromisoformat(s),
        default=dt.date.today(),
    )
    p.add_argument(
        "--series",
        type=lambda s: tuple(x.strip().upper() for x in s.split(",") if x.strip()),
        default=DEFAULT_SERIES,
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    p.add_argument("--confirm-commit", default=None)
    p.add_argument("--logic-version", default=LOGIC_VERSION)
    p.add_argument("--explain", action="store_true")
    p.add_argument(
        "--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=(
            "Phase 11Z — calendar-day lookback added before --start "
            "for fetching only. Persistence is still bounded by "
            "[--start, --end]. Default %(default)s covers all gate "
            "minimum-history requirements."
        ),
    )
    return p.parse_args(argv)


def _confirm(args: argparse.Namespace) -> bool:
    if not args.commit:
        return True
    if args.confirm_commit == "YES":
        return True
    if sys.stdin.isatty():
        sys.stdout.write("Type YES to confirm commit: ")
        sys.stdout.flush()
        return sys.stdin.readline().strip() == "YES"
    return False


# ---------------------------------------------------------------------------
# Persistence (append-only)
# ---------------------------------------------------------------------------

_INSERT_FEATURE_SQL = text(
    """
    INSERT INTO features_daily
      (as_of_date, feature_name, value, value_bool,
       input_hash, computed_at, feature_version)
    VALUES
      (:as_of_date, :feature_name, :value, NULL,
       :input_hash, now(), :feature_version)
    ON CONFLICT DO NOTHING
    """
)

_INSERT_CONTEXT_SQL = text(
    """
    INSERT INTO context_daily
      (as_of_date, context_name, status, value_bool,
       source_features, logic_version, logic_hash, computed_at)
    VALUES
      (:as_of_date, :context_name, :status, :value_bool,
       :source_features, :logic_version, :logic_hash, now())
    ON CONFLICT (as_of_date, context_name, logic_version) DO UPDATE
      SET status      = EXCLUDED.status,
          value_bool  = EXCLUDED.value_bool,
          computed_at = EXCLUDED.computed_at
    """
)


def _logic_hash(name: str, version: str) -> str:
    import hashlib
    return hashlib.sha256(
        f"{name}:{version}:{SOURCE_TAG}".encode("utf-8"),
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def fetch_all_series(
    adapter: FredAdapter,
    *,
    series: Sequence[str],
    start: dt.date,
    end: dt.date,
) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for sid in series:
        s = adapter.fetch_series(sid, start=start, end=end)
        out[sid] = s
    return out


def load_spy_close(
    start: dt.date,
    end: dt.date,
    *,
    session_factory=None,
) -> pd.Series:
    """SPY adjusted close from existing price_bar table — used by
    compute_vrp_supportive. Returns empty Series when SPY missing."""
    sf = session_factory or SessionLocal
    with sf() as session:
        rows = session.execute(text(
            """
            SELECT pb.ts::date AS d, pb.adjusted_close
            FROM price_bar pb
            JOIN asset a ON a.id = pb.asset_id
            WHERE a.symbol = 'SPY'
              AND pb.timeframe = '1d'
              AND pb.ts::date BETWEEN :start AND :end
            ORDER BY pb.ts::date
            """
        ), {"start": start, "end": end}).all()
    if not rows:
        return pd.Series(dtype="float64", name="SPY")
    idx = pd.to_datetime([r.d for r in rows])
    return pd.Series(
        [float(r.adjusted_close) for r in rows],
        index=idx, name="SPY", dtype="float64",
    )


def compute_gates_for_day(
    series: dict[str, pd.Series],
    spy: pd.Series,
    *,
    as_of: dt.date,
) -> dict[str, bool | None]:
    """Legacy bool-only gate dispatch (kept for compat with existing
    callers / tests). Returns the raw True/False/None directly from
    each compute_* fn — no diagnostic envelope. Phase 11Z prefers
    `compute_gates_with_diagnostics` for persistence."""
    dgs10 = series.get("DGS10", pd.Series(dtype="float64"))
    vix   = series.get("VIXCLS", pd.Series(dtype="float64"))
    hyoas = series.get("BAMLH0A0HYM2", pd.Series(dtype="float64"))
    walcl = series.get("WALCL", pd.Series(dtype="float64"))
    wtreg = series.get("WTREGEN", pd.Series(dtype="float64"))
    rrp   = series.get("RRPONTSYD", pd.Series(dtype="float64"))
    return {
        "rates_calm":           compute_rates_calm(dgs10, as_of),
        "vrp_supportive":       compute_vrp_supportive(vix, spy, as_of),
        "credit_stable":        compute_credit_stable(hyoas, None, as_of),
        "liquidity_expanding":  compute_liquidity_expanding(
            walcl, wtreg, rrp, as_of,
        ),
    }


# ---------------------------------------------------------------------------
# Phase 11Z — diagnostic gate dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateDiagnostic:
    """Per-gate result plus the diagnostic info needed for
    `context_daily` semantics. `value` is the True/False/None gate
    boolean. `status` is one of {production, insufficient_data,
    missing_data, stale_data}."""
    name: str
    value: bool | None
    status: str
    reason: str
    required_obs: int
    available_obs: int
    latest_input_date: dt.date | None
    inputs_used: tuple[str, ...]


def _series_state(
    s: pd.Series, *, as_of: dt.date, sid: str, required: int,
) -> tuple[str, str, int, dt.date | None]:
    """Classify a single FRED-style series into one of the diagnostic
    statuses. Returns (status, reason, available_obs, latest_date).
    `production` here means "this series is fit-for-use"; the
    caller must still call the gate compute fn before declaring the
    overall gate `production`."""
    s2 = s.loc[:as_of] if not s.empty else s
    available = int(len(s2))
    if available == 0:
        return STATUS_MISSING, f"no {sid} obs on or before {as_of}", 0, None
    latest_ts = s2.index[-1]
    latest_d = (
        latest_ts.date() if hasattr(latest_ts, "date") else latest_ts
    )
    if available < required:
        return (
            STATUS_INSUFFICIENT,
            f"need >={required} {sid} obs, have {available}",
            available, latest_d,
        )
    tol = STALE_TOLERANCE_DAYS.get(sid, 5)
    lag = (as_of - latest_d).days
    if lag > tol:
        return (
            STATUS_STALE,
            f"latest {sid}={latest_d} ({lag}d > {tol}d tolerance)",
            available, latest_d,
        )
    return STATUS_PRODUCTION, "ok", available, latest_d


def _worst_status(states: list[tuple[str, str, int, dt.date | None]]) -> int:
    """Status priority — higher means more severe (overrides)."""
    pri = {
        STATUS_PRODUCTION: 0,
        STATUS_STALE: 1,
        STATUS_INSUFFICIENT: 2,
        STATUS_MISSING: 3,
    }
    return max(pri[st[0]] for st in states)


def _combine(
    name: str, *,
    inputs: list[tuple[str, pd.Series, int]],
    as_of: dt.date,
    compute_value: callable,
) -> GateDiagnostic:
    """Run per-input series classification, pick the worst status,
    and only invoke `compute_value()` when every input is
    `production`-fit. Returns a GateDiagnostic envelope."""
    states = [
        (sid, *_series_state(s, as_of=as_of, sid=sid, required=req))
        for sid, s, req in inputs
    ]
    inputs_used = tuple(sid for sid, _, _ in inputs)
    severity_priority = {
        STATUS_PRODUCTION: 0,
        STATUS_STALE: 1,
        STATUS_INSUFFICIENT: 2,
        STATUS_MISSING: 3,
    }
    worst = max(states, key=lambda st: severity_priority[st[1]])
    status, reason = worst[1], worst[2]
    # combined available_obs/latest_date: report the bottleneck input's
    available_obs = worst[3]
    latest_date = worst[4]
    # required_obs: max requirement across inputs (rough, summary-only)
    req_total = max(req for _, _, req in inputs) if inputs else 0
    if status != STATUS_PRODUCTION:
        return GateDiagnostic(
            name=name, value=None, status=status,
            reason=f"{worst[0]}: {reason}",
            required_obs=req_total, available_obs=available_obs,
            latest_input_date=latest_date, inputs_used=inputs_used,
        )
    # All inputs OK — compute the value.
    val = compute_value()
    if val is None:
        # Defensive: compute fn refused despite passing checks.
        # Treat as insufficient_data with explicit reason.
        return GateDiagnostic(
            name=name, value=None, status=STATUS_INSUFFICIENT,
            reason="compute_returned_none_despite_input_checks",
            required_obs=req_total, available_obs=available_obs,
            latest_input_date=latest_date, inputs_used=inputs_used,
        )
    return GateDiagnostic(
        name=name, value=bool(val), status=STATUS_PRODUCTION,
        reason="computed",
        required_obs=req_total, available_obs=available_obs,
        latest_input_date=latest_date, inputs_used=inputs_used,
    )


def compute_gates_with_diagnostics(
    series: dict[str, pd.Series],
    spy: pd.Series,
    *,
    as_of: dt.date,
) -> dict[str, GateDiagnostic]:
    """Phase 11Z replacement for the bool-only dispatch. Each gate
    now returns a `GateDiagnostic` envelope so the persister can
    distinguish missing/insufficient/stale inputs from real True/
    False values. The compute_* functions in
    apps/api/src/data/features/* are NOT touched — they are called
    only after every required input passes its gating checks."""
    dgs10 = series.get("DGS10", pd.Series(dtype="float64"))
    vix   = series.get("VIXCLS", pd.Series(dtype="float64"))
    hyoas = series.get("BAMLH0A0HYM2", pd.Series(dtype="float64"))
    walcl = series.get("WALCL", pd.Series(dtype="float64"))
    wtreg = series.get("WTREGEN", pd.Series(dtype="float64"))
    rrp   = series.get("RRPONTSYD", pd.Series(dtype="float64"))

    rates = _combine(
        "rates_calm",
        inputs=[("DGS10", dgs10, 6)],
        as_of=as_of,
        compute_value=lambda: compute_rates_calm(dgs10, as_of),
    )

    # vrp_supportive needs SPY (≥52 daily obs so 21d-rolling RV
    # produces ≥30 valid VRP points) and VIX (≥1 obs at as_of).
    vrp = _combine(
        "vrp_supportive",
        inputs=[("SPY", spy, 52), ("VIXCLS", vix, 1)],
        as_of=as_of,
        compute_value=lambda: compute_vrp_supportive(vix, spy, as_of),
    )

    credit = _combine(
        "credit_stable",
        inputs=[("BAMLH0A0HYM2", hyoas, 21)],
        as_of=as_of,
        compute_value=lambda: compute_credit_stable(hyoas, None, as_of),
    )

    # liquidity_expanding needs WALCL/WTREGEN/RRP at as_of *and* at
    # as_of−20d. Treat the lookback presence as part of the input
    # contract: we need each series to start ≤ (as_of − 20d).
    past = as_of - dt.timedelta(days=20)
    walcl_past_state = _series_state(walcl, as_of=past, sid="WALCL", required=1)
    wtreg_past_state = _series_state(wtreg, as_of=past, sid="WTREGEN", required=1)
    rrp_past_state   = _series_state(rrp,   as_of=past, sid="RRPONTSYD", required=1)
    liq_inputs = [
        ("WALCL", walcl, 1),
        ("WTREGEN", wtreg, 1),
        ("RRPONTSYD", rrp, 1),
    ]
    # Promote the worst of (current-day inputs, lookback-day
    # availability) into a single status. If the past series is
    # missing/insufficient, the gate cannot be computed at all.
    liq = _combine(
        "liquidity_expanding",
        inputs=liq_inputs,
        as_of=as_of,
        compute_value=lambda: compute_liquidity_expanding(
            walcl, wtreg, rrp, as_of,
        ),
    )
    # Override liq if any past_20d series is missing/insufficient/stale.
    severity_priority = {
        STATUS_PRODUCTION: 0,
        STATUS_STALE: 1,
        STATUS_INSUFFICIENT: 2,
        STATUS_MISSING: 3,
    }
    past_worst = max(
        (walcl_past_state, wtreg_past_state, rrp_past_state),
        key=lambda st: severity_priority[st[0]],
    )
    if (
        severity_priority[past_worst[0]]
        > severity_priority[liq.status]
    ):
        liq = GateDiagnostic(
            name="liquidity_expanding",
            value=None, status=past_worst[0],
            reason=(
                f"past_20d={past.isoformat()} input lacking: "
                f"{past_worst[1]}"
            ),
            required_obs=1, available_obs=past_worst[2],
            latest_input_date=past_worst[3],
            inputs_used=("WALCL@past", "WTREGEN@past", "RRPONTSYD@past"),
        )

    return {
        "rates_calm":          rates,
        "vrp_supportive":      vrp,
        "credit_stable":       credit,
        "liquidity_expanding": liq,
    }


def business_days(start: dt.date, end: dt.date) -> list[dt.date]:
    return list(pd.bdate_range(start=start, end=end).date)


def persist_features(
    series: dict[str, pd.Series],
    *,
    session_factory=None,
) -> int:
    sf = session_factory or SessionLocal
    total = 0
    with sf() as session:
        version_for = {
            "DGS10":         f"rates_{RATES_FV}",
            "VIXCLS":        f"vol_{VOL_FV}",
            "BAMLH0A0HYM2":  f"credit_{CREDIT_FV}",
            "WALCL":         f"liq_{LIQ_FV}",
            "WTREGEN":       f"liq_{LIQ_FV}",
            "RRPONTSYD":     f"liq_{LIQ_FV}",
        }
        import hashlib
        for sid, s in series.items():
            fv = version_for.get(sid, "macro_v1.0.0")
            for ts, val in s.items():
                d = ts.date() if isinstance(ts, pd.Timestamp) else ts
                input_hash = hashlib.sha256(
                    f"{SOURCE_TAG}:{sid}:{d}:{val}:{fv}".encode("utf-8"),
                ).hexdigest()[:32]
                result = session.execute(_INSERT_FEATURE_SQL, {
                    "as_of_date": d,
                    "feature_name": sid,
                    "value": Decimal(str(val)),
                    "input_hash": input_hash,
                    "feature_version": fv,
                })
                if result.rowcount and result.rowcount > 0:
                    total += 1
        session.commit()
    return total


def persist_context(
    rows: list[tuple[dt.date, str, bool | None] | "GateDiagnostic"],
    *,
    logic_version: str,
    session_factory=None,
) -> int:
    """Phase 11Z — persist gate rows with explicit status.

    Accepts either:
      * `(as_of, name, GateDiagnostic)` triples (new path), OR
      * `(as_of, name, bool|None)` triples (legacy path) — preserved
        for backward-compat with existing call sites and tests.

    The legacy path used to silently coerce `None → False` and tag
    every row `status='production'`. Phase 11Z removes that
    coercion: when a `bool|None` triple is passed and the value is
    `None`, we now persist `status='insufficient_data'` and
    `value_bool=NULL` rather than fabricating a `False`.
    """
    sf = session_factory or SessionLocal
    total = 0
    with sf() as session:
        for row in rows:
            d = row[0]
            name = row[1]
            payload = row[2]
            if isinstance(payload, GateDiagnostic):
                status = payload.status
                value_bool = (
                    payload.value if payload.value is not None else None
                )
            else:
                # Legacy bool|None path. No coercion: None → unknown.
                if payload is None:
                    status = STATUS_INSUFFICIENT
                    value_bool = None
                else:
                    status = STATUS_PRODUCTION
                    value_bool = bool(payload)
            result = session.execute(_INSERT_CONTEXT_SQL, {
                "as_of_date": d,
                "context_name": name,
                "status": status,
                "value_bool": value_bool,
                "source_features": [SOURCE_TAG],
                "logic_version": logic_version,
                "logic_hash": _logic_hash(name, logic_version),
            })
            if result.rowcount and result.rowcount > 0:
                total += 1
        session.commit()
    return total


# ---------------------------------------------------------------------------
# Audit + render
# ---------------------------------------------------------------------------

def _audit_path(
    cfg: BackfillConfig, *, log_dir: Path = JSONL_LOG_DIR,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / (
        f"{JSONL_LOG_PREFIX}"
        f"{cfg.start.isoformat()}_{cfg.end.isoformat()}.jsonl"
    )


def _write_audit(
    cfg: BackfillConfig,
    summary: dict,
    *,
    log_dir: Path = JSONL_LOG_DIR,
) -> Path:
    if not cfg.commit:
        raise RuntimeError("audit log only on commit runs")
    path = _audit_path(cfg, log_dir=log_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, default=str) + "\n")
    return path


def _render_summary(
    cfg: BackfillConfig,
    summary: dict,
) -> str:
    lines: list[str] = []
    lines.append(
        f"[fetch] series={','.join(cfg.series)} "
        f"start={cfg.start} end={cfg.end}"
    )
    for sid, n in summary["fetched_counts"].items():
        lines.append(f"[fetch] {sid:<14} {n} rows")
    lines.append(f"[align] business-day index {summary['n_business_days']} days")
    for name in (
        "rates_calm", "vrp_supportive", "credit_stable",
        "liquidity_expanding",
    ):
        agg = summary["gate_aggregates"][name]
        lines.append(
            f"[compute] {name:<22} "
            f"true={agg['true']:>4} "
            f"({agg['pct']:>5.1f}%)"
        )
    pass_dist = summary["all_pass_distribution"]
    lines.append(
        f"[compute] all-4-pass            true={pass_dist['n_4']:>4}"
    )
    lines.append(
        f"[compute] >=2-pass              true={pass_dist['n_ge2']:>4}"
    )
    label = (
        "DRY-RUN -- no DB writes"
        if cfg.dry_run else
        "COMMIT -- writes complete"
    )
    lines.append("")
    lines.append(label)
    if summary.get("samples"):
        lines.append("sample (last 5 business days):")
        def _glyph(v: bool | None) -> str:
            if v is True:
                return "T"
            if v is False:
                return "F"
            return "U"  # Phase 11Z — value is None, status non-production
        for row in summary["samples"]:
            lines.append(
                f" {row['as_of_date']}  "
                f"rates={_glyph(row.get('rates_calm'))} "
                f"vrp={_glyph(row.get('vrp_supportive'))} "
                f"credit={_glyph(row.get('credit_stable'))} "
                f"liq={_glyph(row.get('liquidity_expanding'))}  "
                f"({row.get('n_pass', 0)}/4 pass)"
            )
    if cfg.dry_run:
        lines.append("")
        lines.append(
            "next step: re-run with --commit --confirm-commit YES"
        )
    if cfg.commit:
        lines.append(
            f"[persist] features_daily inserted="
            f"{summary['n_features_inserted']}"
        )
        lines.append(
            f"[persist] context_daily inserted="
            f"{summary['n_context_inserted']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(
    cfg: BackfillConfig,
    *,
    adapter: FredAdapter | None = None,
    session_factory=None,
    audit_log_dir: Path | None = None,
) -> dict:
    own_adapter = adapter is None
    adp = adapter or FredAdapter()

    try:
        try:
            # Phase 11Z — fetch from `cfg.fetch_start` (= cfg.start −
            # lookback_days) so single-day reruns still pull enough
            # history for every gate compute fn. Persistence is
            # still bounded by [cfg.start, cfg.end].
            series = fetch_all_series(
                adp, series=cfg.series,
                start=cfg.fetch_start, end=cfg.end,
            )
        except (FredUnavailable, FredAPIError) as exc:
            raise RuntimeError(f"[ingest] {exc}") from exc

        spy = load_spy_close(
            cfg.fetch_start, cfg.end, session_factory=session_factory,
        )
        days = business_days(cfg.start, cfg.end)

        per_day_gates: list[dict] = []
        agg = {
            "rates_calm":          [0, 0],
            "vrp_supportive":      [0, 0],
            "credit_stable":       [0, 0],
            "liquidity_expanding": [0, 0],
        }
        unknown_agg = {
            "rates_calm":          [0, 0],
            "vrp_supportive":      [0, 0],
            "credit_stable":       [0, 0],
            "liquidity_expanding": [0, 0],
        }
        n4 = 0
        nge2 = 0
        per_day_diagnostics: list[dict[str, GateDiagnostic]] = []
        for d in days:
            gate_diags = compute_gates_with_diagnostics(
                series, spy, as_of=d,
            )
            per_day_diagnostics.append(gate_diags)
            n_pass = 0
            for name, gd in gate_diags.items():
                agg[name][1] += 1
                unknown_agg[name][1] += 1
                if gd.value is True:
                    agg[name][0] += 1
                    n_pass += 1
                if gd.status != STATUS_PRODUCTION:
                    unknown_agg[name][0] += 1
            if n_pass == 4:
                n4 += 1
            if n_pass >= 2:
                nge2 += 1
            per_day_gates.append({
                "as_of_date": d.isoformat(),
                **{name: gd.value for name, gd in gate_diags.items()},
                "n_pass": n_pass,
                "diagnostics": {
                    name: {
                        "status": gd.status,
                        "reason": gd.reason,
                        "required_obs": gd.required_obs,
                        "available_obs": gd.available_obs,
                        "latest_input_date": (
                            gd.latest_input_date.isoformat()
                            if gd.latest_input_date else None
                        ),
                    }
                    for name, gd in gate_diags.items()
                },
            })

        n_features_inserted = 0
        n_context_inserted = 0
        if cfg.commit:
            n_features_inserted = persist_features(
                series, session_factory=session_factory,
            )
            ctx_rows: list[tuple[dt.date, str, GateDiagnostic]] = []
            for d, gate_diags in zip(days, per_day_diagnostics):
                for name in (
                    "rates_calm", "vrp_supportive", "credit_stable",
                    "liquidity_expanding",
                ):
                    ctx_rows.append((d, name, gate_diags[name]))
            n_context_inserted = persist_context(
                ctx_rows, logic_version=cfg.logic_version,
                session_factory=session_factory,
            )

        summary = {
            "config": {
                "start": cfg.start.isoformat(),
                "end": cfg.end.isoformat(),
                "fetch_start": cfg.fetch_start.isoformat(),
                "lookback_days": int(cfg.lookback_days),
                "series": list(cfg.series),
                "logic_version": cfg.logic_version,
                "commit": cfg.commit,
            },
            "fetched_counts": {sid: int(len(s)) for sid, s in series.items()},
            "spy_fetched": int(len(spy)),
            "n_business_days": len(days),
            "gate_aggregates": {
                name: {
                    "true": agg[name][0],
                    "total": agg[name][1],
                    "pct":
                        (100.0 * agg[name][0] / agg[name][1])
                        if agg[name][1] > 0 else 0.0,
                }
                for name in agg
            },
            "unknown_aggregates": {
                name: {
                    "unknown": unknown_agg[name][0],
                    "total": unknown_agg[name][1],
                    "pct":
                        (100.0 * unknown_agg[name][0] / unknown_agg[name][1])
                        if unknown_agg[name][1] > 0 else 0.0,
                }
                for name in unknown_agg
            },
            "all_pass_distribution": {"n_4": n4, "n_ge2": nge2},
            "samples": per_day_gates[-5:],
            "n_features_inserted": n_features_inserted,
            "n_context_inserted": n_context_inserted,
        }

        if cfg.commit:
            _write_audit(
                cfg, summary,
                log_dir=(audit_log_dir or JSONL_LOG_DIR),
            )
        return summary
    finally:
        if own_adapter:
            adp.close()


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = _parse_args(raw)

    commit = bool(args.commit)
    dry_run = not commit

    if commit and not _confirm(args):
        sys.stderr.write(
            "commit confirmation required: pass --confirm-commit YES "
            "or type YES at the interactive prompt\n"
        )
        return 2

    try:
        cfg = BackfillConfig(
            start=args.start, end=args.end,
            series=tuple(args.series),
            dry_run=dry_run, commit=commit,
            logic_version=args.logic_version,
            explain=bool(args.explain),
            lookback_days=int(args.lookback_days),
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        adapter = FredAdapter()
    except FredConfigError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    try:
        summary = run(cfg, adapter=adapter)
    except (FredUnavailable, FredAPIError, RuntimeError) as exc:
        sys.stderr.write(f"[fetch] {exc}\n")
        return 3
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9
    finally:
        adapter.close()

    if summary["n_business_days"] == 0:
        sys.stdout.write("no business days in window\n")
        return 4

    sys.stdout.write(_render_summary(cfg, summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
