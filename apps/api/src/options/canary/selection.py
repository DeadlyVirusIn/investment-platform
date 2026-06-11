"""Phase P6B.0 — canary candidate selection + TradeRequest building (read-only).

Replaces the P6A `_load_promotable_requests` seam. Selects promotable
SHORT_PUT_CREDIT_SPREAD candidates for the canary universe, deterministically
ranked, and builds engine TradeRequests priced from the latest chain
snapshot. Pure reads — opens its own short-lived session(s); never mutates.

Gated upstream: the promotion handler only calls this when
OPTIONS_CANARY_ENABLED is true. Filters mirror the funnel skip-reason
taxonomy (universe / strategy / DTE / confidence / chain availability).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.options.canary import positions as pos
from apps.api.src.options.canary.economics import assess_economics
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import TradeRequest
from apps.api.src.options.paper.fills import compute_fill
from apps.api.src.options.paper.strategies import (
    LegSpec,
    compute_risk,
    net_credit_dollars,
)

STRATEGY_VERSION = "canary-v1"


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def effective_age_seconds(
    snapshot_at_utc: dt.datetime,
    stored_quote_age_seconds: int,
    now: dt.datetime,
) -> int:
    """P6D.34A — age of a rehydrated quote RIGHT NOW.

    (now − snapshot_at_utc) + stored age. The stored quote_age_seconds is
    the provider-reported age AT INGESTION (~0), so on its own it hides
    hours of staleness. Clock-skew safe: never negative (snapshot_at_utc in
    the future clamps the elapsed term to 0). Naive timestamps = UTC.
    """
    if snapshot_at_utc.tzinfo is None:
        snapshot_at_utc = snapshot_at_utc.replace(tzinfo=dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    elapsed = (now - snapshot_at_utc).total_seconds()
    if elapsed < 0:
        elapsed = 0.0
    age = int(elapsed) + max(int(stored_quote_age_seconds or 0), 0)
    return age if age >= 0 else 0


def latest_chain_quotes(
    session: Session, symbols: list[str],
    now: dt.datetime | None = None,
) -> dict[str, OptionChainQuote]:
    """Latest snapshot row per option_symbol → OptionChainQuote. Symbols
    absent from the chain are simply omitted (caller treats as unpriced).

    P6D.34A: every rehydrated quote carries effective_age_seconds (true age
    vs `now`); evaluate_quote prefers it over the stored-at-ingest age."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    syms = sorted({s for s in symbols if s})
    if not syms:
        return {}
    rows = session.execute(text(
        """
        SELECT DISTINCT ON (option_symbol)
               option_symbol, snapshot_at_utc, underlying, expiry, strike,
               option_type, bid, ask, mid, last, volume, open_interest,
               delta, gamma, theta, vega, iv, quote_age_seconds,
               provider, provider_version
        FROM options_chain_snapshot
        WHERE option_symbol = ANY(:syms)
        ORDER BY option_symbol, snapshot_at_utc DESC
        """
    ), {"syms": syms}).mappings().all()
    out: dict[str, OptionChainQuote] = {}
    for r in rows:
        out[r["option_symbol"]] = OptionChainQuote(
            snapshot_at_utc=r["snapshot_at_utc"], underlying=r["underlying"],
            expiry=r["expiry"], strike=_dec(r["strike"]),
            option_type=r["option_type"], option_symbol=r["option_symbol"],
            bid=_dec(r["bid"]), ask=_dec(r["ask"]), mid=_dec(r["mid"]),
            last=_dec(r["last"]), volume=r["volume"],
            open_interest=r["open_interest"], delta=_dec(r["delta"]),
            gamma=_dec(r["gamma"]), theta=_dec(r["theta"]), vega=_dec(r["vega"]),
            iv=_dec(r["iv"]),
            quote_age_seconds=int(r["quote_age_seconds"] or 0),
            provider=r["provider"], provider_version=r["provider_version"],
            effective_age_seconds=effective_age_seconds(
                r["snapshot_at_utc"], int(r["quote_age_seconds"] or 0), now,
            ),
        )
    return out


# P6D.36B — settlement fallback window. A weekend/holiday expiry settles
# with the last trading-day close strictly before expiry, but never one
# older than this many calendar days (covers Sat/Sun + a long-weekend
# holiday; anything older is the wrong settlement context → HOLD).
SETTLEMENT_MAX_AGE_DAYS = 4


