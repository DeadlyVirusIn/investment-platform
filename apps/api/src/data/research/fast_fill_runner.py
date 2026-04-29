"""Phase 11R - Fast-fill research runner.

Generates same-day simulated fills for ML label generation. Append-
only. NEVER touches paper_trade / paper_position / decision_log /
paper_portfolio. NEVER imports broker / live / execution modules.

Fill-price selection priority (FROZEN):
  1. VWAP    (when bar has vwap)
  2. CLOSE
  3. OPEN    (only when bar.ts <= decision_ts)

Future bars are forbidden by construction — the runner queries
price_bar with `ts::date = as_of_date` and never beyond.

Idempotency via UNIQUE constraint on
  (source, as_of_date, underlying, rule_id, side, fill_model,
   label_version)
plus INSERT ... ON CONFLICT DO NOTHING.

Operator opt-in: every commit run requires explicit --confirm-commit
YES. Default mode is --dry-run (no DB writes, no audit log).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Frozen constants — DO NOT bump without registry-review.
# ---------------------------------------------------------------------------

SOURCE = "research_fast_fill"
FILL_MODEL = "same_day_research_v1"
LABEL_VERSION = "research-fast-fill-v1.0.0"
DECISION_TS_HOUR_UTC = 15
PRIORITY_ORDER: tuple[str, ...] = ("vwap", "close", "open")
RESEARCH_QTY_PAPER = Decimal("1")
DEFAULT_RULE_ID = "research_fast_fill_open_buy_v1"
DEFAULT_ENGINE = "research"
DEFAULT_SIDE = "BUY"
DEFAULT_UNDERLYINGS: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "GLD", "TLT",
)
DEFAULT_MAX_PER_DAY = 20
HARD_MAX_PER_DAY = 100

JSONL_LOG_DIR = Path("logs")
JSONL_LOG_PREFIX = "research_fast_fill_"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FastFillSafetyError(RuntimeError):
    """Raised on safety-invariant failure."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunnerConfig:
    date: dt.date
    backfill_from: dt.date | None
    underlyings: tuple[str, ...]
    max_per_day: int
    label_version: str
    dry_run: bool
    commit: bool
    explain: bool
    skip_context: bool

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError(
                "dry_run and commit are mutually exclusive"
            )
        if not (1 <= self.max_per_day <= HARD_MAX_PER_DAY):
            raise ValueError(
                f"max_per_day out of bounds 1..{HARD_MAX_PER_DAY}: "
                f"{self.max_per_day}"
            )
        if not self.underlyings:
            raise ValueError("underlyings must be non-empty")
        if (
            self.backfill_from is not None
            and self.backfill_from > self.date
        ):
            raise ValueError("backfill_from must be <= date")


@dataclass(frozen=True)
class FillCandidate:
    fill_price: Decimal
    fill_price_source: str
    fill_ts: dt.datetime


@dataclass(frozen=True)
class PlannedFill:
    decision_ts: dt.datetime
    as_of_date: dt.date
    underlying: str
    asset_id: str | None
    rule_id: str
    engine: str
    side: str
    qty: Decimal
    fill_price: Decimal | None
    fill_price_source: str | None
    fill_ts: dt.datetime | None
    gate_snapshot: dict
    failed_gates: tuple[str, ...]
    skipped: bool
    skip_reason: str | None


@dataclass(frozen=True)
class RunnerSummary:
    config: RunnerConfig
    n_days: int
    n_candidates: int
    n_filled: int
    n_skipped_no_bar: int
    n_committed: int
    n_skipped_existing: int
    audit_log_path: str | None


# ---------------------------------------------------------------------------
# Pure-fn fill selection
# ---------------------------------------------------------------------------

