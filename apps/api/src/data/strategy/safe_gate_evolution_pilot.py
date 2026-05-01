"""Phase 11X.2 — controlled paper-only pilot execution path.

Reads the existing `safe_gate_evolution_shadow` diagnostic + extra
production-state checks; if every condition holds AND the
`SAFE_GATE_EVOLUTION_PILOT_EXECUTION` flag is True, opens **one**
paper trade at a frozen 0.25× size for that day.

Hard guarantees:
  * **Paper trade table only.** Never touches broker, options,
    or live execution. Never writes `paper_position` directly —
    only inserts a `paper_trade` row tagged in its `reason` field
    so the existing position aggregation still works without
    schema changes.
  * **Feature-flagged off by default.** Setting
    `SAFE_GATE_EVOLUTION_PILOT_EXECUTION=false` (the default)
    short-circuits before any DB write.
  * **Idempotent on `(run_date)`.** Detects an already-open pilot
    trade for the day and refuses to double-fire.
  * **Strategy unchanged.** Reads existing `safe_gate_evolution_shadow`
    rows produced by the unmodified Phase 11X evaluator. Reads
    existing `context_daily` rows produced by the Phase 11Z
    backfill. Production selector logic / engine A / engine B /
    macro thresholds / candidate scoring NOT touched.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings


PILOT_REASON_PREFIX = "safe_gate_evolution_pilot"
PRODUCTION_GATE_NAMES = (
    "rates_calm", "vrp_supportive",
    "credit_stable", "liquidity_expanding",
)


@dataclass(frozen=True)
class PilotEligibility:
    """Per-day eligibility evaluation. Pure data."""
    run_date: dt.date
    eligible: bool
    reason: str
    macro_favorable: int
    unknown_count: int
    shadow_would_trade: bool
    shadow_symbol: str | None
    shadow_score: Decimal | None
    shadow_confidence: Decimal | None
    production_fired: bool
    pilot_already_opened: bool
    price_regime_favorable: bool


@dataclass(frozen=True)
class PilotExecutionResult:
    """Outcome of a `evaluate_and_execute_pilot` call."""
    run_date: dt.date
    flag_enabled: bool
    eligibility: PilotEligibility
    opened: bool
    paper_trade_id: str | None
    symbol: str | None
    side: str | None
    quantity: Decimal | None
    fill_price: Decimal | None
    size_multiplier: Decimal
    notional_usd: Decimal | None
    reason: str


# ---------------------------------------------------------------------------
# Read helpers — pure SELECTs
# ---------------------------------------------------------------------------


def _read_macro_status(
    session: Session, run_date: dt.date,
) -> tuple[int, int, dict[str, str]]:
    """Returns (favorable_count, unknown_count, status_by_name).
    Mirrors the Phase 11Z accounting: only `production` rows can
    contribute T/F; `insufficient_data`/`missing_data`/`stale_data`
    rows count as `unknown`."""
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (context_name)
                   context_name, status, value_bool
            FROM context_daily
            WHERE context_name = ANY(:names)
              AND as_of_date <= :d
            ORDER BY context_name, as_of_date DESC
            """
        ),
        {"names": list(PRODUCTION_GATE_NAMES), "d": run_date},
    ).all()
    favorable = 0
    unknown = 0
    statuses: dict[str, str] = {}
    for r in rows:
        statuses[r.context_name] = r.status
        if r.status == "production":
            if r.value_bool is True:
                favorable += 1
        else:
            unknown += 1
    return favorable, unknown, statuses


