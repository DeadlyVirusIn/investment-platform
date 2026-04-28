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

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError(
                "dry_run and commit are mutually exclusive"
            )
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if not self.series:
            raise ValueError("series must be non-empty")


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
    ON CONFLICT DO NOTHING
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
    rows: list[tuple[dt.date, str, bool | None]],
    *,
    logic_version: str,
    session_factory=None,
) -> int:
    sf = session_factory or SessionLocal
    total = 0
    with sf() as session:
        for d, name, val in rows:
            if val is None:
                status = "missing_data"
                value_bool = False
            else:
                status = "ok"
                value_bool = bool(val)
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
        for row in summary["samples"]:
            lines.append(
                f" {row['as_of_date']}  "
                f"rates={'T' if row.get('rates_calm') else 'F'} "
                f"vrp={'T' if row.get('vrp_supportive') else 'F'} "
                f"credit={'T' if row.get('credit_stable') else 'F'} "
                f"liq={'T' if row.get('liquidity_expanding') else 'F'}  "
                f"({row.get('n_pass', 0)}/4)"
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
            series = fetch_all_series(
                adp, series=cfg.series, start=cfg.start, end=cfg.end,
            )
        except (FredUnavailable, FredAPIError) as exc:
            raise RuntimeError(f"[ingest] {exc}") from exc

        spy = load_spy_close(
            cfg.start, cfg.end, session_factory=session_factory,
        )
        days = business_days(cfg.start, cfg.end)

        per_day_gates: list[dict] = []
        agg = {
            "rates_calm":          [0, 0],
            "vrp_supportive":      [0, 0],
            "credit_stable":       [0, 0],
            "liquidity_expanding": [0, 0],
        }
        n4 = 0
        nge2 = 0
        for d in days:
            gates = compute_gates_for_day(series, spy, as_of=d)
            n_pass = 0
            for name, val in gates.items():
                agg[name][1] += 1
                if val is True:
                    agg[name][0] += 1
                    n_pass += 1
            if n_pass == 4:
                n4 += 1
            if n_pass >= 2:
                nge2 += 1
            per_day_gates.append({
                "as_of_date": d.isoformat(),
                **gates,
                "n_pass": n_pass,
            })

        n_features_inserted = 0
        n_context_inserted = 0
        if cfg.commit:
            n_features_inserted = persist_features(
                series, session_factory=session_factory,
            )
            ctx_rows: list[tuple[dt.date, str, bool | None]] = []
            for row in per_day_gates:
                d = dt.date.fromisoformat(row["as_of_date"])
                for name in (
                    "rates_calm", "vrp_supportive", "credit_stable",
                    "liquidity_expanding",
                ):
                    ctx_rows.append((d, name, row.get(name)))
            n_context_inserted = persist_context(
                ctx_rows, logic_version=cfg.logic_version,
                session_factory=session_factory,
            )

        summary = {
            "config": {
                "start": cfg.start.isoformat(),
                "end": cfg.end.isoformat(),
                "series": list(cfg.series),
                "logic_version": cfg.logic_version,
                "commit": cfg.commit,
            },
            "fetched_counts": {sid: int(len(s)) for sid, s in series.items()},
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