def select_same_day_fill_price(
    bars_for_day: Sequence[dict],
    *,
    decision_ts: dt.datetime,
) -> FillCandidate | None:
    """Pick a same-day fill price following frozen priority order.

    `bars_for_day` is a list of dicts with keys at minimum:
        ts:       datetime (UTC, the bar's anchor timestamp)
        open:     Decimal | None
        close:    Decimal | None
        vwap:     Decimal | None  (optional — None when not provided)

    Rules (frozen):
      1. VWAP if any bar has a non-null vwap → use the FIRST bar's vwap
      2. else CLOSE → use the LAST bar's close
      3. else OPEN → use the FIRST bar's open BUT ONLY if its ts is
         <= decision_ts. Future bars are forbidden by construction.

    Returns None when no valid price is available.
    """
    if not bars_for_day:
        return None

    # Dedup + sort defensively. Caller should already supply same-day.
    bars = sorted(
        [b for b in bars_for_day if b is not None],
        key=lambda b: b["ts"],
    )
    if not bars:
        return None

    # Hard guard: NEVER use a bar with ts > decision_ts for any source
    # other than CLOSE/VWAP that represents the *whole* day. We allow
    # VWAP and CLOSE because they are aggregates anchored to the trading
    # day; we only restrict OPEN explicitly. (Future-day bars cannot
    # appear here because the SQL caller filters ts::date = as_of_date.)

    # 1. VWAP
    for b in bars:
        v = b.get("vwap")
        if v is not None:
            return FillCandidate(
                fill_price=Decimal(str(v)),
                fill_price_source="vwap",
                fill_ts=b["ts"],
            )

    # 2. CLOSE — use the latest same-day bar
    last = bars[-1]
    cv = last.get("close")
    if cv is not None:
        return FillCandidate(
            fill_price=Decimal(str(cv)),
            fill_price_source="close",
            fill_ts=last["ts"],
        )

    # 3. OPEN — only if the bar's ts is <= decision_ts
    first = bars[0]
    ov = first.get("open")
    if ov is not None and first["ts"] <= decision_ts:
        return FillCandidate(
            fill_price=Decimal(str(ov)),
            fill_price_source="open",
            fill_ts=first["ts"],
        )

    return None


