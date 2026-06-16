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
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
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
) -> ReplayDayResult:
    """Replay one historical decision day through the real paper pipeline."""
    cfg = config or load_engine_config()
    version = f"{cfg.version}+replay:{run_label}"
    name = f"replay:{run_label}"

    account_id = _get_or_create_account(session, name)
    portfolio_id = _get_or_create_portfolio(session, name, starting_cash)

    # Decision date = midnight(T) UTC; fill submitted at end-of-T so the next
    # bar (T+1) fills (decision uses data through T's close).
    generated_at = dt.datetime(as_of.year, as_of.month, as_of.day,
                               tzinfo=dt.timezone.utc)
    submitted_at = dt.datetime.combine(
        as_of, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)

    assets = _universe_assets(session, universe_name, as_of)

    recommendations = buys = trades_submitted = 0
    trades_skipped_existing = rejected = 0

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
    )