def _read_shadow(
    session: Session, run_date: dt.date,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT would_trade, symbol, composite_score, confidence,
                   macro_favorable_count, shadow_reason, price_regime
            FROM safe_gate_evolution_shadow
            WHERE run_date = :d
            ORDER BY created_at DESC LIMIT 1
            """
        ),
        {"d": run_date},
    ).mappings().first()
    return dict(row) if row else None


def _production_fired(
    session: Session, run_date: dt.date,
) -> bool:
    """Same logic as the Phase 11X shadow uses to detect production
    activity. Resilient to the test schema not materializing
    paper_trade_log."""
    from sqlalchemy.exc import ProgrammingError

    n_strict = 0
    n_auto = 0
    try:
        n_strict = int(session.execute(
            text(
                "SELECT count(*) FROM paper_trade_log "
                "WHERE entry_date = :d AND action IN ('Buy','BUY','OPEN')"
            ),
            {"d": run_date},
        ).scalar_one() or 0)
    except ProgrammingError:
        session.rollback()
    try:
        n_auto = int(session.execute(
            text(
                "SELECT count(*) FROM paper_trade "
                "WHERE fill_ts::date = :d AND side = 'buy' "
                "AND COALESCE(reason,'') NOT LIKE :pilot_prefix"
            ),
            {
                "d": run_date,
                "pilot_prefix": f"{PILOT_REASON_PREFIX}%",
            },
        ).scalar_one() or 0)
    except ProgrammingError:
        session.rollback()
    return n_strict > 0 or n_auto > 0


def _pilot_already_opened(
    session: Session, run_date: dt.date,
) -> bool:
    """Did this pilot path already open a trade today?"""
    n = int(session.execute(
        text(
            "SELECT count(*) FROM paper_trade "
            "WHERE fill_ts::date = :d "
            "AND COALESCE(reason,'') LIKE :pilot_prefix"
        ),
        {
            "d": run_date,
            "pilot_prefix": f"{PILOT_REASON_PREFIX}%",
        },
    ).scalar_one() or 0)
    return n > 0


def _resolve_fill_price(
    session: Session, *, symbol: str, run_date: dt.date,
) -> Decimal | None:
    """Most recent close at or before run_date for `symbol`. Read-only."""
    row = session.execute(
        text(
            """
            SELECT pb.adjusted_close, pb.close
            FROM price_bar pb JOIN asset a ON a.id = pb.asset_id
            WHERE a.symbol = :sym
              AND pb.timeframe = '1d'
              AND pb.ts::date <= :d
            ORDER BY pb.ts DESC LIMIT 1
            """
        ),
        {"sym": symbol, "d": run_date},
    ).mappings().first()
    if not row:
        return None
    px = row["adjusted_close"] or row["close"]
    return Decimal(px) if px is not None else None


def _portfolio_id(session: Session) -> str | None:
    row = session.execute(
        text("SELECT id FROM paper_portfolio ORDER BY id LIMIT 1")
    ).first()
    return str(row[0]) if row else None


def _asset_id(session: Session, symbol: str) -> str | None:
    row = session.execute(
        text("SELECT id FROM asset WHERE symbol = :s LIMIT 1"),
        {"s": symbol},
    ).first()
    return str(row[0]) if row else None


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def _price_regime_favorable_from_shadow(shadow: dict[str, Any]) -> bool:
    pr = shadow.get("price_regime") or {}
    if isinstance(pr, str):
        try:
            pr = json.loads(pr)
        except Exception:  # noqa: BLE001
            pr = {}
    return (
        pr.get("market_trend") == "uptrend"
        and pr.get("vol_regime") in ("low", "normal")
        and bool(pr.get("sma50_above_sma200"))
    )


def evaluate_eligibility(
    session: Session, run_date: dt.date,
) -> PilotEligibility:
    """Evaluate every gating condition. Read-only."""
    favorable, unknown, _statuses = _read_macro_status(session, run_date)
    shadow = _read_shadow(session, run_date)
    prod_fired = _production_fired(session, run_date)
    already = _pilot_already_opened(session, run_date)

    base = dict(
        run_date=run_date,
        macro_favorable=favorable,
        unknown_count=unknown,
        production_fired=prod_fired,
        pilot_already_opened=already,
        shadow_would_trade=bool(shadow and shadow.get("would_trade")),
        shadow_symbol=(shadow or {}).get("symbol"),
        shadow_score=(shadow or {}).get("composite_score"),
        shadow_confidence=(shadow or {}).get("confidence"),
        price_regime_favorable=(
            _price_regime_favorable_from_shadow(shadow) if shadow else False
        ),
    )

    if shadow is None:
        return PilotEligibility(
            **base, eligible=False,
            reason="no_shadow_row_for_run_date",
        )
    if not shadow.get("would_trade"):
        return PilotEligibility(
            **base, eligible=False,
            reason=f"shadow_blocked:{shadow.get('shadow_reason')}",
        )
    if favorable < int(settings.SAFE_GATE_EVOLUTION_PILOT_MIN_MACRO_FAVORABLE):
        return PilotEligibility(
            **base, eligible=False,
            reason=(
                f"macro_favorable<{settings.SAFE_GATE_EVOLUTION_PILOT_MIN_MACRO_FAVORABLE}"
            ),
        )
    if unknown > 0:
        return PilotEligibility(
            **base, eligible=False,
            reason=f"unknown_macro_gates_present:{unknown}",
        )
    if not _price_regime_favorable_from_shadow(shadow):
        return PilotEligibility(
            **base, eligible=False,
            reason="price_regime_unfavorable",
        )
    if prod_fired:
        return PilotEligibility(
            **base, eligible=False,
            reason="production_trade_already_opened",
        )
    if already:
        return PilotEligibility(
            **base, eligible=False,
            reason="pilot_trade_already_opened",
        )
    return PilotEligibility(
        **base, eligible=True,
        reason="all_conditions_met",
    )


# ---------------------------------------------------------------------------
# Execution — paper-only writer
# ---------------------------------------------------------------------------


def _build_pilot_reason(
    *, eligibility: PilotEligibility, size_multiplier: Decimal,
) -> str:
    parts = [
        PILOT_REASON_PREFIX,
        f"size_mult={size_multiplier}",
        f"macro_fav={eligibility.macro_favorable}",
        f"shadow_score={eligibility.shadow_score}",
        f"shadow_conf={eligibility.shadow_confidence}",
    ]
    return ":".join(parts)


def _open_paper_trade(
    session: Session, *,
    portfolio_id: str, asset_id: str,
    quantity: Decimal, fill_price: Decimal,
    fill_ts: dt.datetime,
    reason: str,
) -> str:
    """Single paper_trade INSERT. Idempotent in caller via the
    `_pilot_already_opened` precheck above. Returns row id."""
    trade_id = str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO paper_trade
              (id, portfolio_id, asset_id, side, quantity,
               fill_price, fill_ts, submitted_at, reason,
               recommendation_id, realized_pnl, slippage_bps,
               commission, created_at)
            VALUES
              (:id, :pid, :aid, 'buy', :qty,
               :px, :ts, :ts, :reason,
               NULL, NULL, NULL,
               0, now())
            """
        ),
        {
            "id": trade_id, "pid": portfolio_id, "aid": asset_id,
            "qty": quantity, "px": fill_price, "ts": fill_ts,
            "reason": reason,
        },
    )
    session.commit()
    return trade_id