def settlement_price(
    session: Session, underlying: str, *,
    expiry: dt.date, as_of: dt.datetime,
) -> Decimal | None:
    """Settlement close for `underlying` at `expiry` (P6D.36B).

    Rule (date-correct — never "latest close, whatever the day"):
      1. EXACT — the 1d price_bar dated the expiry date.
      2. FALLBACK — only once `as_of` is PAST the expiry date (so an
         expiry-day bar had a full chance to ingest): the latest 1d bar
         STRICTLY BEFORE expiry, at most SETTLEMENT_MAX_AGE_DAYS old.
         This is the weekend/holiday-expiry path.
      3. None — no valid settlement context; the caller must HOLD the
         position and retry next lifecycle cycle.
    """
    v = session.execute(text(
        "SELECT pb.close FROM price_bar pb JOIN asset a ON a.id = pb.asset_id "
        "WHERE a.symbol = :s AND pb.timeframe = '1d' "
        "AND (pb.ts AT TIME ZONE 'UTC')::date = :exp "
        "ORDER BY pb.ts DESC LIMIT 1"
    ), {"s": underlying, "exp": expiry}).scalar()
    if v is not None:
        return _dec(v)
    if as_of.date() <= expiry:
        # Same-day cycle: the expiry-day bar may simply not be ingested
        # yet — do NOT settle with a prior day's close.
        return None
    floor = expiry - dt.timedelta(days=SETTLEMENT_MAX_AGE_DAYS)
    v = session.execute(text(
        "SELECT pb.close FROM price_bar pb JOIN asset a ON a.id = pb.asset_id "
        "WHERE a.symbol = :s AND pb.timeframe = '1d' "
        "AND (pb.ts AT TIME ZONE 'UTC')::date < :exp "
        "AND (pb.ts AT TIME ZONE 'UTC')::date >= :floor "
        "ORDER BY pb.ts DESC LIMIT 1"
    ), {"s": underlying, "exp": expiry, "floor": floor}).scalar()
    return _dec(v)


def _candidate_legs(session: Session, candidate_id: int) -> list[dict]:
    rows = session.execute(text(
        """
        SELECT role, side, option_type, strike, expiry, option_symbol, entry_mid
        FROM options_candidate_leg
        WHERE candidate_id = :cid
        ORDER BY role
        """
    ), {"cid": candidate_id}).mappings().all()
    return [dict(r) for r in rows]


def _build_request(
    *, underlying: str, strategy: str, legs_rows: list[dict],
    quotes: dict[str, OptionChainQuote],
) -> TradeRequest:
    legs = tuple(
        LegSpec(
            side=r["side"], option_type=r["option_type"],
            strike=Decimal(str(r["strike"])), expiry=r["expiry"],
            qty=1, option_symbol=r["option_symbol"],
        )
        for r in legs_rows
    )
    quotes_by_symbol = {r["option_symbol"]: quotes[r["option_symbol"]]
                        for r in legs_rows}
    return TradeRequest(
        underlying=underlying, strategy_name=strategy,
        strategy_version=STRATEGY_VERSION, legs=legs,
        quotes_by_symbol=quotes_by_symbol,
    )


