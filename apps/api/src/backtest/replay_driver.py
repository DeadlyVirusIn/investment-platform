"""BACKTEST-PAPER-5 — single-day real-paper-parity replay driver.

Runs the LIVE recommendation engine + paper execution for ONE historical
decision date, using the bias-guarded as_of seams:

  * compute_for_asset(as_of=T)            — bias-free decision (BP2 + QW2-A)
  * persist(generated_at=T, version+repl) — decision-date stamp + namespace (BP4)
  * submit_trade(submitted_at=end-of-T)   — next-bar (T+1) fill, MP1S attribution

Forward chronological multi-day loop, exits, outcome scoring and reporting
are deferred to BACKTEST-PAPER-6. This slice proves a single day end-to-end.

Idempotent: persist() dedups recommendations on (asset, version,
snapshot_hash); trades are skipped when a PaperPosition already carries the
recommendation's opened_by_recommendation_id. Rerun = no-op.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.db.models import Account, PaperPortfolio, PaperPosition
from apps.api.src.domain.features.stock_factor_engine import _universe_assets
from apps.api.src.domain.ledger.account_service import AccountCreate, create_account
from apps.api.src.domain.paper_trading.paper_execution import (
    PaperTradeRejected,
    submit_trade,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    EngineConfig,
    compute_for_asset,
    load_engine_config,
    persist,
)
from scripts.run_paper_exit_cycle import run_exit_cycle


@dataclass
class ReplayDayResult:
    as_of: dt.date
    account_id: str
    portfolio_id: str
    run_label: str
    model_version: str
    assets_evaluated: int
    recommendations: int
    buys: int
    trades_submitted: int
    trades_skipped_existing: int
    rejected: int
    insufficient_data: int = 0


def _get_or_create_account(session: Session, name: str) -> str:
    existing = session.scalars(
        select(Account).where(Account.name == name)
    ).first()
    if existing is not None:
        return existing.id
    return create_account(session, AccountCreate(name=name, kind="manual")).id


def _get_or_create_portfolio(
    session: Session, name: str, starting_cash: Decimal
) -> str:
    existing = session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.name == name)
    ).first()
    if existing is not None:
        return existing.id
    return create_portfolio(
        session, PortfolioCreate(name=name, starting_cash=starting_cash)
    ).id


def replay_one_day(
    session: Session,
    *,
    as_of: dt.date,
    run_label: str,
    universe_name: str = "stock_swing_v1",
    starting_cash: Decimal = Decimal("100000"),
    trade_usd: Decimal = Decimal("1000"),
    config: EngineConfig | None = None,
    account_id: str | None = None,
    portfolio_id: str | None = None,
) -> ReplayDayResult:
    """Replay one historical decision day through the real paper pipeline.

    ``account_id``/``portfolio_id`` (default None) let a caller (replay_range)
    pass an already-resolved replay account/portfolio so it is created ONCE
    across a multi-day run; when None they are get-or-created by name.
    """
    cfg = config or load_engine_config()
    version = f"{cfg.version}+replay:{run_label}"
    name = f"replay:{run_label}"

    account_id = account_id or _get_or_create_account(session, name)
    portfolio_id = portfolio_id or _get_or_create_portfolio(
        session, name, starting_cash)

    # Decision date = midnight(T) UTC; fill submitted at end-of-T so the next
    # bar (T+1) fills (decision uses data through T's close).
    generated_at = dt.datetime(as_of.year, as_of.month, as_of.day,
                               tzinfo=dt.timezone.utc)
    submitted_at = dt.datetime.combine(
        as_of, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)

    assets = _universe_assets(session, universe_name, as_of)

    recommendations = buys = trades_submitted = 0
    trades_skipped_existing = rejected = insufficient_data = 0

    for asset in assets:
        result = compute_for_asset(
            session, account_id=account_id, asset_id=asset.id,
            config=cfg, as_of=as_of,
        )
        rec_id = persist(
            session, result,
            generated_at=generated_at,
            model_version_override=version,
        )
        recommendations += 1
        if not result.enough_data or result.action == "Watch":
            insufficient_data += 1

        if result.action != "Buy":
            continue
        buys += 1

        already = session.scalars(
            select(PaperPosition).where(
                PaperPosition.portfolio_id == portfolio_id,
                PaperPosition.opened_by_recommendation_id == rec_id,
            )
        ).first()
        if already is not None:
            trades_skipped_existing += 1
            continue

        try:
            submit_trade(
                session,
                portfolio_id=portfolio_id,
                asset_id=asset.id,
                side="buy",
                usd_amount=trade_usd,
                submitted_at=submitted_at,
                recommendation_id=rec_id,
                reason=f"replay:{run_label}",
            )
            trades_submitted += 1
        except PaperTradeRejected:
            rejected += 1

    return ReplayDayResult(
        as_of=as_of, account_id=account_id, portfolio_id=portfolio_id,
        run_label=run_label, model_version=version,
        assets_evaluated=len(assets), recommendations=recommendations,
        buys=buys, trades_submitted=trades_submitted,
        trades_skipped_existing=trades_skipped_existing, rejected=rejected,
        insufficient_data=insufficient_data,
    )


@dataclass
class ReplayRangeResult:
    start: dt.date
    end: dt.date
    run_label: str
    model_version: str
    account_id: str
    portfolio_id: str
    trading_days: int
    days: list[dt.date]
    recommendations: int
    buys: int
    trades_submitted: int
    trades_skipped_existing: int
    rejected: int
    exits_closed: int
    realized_pnl_total: Decimal
    insufficient_data: int
    closed_pairs: list[tuple[Decimal | None, Decimal | None]] = field(
        default_factory=list)


def _trading_days(
    session: Session, universe_name: str, start: dt.date, end: dt.date,
) -> list[dt.date]:
    """Distinct 1d price_bar dates for the universe's assets in [start, end],
    ascending. Weekends/holidays fall out naturally (no bars)."""
    rows = session.execute(text(
        """
        SELECT DISTINCT (pb.ts AT TIME ZONE 'UTC')::date AS d
        FROM price_bar pb
        JOIN universe_membership um ON um.asset_id = pb.asset_id
        WHERE pb.timeframe = '1d' AND um.universe_name = :u
          AND (pb.ts AT TIME ZONE 'UTC')::date BETWEEN :start AND :end
        ORDER BY d
        """
    ), {"u": universe_name, "start": start, "end": end}).all()
    return [r[0] for r in rows]


def replay_range(
    session: Session,
    *,
    start: dt.date,
    end: dt.date,
    run_label: str,
    universe_name: str = "stock_swing_v1",
    starting_cash: Decimal = Decimal("100000"),
    trade_usd: Decimal = Decimal("1000"),
    take_profit_pct: Decimal | None = None,
    stop_loss_pct: Decimal | None = None,
    max_hold_days: int | None = None,
    config: EngineConfig | None = None,
) -> ReplayRangeResult:
    """Deterministic forward-chronological stock replay over [start, end].

    One replay account+portfolio is reused across all days (resolved once),
    so paper cash/holdings stay self-consistent day to day. Per trading day,
    in live order: EXITS first (run_exit_cycle, portfolio-scoped) then OPENS
    (replay_one_day). Commits per day. Idempotent: a full rerun on identical
    data is a no-op (persist dedups recs; trades skip on existing
    opened_by_recommendation_id; exits scan only is_open positions).

    Caveat (v1): the recommendation exposure family reads the LEDGER
    (compute_positions), not paper_position, and the replay account has no
    ledger transactions — so the exposure family is NEUTRAL throughout replay.
    Portfolio cash/holdings/realized_pnl (paper_position) are still
    self-consistent; only the exposure feature input is unaffected by replay
    holdings. Pointing exposure at paper_position is deferred (BP7+).
    """
    cfg = config or load_engine_config()
    version = f"{cfg.version}+replay:{run_label}"
    name = f"replay:{run_label}"

    account_id = _get_or_create_account(session, name)
    portfolio_id = _get_or_create_portfolio(session, name, starting_cash)

    days = _trading_days(session, universe_name, start, end)

    recommendations = buys = trades_submitted = 0
    trades_skipped_existing = rejected = insufficient_data = 0
    exits_closed = 0
    realized_pnl_total = Decimal("0")

    for day in days:
        # Exits first (mirror live: free slots before opens).
        exit_res = run_exit_cycle(
            session, as_of=day, portfolio_id=portfolio_id,
            take_profit_pct=take_profit_pct, stop_loss_pct=stop_loss_pct,
            max_hold_days=max_hold_days, commit=True,
        )
        exits_closed += len(exit_res.closed)
        realized_pnl_total += exit_res.realized_pnl_total

        # Opens second, into the same account/portfolio.
        day_res = replay_one_day(
            session, as_of=day, run_label=run_label,
            universe_name=universe_name, trade_usd=trade_usd, config=cfg,
            account_id=account_id, portfolio_id=portfolio_id,
        )
        recommendations += day_res.recommendations
        buys += day_res.buys
        trades_submitted += day_res.trades_submitted
        trades_skipped_existing += day_res.trades_skipped_existing
        rejected += day_res.rejected
        insufficient_data += day_res.insufficient_data

        session.commit()

    closed_pairs = [
        (r[0], r[1])
        for r in session.execute(text(
            """
            SELECT r.conviction, pp.realized_pnl
            FROM paper_position pp
            JOIN recommendation r ON r.id = pp.opened_by_recommendation_id
            WHERE pp.portfolio_id = :pf
              AND pp.is_open = FALSE
              AND pp.realized_pnl IS NOT NULL
            """
        ), {"pf": portfolio_id}).all()
    ]

    return ReplayRangeResult(
        start=start, end=end, run_label=run_label, model_version=version,
        account_id=account_id, portfolio_id=portfolio_id,
        trading_days=len(days), days=days,
        recommendations=recommendations, buys=buys,
        trades_submitted=trades_submitted,
        trades_skipped_existing=trades_skipped_existing, rejected=rejected,
        exits_closed=exits_closed, realized_pnl_total=realized_pnl_total,
        insufficient_data=insufficient_data, closed_pairs=closed_pairs,
    )