def evaluate_and_execute_pilot(
    session: Session, run_date: dt.date,
    *, fill_ts: dt.datetime | None = None,
    flag_override: bool | None = None,
) -> PilotExecutionResult:
    """Single entry point. Evaluates eligibility, then executes the
    paper trade IFF the flag is on. `flag_override` is for tests
    only — production callers must rely on the env-driven flag."""
    flag_on = (
        flag_override if flag_override is not None
        else bool(settings.SAFE_GATE_EVOLUTION_PILOT_EXECUTION)
    )
    eligibility = evaluate_eligibility(session, run_date)
    size_mult = Decimal(str(settings.SAFE_GATE_EVOLUTION_PILOT_SIZE_MULTIPLIER))

    base = dict(
        run_date=run_date, flag_enabled=flag_on, eligibility=eligibility,
        size_multiplier=size_mult,
    )

    if not flag_on:
        return PilotExecutionResult(
            **base, opened=False, paper_trade_id=None,
            symbol=None, side=None, quantity=None, fill_price=None,
            notional_usd=None, reason="pilot_flag_off",
        )
    if not eligibility.eligible:
        return PilotExecutionResult(
            **base, opened=False, paper_trade_id=None,
            symbol=None, side=None, quantity=None, fill_price=None,
            notional_usd=None, reason=f"not_eligible:{eligibility.reason}",
        )

    symbol = eligibility.shadow_symbol
    if not symbol:
        return PilotExecutionResult(
            **base, opened=False, paper_trade_id=None,
            symbol=None, side=None, quantity=None, fill_price=None,
            notional_usd=None,
            reason="not_eligible:shadow_row_missing_symbol",
        )

    portfolio_id = _portfolio_id(session)
    asset_id = _asset_id(session, symbol)
    fill_price = _resolve_fill_price(
        session, symbol=symbol, run_date=run_date,
    )
    if portfolio_id is None or asset_id is None or fill_price is None:
        return PilotExecutionResult(
            **base, opened=False, paper_trade_id=None,
            symbol=symbol, side=None, quantity=None, fill_price=None,
            notional_usd=None,
            reason=(
                f"not_eligible:missing_state:portfolio={portfolio_id is not None},"
                f"asset={asset_id is not None},price={fill_price is not None}"
            ),
        )

    notional_base = Decimal(str(settings.SAFE_GATE_EVOLUTION_PILOT_NOTIONAL_USD))
    notional = (notional_base * size_mult).quantize(Decimal("0.01"))
    raw_qty = (notional / fill_price).quantize(Decimal("0.0000000001"))
    if raw_qty <= 0:
        return PilotExecutionResult(
            **base, opened=False, paper_trade_id=None,
            symbol=symbol, side=None, quantity=None,
            fill_price=fill_price, notional_usd=notional,
            reason="not_eligible:non_positive_quantity",
        )

    fill_ts = fill_ts or dt.datetime.combine(
        run_date, dt.time(20, 0), tzinfo=dt.timezone.utc,
    )
    reason = _build_pilot_reason(
        eligibility=eligibility, size_multiplier=size_mult,
    )
    trade_id = _open_paper_trade(
        session,
        portfolio_id=portfolio_id, asset_id=asset_id,
        quantity=raw_qty, fill_price=fill_price,
        fill_ts=fill_ts, reason=reason,
    )
    logger.info(
        "[safe_gate_pilot] opened paper trade {} {} qty={} @ {} "
        "(size_mult={}, notional=${})",
        symbol, trade_id, raw_qty, fill_price, size_mult, notional,
    )
    return PilotExecutionResult(
        **base, opened=True, paper_trade_id=trade_id,
        symbol=symbol, side="buy", quantity=raw_qty,
        fill_price=fill_price, notional_usd=notional,
        reason=reason,
    )
