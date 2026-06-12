"""Rule-based auto-trader. Turns Recommendation rows into paper trades.

v1 rules (intentionally simple):
    BUY when:
        - latest recommendation action = Buy
        - AND confidence >= buy_confidence_threshold
        - AND asset not already held
        - AND max_open_positions not exceeded
        Sizing: usd_amount = sizing_pct_of_equity * current_equity.

    SELL when:
        - latest recommendation flips to Sell (or Trim)
        - OR holding age in days >= max_holding_days
        Sells the full open quantity (no partials in v1).

Deterministic. No randomness. Uses existing submit_trade() for execution.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    PaperPortfolio,
    PaperPosition,
    Recommendation,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    DEFAULT_MAX_OPEN_POSITIONS,
    DEFAULT_SIZING_PCT,
    PaperTradeRejected,
    _compute_current_equity,
    _d,
    submit_trade,
)


# ---------------------------------------------------------------------------
# Config + decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutoTradeConfig:
    buy_confidence_threshold: Decimal = Decimal("60")   # 0..100
    max_holding_days: int = 30
    sizing_pct_of_equity: Decimal | None = None          # None → per-portfolio config
    max_buy_candidates_per_run: int = 50


@dataclass
class AutoTradeDecision:
    kind: str                       # "open_buy" | "close_sell" | "skip"
    asset_id: str
    reason: str
    recommendation_id: str | None = None
    usd_amount: Decimal | None = None
    quantity: Decimal | None = None
    symbol: str | None = None       # informational


@dataclass
class AutoTradeRunResult:
    portfolio_id: str
    decisions: list[AutoTradeDecision] = field(default_factory=list)
    executed: list[str] = field(default_factory=list)         # trade_ids
    rejected: list[dict] = field(default_factory=list)        # {asset_id, reason}
    # Per-asset skip reasons for accepted Buys that were NOT turned into a
    # trade decision (filtered in generate_decisions before execute).
    # Categories: duplicate_holding | portfolio_full | sizing_below_threshold
    #             | pending_sell_same_asset
    buy_skips: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _portfolio_config(portfolio: PaperPortfolio) -> dict:
    try:
        return json.loads(portfolio.config_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


@dataclass
class _BuyCandidate:
    """Source-agnostic Buy record consumed by auto-trader. Fields match what
    the decision flow needs (id for recommendation_id FK backfill, asset_id,
    action, conviction). Supports both Recommendation (live) and
    CandidateIdea (historical replay via as_of).
    """
    id: str
    asset_id: str
    action: str
    conviction: Decimal


def _rec_to_buy(rec: Recommendation) -> _BuyCandidate:
    return _BuyCandidate(
        id=rec.id,
        asset_id=rec.asset_id,
        action=rec.action,
        conviction=Decimal(rec.conviction) if rec.conviction is not None else Decimal("0"),
    )


def _candidate_to_buy(c: CandidateIdea) -> _BuyCandidate:
    return _BuyCandidate(
        id=c.id,
        asset_id=c.asset_id,
        action=c.action or "",
        conviction=Decimal(c.confidence) if c.confidence is not None else Decimal("0"),
    )


def _latest_rec_for_asset(
    session: Session, asset_id: str, as_of: dt.date | None = None,
) -> _BuyCandidate | None:
    """Resolve latest engine decision for an asset. When as_of is set, read
    the candidate_idea row for that exact date (live replay). Otherwise fall
    back to Recommendation.generated_at desc (production behavior)."""
    if as_of is not None:
        stmt = (
            select(CandidateIdea)
            .where(
                CandidateIdea.asset_id == asset_id,
                CandidateIdea.as_of_date == as_of,
                CandidateIdea.status == "accepted",
            )
            .order_by(CandidateIdea.created_at.desc())
            .limit(1)
        )
        cand = session.scalars(stmt).first()
        return _candidate_to_buy(cand) if cand else None

    stmt = (
        select(Recommendation)
        .where(Recommendation.asset_id == asset_id)
        .order_by(Recommendation.generated_at.desc())
        .limit(1)
    )
    rec = session.scalars(stmt).first()
    return _rec_to_buy(rec) if rec else None


def _latest_buy_candidates(
    session: Session,
    threshold: Decimal,
    as_of: dt.date | None = None,
) -> list[_BuyCandidate]:
    """When as_of is set, query candidate_idea for that date (historical
    replay). Otherwise use Recommendation-latest-per-asset (live production).
    Threshold is applied against `confidence` (CandidateIdea) or
    `conviction` (Recommendation) respectively."""
    if as_of is not None:
        stmt = (
            select(CandidateIdea)
            .where(
                CandidateIdea.as_of_date == as_of,
                CandidateIdea.status == "accepted",
                CandidateIdea.action == "Buy",
                CandidateIdea.confidence >= threshold,
            )
            .order_by(
                CandidateIdea.confidence.desc(), CandidateIdea.asset_id.asc(),
            )
        )
        return [_candidate_to_buy(c) for c in session.scalars(stmt)]

    # Live path — unchanged behavior.
    from sqlalchemy import func
    latest_ts = (
        select(
            Recommendation.asset_id.label("asset_id"),
            func.max(Recommendation.generated_at).label("max_ts"),
        )
        .where(Recommendation.action == "Buy")
        .group_by(Recommendation.asset_id)
        .subquery()
    )
    stmt = (
        select(Recommendation)
        .join(
            latest_ts,
            (Recommendation.asset_id == latest_ts.c.asset_id)
            & (Recommendation.generated_at == latest_ts.c.max_ts),
        )
        .where(
            Recommendation.action == "Buy",
            Recommendation.conviction >= threshold,
        )
        .order_by(Recommendation.conviction.desc(), Recommendation.asset_id.asc())
    )
    return [_rec_to_buy(r) for r in session.scalars(stmt)]


def _holding_age_days(now: dt.datetime, opened_at: dt.datetime | None) -> int:
    if opened_at is None:
        return 0
    if opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return max(0, (now - opened_at).days)


# ---------------------------------------------------------------------------
# Decision generator
# ---------------------------------------------------------------------------


def generate_decisions(
    session: Session,
    portfolio: PaperPortfolio,
    config: AutoTradeConfig,
    *,
    now: dt.datetime | None = None,
    as_of: dt.date | None = None,
    skips_out: list[dict] | None = None,
) -> list[AutoTradeDecision]:
    """Produce ordered decisions. Sells first (may free exposure), then buys."""
    now = now or dt.datetime.now(dt.timezone.utc)
    portfolio_cfg = _portfolio_config(portfolio)
    max_open = int(portfolio_cfg.get("max_open_positions", DEFAULT_MAX_OPEN_POSITIONS))
    sizing_pct = (
        config.sizing_pct_of_equity
        or _d(portfolio_cfg.get("sizing_pct_of_equity", DEFAULT_SIZING_PCT))
    )

    decisions: list[AutoTradeDecision] = []

    # --- Step 1: evaluate exits on open positions
    open_positions = list(session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.is_open.is_(True),
        )
    ))
    pending_sell_assets: set[str] = set()
    for pos in open_positions:
        # P0-3B — in-run dedup. Duplicate open-position rows for the same
        # asset (the 06-04..06-10 double-fill artifacts) must not emit two
        # sell decisions in one run; close one leg per run.
        if pos.asset_id in pending_sell_assets:
            continue
        age = _holding_age_days(now, pos.opened_at)
        if age >= config.max_holding_days:
            decisions.append(AutoTradeDecision(
                kind="close_sell",
                asset_id=pos.asset_id,
                quantity=_d(pos.quantity),
                reason=f"max_holding_days={config.max_holding_days} exceeded (held {age}d)",
            ))
            pending_sell_assets.add(pos.asset_id)
            continue

        latest = _latest_rec_for_asset(session, pos.asset_id, as_of=as_of)
        if latest is not None and latest.action in ("Sell", "Trim"):
            decisions.append(AutoTradeDecision(
                kind="close_sell",
                asset_id=pos.asset_id,
                quantity=_d(pos.quantity),
                # FK: only Recommendation ids are valid; candidate_idea replay uses None.
                recommendation_id=latest.id if as_of is None else None,
                reason=f"recommendation flipped to {latest.action}",
            ))
            pending_sell_assets.add(pos.asset_id)

    held_asset_ids = {pos.asset_id for pos in open_positions} - pending_sell_assets
    # Post-sell open count estimate
    running_open_count = len(open_positions) - len(pending_sell_assets)

    # --- Step 2: buy candidates
    candidates = _latest_buy_candidates(
        session, config.buy_confidence_threshold, as_of=as_of,
    )[: config.max_buy_candidates_per_run]

    equity = _compute_current_equity(session, portfolio)
    usd_target = (sizing_pct * equity).quantize(Decimal("0.01"))

    if usd_target <= 0:
        return decisions

    # Cash-aware shrink — never removes the cash guard. If shrunk
    # below the min-notional floor, the decision is skipped below.
    from apps.api.src.domain.paper_trading.paper_execution import (
        shrink_to_cash as _shrink,
    )
    available_cash = _d(portfolio.cash)
    usd_per_trade, shrink_info = _shrink(
        target_usd=usd_target, available_cash=available_cash,
    )
    if shrink_info["shrink_applied"] and not shrink_info["below_min"]:
        logger.info(
            "[auto_trader.shrink] target={} cash={} buffer={} "
            "cap={} final={} shrink_applied=True",
            shrink_info["target_usd"], shrink_info["available_cash"],
            shrink_info["cash_buffer_pct"], shrink_info["cap_usd"],
            shrink_info["final_usd"],
        )

    # recommendation_id must be None when signal source is candidate_idea
    # (FK to `recommendation.id`; candidate_idea.id is a different table).
    rec_id_allowed = as_of is None

    def _record_skip(asset_id: str, code: str, detail: dict | None = None) -> None:
        if skips_out is None:
            return
        skips_out.append({
            "asset_id": asset_id, "reason": code, "detail": detail or {},
        })

    # P0-3B — pending-buy guard, the buy-side twin of pending_sell_assets.
    # A duplicated candidate list (or any double iteration) can emit at most
    # ONE buy decision per asset per run.
    pending_buy_assets: set[str] = set()
    for rec in candidates:
        if running_open_count >= max_open:
            _record_skip(rec.asset_id, "portfolio_full",
                         {"running_open": running_open_count, "max_open": max_open})
            continue
        if rec.asset_id in pending_buy_assets:
            _record_skip(rec.asset_id, "duplicate_candidate_in_run")
            continue
        if rec.asset_id in held_asset_ids:
            _record_skip(rec.asset_id, "duplicate_holding")
            continue
        if rec.asset_id in pending_sell_assets:
            _record_skip(rec.asset_id, "pending_sell_same_asset")
            continue
        if usd_per_trade <= 0:
            # Either equity-based target was zero/negative (extreme
            # config), or cash-aware shrink fell below
            # PAPER_MIN_NOTIONAL_USD. Surface the explicit reason.
            code = (
                "position_too_small"
                if shrink_info.get("below_min")
                else "sizing_below_threshold"
            )
            _record_skip(rec.asset_id, code, {
                "usd_per_trade": str(usd_per_trade),
                **shrink_info,
            })
            continue
        decisions.append(AutoTradeDecision(
            kind="open_buy",
            asset_id=rec.asset_id,
            recommendation_id=rec.id if rec_id_allowed else None,
            usd_amount=usd_per_trade,
            reason=(
                f"Buy rec conviction={rec.conviction} >= threshold "
                f"{config.buy_confidence_threshold}"
            ),
        ))
        pending_buy_assets.add(rec.asset_id)
        running_open_count += 1

    return decisions


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_decisions(
    session: Session,
    portfolio: PaperPortfolio,
    decisions: list[AutoTradeDecision],
    *,
    submitted_at: dt.datetime | None = None,
) -> AutoTradeRunResult:
    """Submit each decision; collect trade ids + rejections (don't raise).

    ``submitted_at`` is propagated as the submission timestamp of every trade
    (callers can freeze time for determinism / tests). Defaults to None →
    ``submit_trade`` uses ``datetime.now(UTC)``.
    """
    run = AutoTradeRunResult(portfolio_id=portfolio.id)
    run.decisions = decisions
    for d in decisions:
        try:
            if d.kind == "open_buy":
                result = submit_trade(
                    session,
                    portfolio_id=portfolio.id,
                    asset_id=d.asset_id,
                    side="buy",
                    usd_amount=d.usd_amount,
                    submitted_at=submitted_at,
                    reason=f"auto_trader: {d.reason}",
                    recommendation_id=d.recommendation_id,
                )
                run.executed.append(result.trade_id)
            elif d.kind == "close_sell":
                result = submit_trade(
                    session,
                    portfolio_id=portfolio.id,
                    asset_id=d.asset_id,
                    side="sell",
                    quantity=d.quantity,
                    submitted_at=submitted_at,
                    reason=f"auto_trader: {d.reason}",
                    recommendation_id=d.recommendation_id,
                )
                run.executed.append(result.trade_id)
        except PaperTradeRejected as exc:
            run.rejected.append({
                "asset_id": d.asset_id,
                "kind": d.kind,
                "reason": str(exc),
            })
            logger.info(
                "auto_trader rejected kind={} asset={}: {}",
                d.kind, d.asset_id, exc,
            )
    return run


def auto_trade_portfolio(
    session: Session,
    portfolio: PaperPortfolio,
    config: AutoTradeConfig | None = None,
    *,
    now: dt.datetime | None = None,
    as_of: dt.date | None = None,
) -> AutoTradeRunResult:
    """Convenience: generate + execute for one portfolio.

    ``now`` drives holding-age + submission timestamp.
    ``as_of`` (optional) switches signal source from Recommendation-latest
    (live) to candidate_idea.as_of_date (historical replay).
    """
    cfg = config or AutoTradeConfig()
    skips: list[dict] = []
    decisions = generate_decisions(
        session, portfolio, cfg, now=now, as_of=as_of, skips_out=skips,
    )
    result = execute_decisions(session, portfolio, decisions, submitted_at=now)
    result.buy_skips = skips
    # Log execution-layer rejections with a normalized code so they roll up
    # into the same categorization.
    for rj in result.rejected:
        msg = str(rj.get("reason", "")).lower()
        if rj.get("kind") != "open_buy":
            continue
        if "insufficient cash" in msg:
            code = "cash_constraint"
        elif "no price bar" in msg:
            code = "execution_failure"
        elif "max open positions" in msg:
            code = "portfolio_full"
        else:
            code = "unknown_reason"
        result.buy_skips.append({
            "asset_id": rj.get("asset_id"), "reason": code,
            "detail": {"exec_reason": rj.get("reason")},
        })
    return result