def business_days_in_window(
    cfg: RunnerConfig,
) -> list[dt.date]:
    start = cfg.backfill_from or cfg.date
    end = cfg.date
    out: list[dt.date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def decision_ts_for(date: dt.date) -> dt.datetime:
    return dt.datetime(
        date.year, date.month, date.day,
        DECISION_TS_HOUR_UTC, 0,
        tzinfo=dt.timezone.utc,
    )


# ---------------------------------------------------------------------------
# DB read helpers (read-only)
# ---------------------------------------------------------------------------

def _read_same_day_bars(
    session: Session, *, symbol: str, day: dt.date,
) -> list[dict]:
    """Read all 1d price_bar rows for (symbol, day). NEVER queries a
    future date — the WHERE clause restricts to the as_of date only."""
    rows = session.execute(text(
        """
        SELECT pb.ts AS ts, pb.open AS open, pb.close AS close,
               pb.adjusted_close AS adjusted_close, pb.asset_id AS asset_id
        FROM price_bar pb
        JOIN asset a ON a.id = pb.asset_id
        WHERE a.symbol = :sym
          AND pb.timeframe = '1d'
          AND pb.ts::date = :day
        ORDER BY pb.ts
        """
    ), {"sym": symbol, "day": day}).all()
    out: list[dict] = []
    for r in rows:
        out.append({
            "ts": r.ts,
            "open": r.open,
            "close": r.close,
            # `price_bar` schema in this codebase has no vwap column;
            # leave vwap=None so the priority logic falls through to
            # CLOSE. When the operator's price feed exposes VWAP later,
            # it can be wired in by extending the SELECT here.
            "vwap": None,
            "asset_id": str(r.asset_id) if r.asset_id else None,
        })
    return out


def _read_asset_id(
    session: Session, *, symbol: str,
) -> str | None:
    row = session.execute(text(
        "SELECT id FROM asset WHERE symbol = :sym LIMIT 1"
    ), {"sym": symbol}).first()
    return str(row[0]) if row and row[0] else None


def _read_context_for_day(
    session: Session, *, day: dt.date,
) -> tuple[dict, list[str]]:
    """Optional read-only snapshot of the four production gates for a
    day. Empty dict + empty failed list when --skip-context."""
    rows = session.execute(text(
        """
        SELECT context_name, value_bool, status
        FROM context_daily
        WHERE as_of_date = :d
          AND context_name IN (
            'rates_calm','vrp_supportive',
            'credit_stable','liquidity_expanding'
          )
        """
    ), {"d": day}).all()
    snapshot: dict = {}
    failed: list[str] = []
    expected = {
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    }
    for r in rows:
        if r.status == "missing_data":
            snapshot[r.context_name] = None
        else:
            snapshot[r.context_name] = bool(r.value_bool)
    for name in sorted(expected):
        if snapshot.get(name) is not True:
            failed.append(name)
    return snapshot, failed


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_plan_for_day(
    session: Session,
    *,
    day: dt.date,
    underlyings: Sequence[str],
    skip_context: bool,
    cap: int,
) -> list[PlannedFill]:
    decision_ts = decision_ts_for(day)
    if skip_context:
        gate_snapshot: dict = {}
        failed_gates: tuple[str, ...] = ()
    else:
        snap, failed = _read_context_for_day(session, day=day)
        gate_snapshot = snap
        failed_gates = tuple(failed)

    out: list[PlannedFill] = []
    for sym in underlyings:
        if len(out) >= cap:
            break
        bars = _read_same_day_bars(session, symbol=sym, day=day)
        candidate = select_same_day_fill_price(
            bars, decision_ts=decision_ts,
        )
        asset_id = (
            bars[0]["asset_id"] if bars else None
        ) or _read_asset_id(session, symbol=sym)
        if candidate is None:
            out.append(PlannedFill(
                decision_ts=decision_ts,
                as_of_date=day,
                underlying=sym,
                asset_id=asset_id,
                rule_id=DEFAULT_RULE_ID,
                engine=DEFAULT_ENGINE,
                side=DEFAULT_SIDE,
                qty=RESEARCH_QTY_PAPER,
                fill_price=None,
                fill_price_source=None,
                fill_ts=None,
                gate_snapshot=gate_snapshot,
                failed_gates=failed_gates,
                skipped=True,
                skip_reason="no_same_day_bar",
            ))
            continue
        out.append(PlannedFill(
            decision_ts=decision_ts,
            as_of_date=day,
            underlying=sym,
            asset_id=asset_id,
            rule_id=DEFAULT_RULE_ID,
            engine=DEFAULT_ENGINE,
            side=DEFAULT_SIDE,
            qty=RESEARCH_QTY_PAPER,
            fill_price=candidate.fill_price,
            fill_price_source=candidate.fill_price_source,
            fill_ts=candidate.fill_ts,
            gate_snapshot=gate_snapshot,
            failed_gates=failed_gates,
            skipped=False,
            skip_reason=None,
        ))
    return out


_INSERT_SQL = text(
    """
    INSERT INTO paper_research_fill
      (source, fill_model, label_version,
       ml_label_eligible, strict_fill_model_used,
       decision_ts, as_of_date, underlying, asset_id,
       rule_id, engine, side,
       fill_price, fill_price_source, fill_ts, qty,
       gate_snapshot, failed_gates, audit_jsonl_path)
    VALUES
      (:source, :fill_model, :label_version,
       :ml_eligible, :strict_off,
       :decision_ts, :as_of_date, :underlying, :asset_id,
       :rule_id, :engine, :side,
       :fill_price, :fill_price_source, :fill_ts, :qty,
       CAST(:gate_snapshot AS jsonb), :failed_gates, :audit_jsonl_path)
    ON CONFLICT ON CONSTRAINT uq_paper_research_fill_natural_key
        DO NOTHING
    """
)


def step_commit_fills(
    session: Session,
    fills: Sequence[PlannedFill],
    *,
    label_version: str,
    audit_log_path: str | None,
) -> tuple[int, int]:
    inserted = 0
    skipped_existing = 0
    for f in fills:
        if f.skipped:
            continue
        result = session.execute(_INSERT_SQL, {
            "source": SOURCE,
            "fill_model": FILL_MODEL,
            "label_version": label_version,
            "ml_eligible": True,
            "strict_off": False,
            "decision_ts": f.decision_ts,
            "as_of_date": f.as_of_date,
            "underlying": f.underlying,
            "asset_id": f.asset_id,
            "rule_id": f.rule_id,
            "engine": f.engine,
            "side": f.side,
            "fill_price": f.fill_price,
            "fill_price_source": f.fill_price_source,
            "fill_ts": f.fill_ts,
            "qty": f.qty,
            "gate_snapshot": json.dumps(f.gate_snapshot, default=str),
            "failed_gates": list(f.failed_gates),
            "audit_jsonl_path": audit_log_path,
        })
        if result.rowcount and result.rowcount > 0:
            inserted += 1
        else:
            skipped_existing += 1
    return inserted, skipped_existing


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _audit_path(
    cfg: RunnerConfig, *, log_dir: Path = JSONL_LOG_DIR,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    if cfg.backfill_from and cfg.backfill_from < cfg.date:
        name = (
            f"{JSONL_LOG_PREFIX}{cfg.backfill_from.isoformat()}"
            f"_{cfg.date.isoformat()}.jsonl"
        )
    else:
        name = f"{JSONL_LOG_PREFIX}{cfg.date.isoformat()}.jsonl"
    return log_dir / name


def _write_audit(
    cfg: RunnerConfig,
    fills: Sequence[PlannedFill],
    *,
    log_dir: Path,
) -> Path:
    """Append-only JSONL. Writes one line per planned fill including
    skipped rows so the operator can audit no-bar dates."""
    if not cfg.commit:
        raise RuntimeError("audit log only on commit runs")
    path = _audit_path(cfg, log_dir=log_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "kind": "summary",
            "source": SOURCE,
            "fill_model": FILL_MODEL,
            "label_version": cfg.label_version,
            "as_of_date": cfg.date.isoformat(),
            "backfill_from":
                cfg.backfill_from.isoformat()
                if cfg.backfill_from else None,
            "n_planned": len(fills),
        }) + "\n")
        for plan in fills:
            row = {
                "kind": "skipped_research_fill" if plan.skipped
                        else "research_fill",
                "as_of_date": plan.as_of_date.isoformat(),
                "decision_ts": plan.decision_ts.isoformat(),
                "underlying": plan.underlying,
                "rule_id": plan.rule_id,
                "side": plan.side,
                "fill_price":
                    str(plan.fill_price) if plan.fill_price else None,
                "fill_price_source": plan.fill_price_source,
                "fill_ts":
                    plan.fill_ts.isoformat() if plan.fill_ts else None,
                "skip_reason": plan.skip_reason,
                "gate_snapshot": plan.gate_snapshot,
                "failed_gates": list(plan.failed_gates),
            }
            f.write(json.dumps(row, default=str) + "\n")
    return path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(
    cfg: RunnerConfig,
    *,
    session_factory=None,
    audit_log_dir: Path | None = None,
) -> RunnerSummary:
    # Lazy import — test fixtures often monkeypatch SessionLocal.
    from apps.api.src.db import SessionLocal
    sf = session_factory or SessionLocal

    days = business_days_in_window(cfg)

    n_candidates = 0
    n_filled = 0
    n_skipped_no_bar = 0
    all_planned: list[PlannedFill] = []

    with sf() as session:
        for d in days:
            planned = step_plan_for_day(
                session, day=d,
                underlyings=cfg.underlyings,
                skip_context=cfg.skip_context,
                cap=cfg.max_per_day,
            )
            for p in planned:
                n_candidates += 1
                if p.skipped:
                    n_skipped_no_bar += 1
                else:
                    n_filled += 1
            all_planned.extend(planned)

        n_committed = 0
        n_skipped_existing = 0
        audit_path: str | None = None

        if cfg.commit:
            log_dir = audit_log_dir or JSONL_LOG_DIR
            ap = _write_audit(cfg, all_planned, log_dir=log_dir)
            audit_path = str(ap)
            inserted, dup_skipped = step_commit_fills(
                session, all_planned,
                label_version=cfg.label_version,
                audit_log_path=audit_path,
            )
            session.commit()
            n_committed = inserted
            n_skipped_existing = dup_skipped

    summary = RunnerSummary(
        config=cfg,
        n_days=len(days),
        n_candidates=n_candidates,
        n_filled=n_filled,
        n_skipped_no_bar=n_skipped_no_bar,
        n_committed=n_committed,
        n_skipped_existing=n_skipped_existing,
        audit_log_path=audit_path,
    )
    logger.info(
        "phase 11R fast-fill complete: dry_run={} days={} "
        "candidates={} filled={} skipped_no_bar={} committed={} "
        "skipped_existing={}",
        cfg.dry_run, summary.n_days, summary.n_candidates,
        summary.n_filled, summary.n_skipped_no_bar,
        summary.n_committed, summary.n_skipped_existing,
    )
    return summary