def _load_promotable_requests(
    *, portfolio_id, run_date, session_factory,
    now: dt.datetime | None = None,
):
    """Ranked, eligible (TradeRequest, proposal_hash) pairs for the canary.

    Filters: universe + strategy + DTE window + confidence + all legs priced
    in the latest chain. Deterministic order: confidence desc, composite desc,
    id asc. Liquidity is enforced downstream by the engine's compute_fill;
    here we only require a chain quote (mid) to exist for each leg."""
    universe = settings.OPTIONS_CANARY_UNIVERSE
    strategy = settings.OPTIONS_CANARY_STRATEGY
    min_dte = int(settings.OPTIONS_CANARY_MIN_DTE)
    max_dte = int(settings.OPTIONS_CANARY_MAX_DTE)
    min_conf = float(settings.OPTIONS_CANARY_MIN_CONFIDENCE)

    out: list[tuple[TradeRequest, str]] = []
    with session_factory() as s:
        cands = s.execute(text(
            """
            SELECT id, underlying, rule_id, confidence, composite_score
            FROM options_strategy_candidate
            WHERE underlying = :u AND rule_id = :strat
              AND run_date = :rd AND confidence >= :minc
            ORDER BY confidence DESC, composite_score DESC, id ASC
            """
        ), {"u": universe, "strat": strategy, "rd": run_date,
            "minc": min_conf}).mappings().all()

        for c in cands:
            legs_rows = _candidate_legs(s, c["id"])
            if not legs_rows or any(not lr["option_symbol"] for lr in legs_rows):
                continue   # legs not materialized → skip (no_chain_for_proposal)
            expiries = {lr["expiry"] for lr in legs_rows}
            if len(expiries) != 1:
                continue
            dte = (next(iter(expiries)) - run_date).days
            if not (min_dte <= dte <= max_dte):
                continue
            syms = [lr["option_symbol"] for lr in legs_rows]
            quotes = latest_chain_quotes(s, syms, now=now)
            # P6D.34D promotion freshness gate — runs BEFORE the fillability
            # loop for correct reason attribution: compute_fill's
            # evaluate_quote already rejects effective age > 60s
            # (MAX_QUOTE_AGE_SECONDS) as REJECT_STALE_QUOTE, so without this
            # explicit check a stale candidate would be misreported as
            # 'unfillable'. The 60s fill gate below stays authoritative
            # (P6D.12 selector==engine parity is NOT loosened); this 900s
            # check is the coarse classifier. In practice the P6D.34D
            # universe refresh in run_promotion_cycle makes effective ages
            # ~0 so both gates pass on fresh chains. A missing leg quote is
            # classified stale too (no chain row = no fresh price).
            max_promo_age = int(
                settings.OPTIONS_CANARY_MAX_PROMOTION_AGE_SECONDS)
            leg_ages = [
                (quotes[lr["option_symbol"]].effective_age_seconds
                 if lr["option_symbol"] in quotes else None)
                for lr in legs_rows
            ]
            if any(a is None for a in leg_ages) or max(leg_ages) > max_promo_age:
                known = [a for a in leg_ages if a is not None]
                logger.info(
                    "canary selection: candidate id={} skipped stale_quotes "
                    "(max effective age={}s, limit={}s, missing_quotes={})",
                    c["id"], max(known) if known else None, max_promo_age,
                    sum(1 for a in leg_ages if a is None),
                )
                continue
            # P6D.12 fillability parity — every leg must clear the SAME
            # liquidity gate the paper engine enforces at open (OI>=500,
            # spread<=$0.10, age<=60s, valid bid/ask). Reuses compute_fill so
            # selector-promotable == engine-fillable; no duplicated thresholds.
            # The conservative FillResults are kept for the economics gate.
            fills: list[Decimal] = []
            for lr in legs_rows:
                q = quotes.get(lr["option_symbol"])
                fr = compute_fill(q, side=lr["side"]) if q is not None else None
                if fr is None or not fr.accepted:
                    fills = []
                    break
                fills.append(fr.fill_price)
            if not fills:
                continue   # unpriced or unfillable leg → skip
            req = _build_request(underlying=c["underlying"], strategy=strategy,
                                 legs_rows=legs_rows, quotes=quotes)
            # P6D.33A economic viability — entry credit estimated from the
            # SAME conservative fills the engine would use at open
            # (SELL fills − BUY fills, ×100×qty); max_loss via compute_risk;
            # close drag from the live half-spreads. Structurally uneconomic
            # spreads (fees+drag exceed economics) are never promoted.
            try:
                legs = list(req.legs)
                econ = assess_economics(
                    entry_credit=net_credit_dollars(legs, fills),
                    max_loss=compute_risk(
                        strategy, legs, fills).max_loss_dollars,
                    leg_half_spreads=[
                        (quotes[lr["option_symbol"]].ask
                         - quotes[lr["option_symbol"]].bid) / Decimal("2")
                        for lr in legs_rows
                    ],
                    leg_qtys=[l.qty for l in legs],
                    tp_pct=float(settings.OPTIONS_CANARY_TP_PCT),
                    min_credit_multiple=float(
                        settings.OPTIONS_CANARY_MIN_CREDIT_MULTIPLE),
                    min_net_reward_risk=float(
                        settings.OPTIONS_CANARY_MIN_NET_REWARD_RISK),
                )
            except (ValueError, StopIteration) as exc:
                logger.info(
                    "canary selection: candidate id={} skipped "
                    "(economics shape error: {})", c["id"], exc,
                )
                continue
            if not econ.viable:
                logger.info(
                    "canary selection: candidate id={} skipped uneconomic "
                    "({}): entry_credit={} min_viable_credit={} "
                    "expected_tp_close_net_pnl={} net_reward_risk={}",
                    c["id"], econ.reason, econ.entry_credit,
                    econ.min_viable_credit, econ.expected_tp_close_net_pnl,
                    econ.net_reward_risk,
                )
                continue
            phash = pos.proposal_hash(
                portfolio_id=portfolio_id, run_date=run_date,
                underlying=c["underlying"], strategy_name=strategy,
                strategy_version=STRATEGY_VERSION, legs=list(req.legs),
            )
            out.append((req, phash))

    logger.info(
        "canary selection: portfolio={} universe={} strategy={} eligible={}",
        portfolio_id, universe, strategy, len(out),
    )
    return out
