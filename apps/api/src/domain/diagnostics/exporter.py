"""Diagnostic bundle exporter — stdlib zipfile + json + csv.

All inputs are sourced from existing domain services. No new writes.

Bounds (stated defaults):
* factor_snapshots rows: capped at ``FACTOR_ROW_CAP`` unless symbols filter is
  provided, in which case the date window is the only bound.
* candidates + paper_trades: bounded by the (from, to) window; no global row
  cap.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import zipfile
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    FactorSnapshot,
    JobRun,
    JobSchedule,
    PaperPortfolio,
    PaperTrade,
    RegimeSnapshot,
)
from apps.api.src.domain.dashboard.summary import build_summary
from apps.api.src.domain.diagnostics.csv_tools import rows_to_csv
from apps.api.src.domain.pnl.attribution import (
    DEFAULT_BLOCKED_HORIZON_DAYS,
    DEFAULT_BLOCKED_MIN_SCORE,
    attribution_by_regime,
    attribution_by_score_bucket,
    blocked_alpha_sim,
)
from apps.api.src.domain.pnl.engine import (
    per_symbol_pnl,
    portfolio_pnl,
    resolve_portfolio,
)
from apps.api.src.domain.stock_engine.candidate_repo import rejection_summary

FACTOR_ROW_CAP = 2000


# ---------------------------------------------------------------------------
# Shared column specs (keep parity with the single-endpoint CSV exports)
# ---------------------------------------------------------------------------


CANDIDATE_COLUMNS: tuple[str, ...] = (
    "as_of_date", "symbol", "asset_id", "status", "action",
    "rejection_reason", "composite_score", "confidence",
    "model_version", "engine",
)

SYMBOL_PNL_COLUMNS: tuple[str, ...] = (
    "symbol", "asset_id", "status", "quantity", "avg_cost", "mark",
    "realized_pnl", "unrealized_pnl", "total_pnl", "holding_days",
    "entry_composite_score", "entry_confidence",
    "entry_market_trend", "entry_vol_regime",
)

PAPER_TRADE_COLUMNS: tuple[str, ...] = (
    "fill_ts", "side", "symbol", "asset_id", "quantity", "fill_price",
    "slippage_bps", "commission", "realized_pnl", "reason",
    "recommendation_id",
)

FACTOR_COLUMNS: tuple[str, ...] = (
    "as_of_date", "symbol", "asset_id",
    "residual_momentum_20d", "residual_momentum_60d",
    "sector_relative_rank", "trend_strength_20d",
    "price_vs_200sma", "atr_percent_14",
    "earnings_proximity_days", "avg_dollar_volume_20d",
    "enough_data", "stale_data", "feature_set_hash",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dec_str(v: Any) -> str | None:
    if v is None:
        return None
    return str(v) if isinstance(v, Decimal) else str(v)


def _json(obj: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (dt.datetime, dt.date)):
            return o.isoformat()
        raise TypeError(f"not serializable: {type(o).__name__}")

    return json.dumps(obj, indent=2, default=default, sort_keys=False)


def _resolve_symbol_filter(
    session: Session, symbols: Sequence[str] | None,
) -> set[str] | None:
    if not symbols:
        return None
    rows = session.execute(
        select(Asset.id).where(Asset.symbol.in_([s.upper() for s in symbols]))
    ).all()
    return {r[0] for r in rows}


def _symbol_map_for(
    session: Session, asset_ids: Iterable[str],
) -> dict[str, str]:
    ids = list(set(asset_ids))
    if not ids:
        return {}
    rows = session.execute(
        select(Asset.id, Asset.symbol).where(Asset.id.in_(ids))
    ).all()
    return {aid: sym for aid, sym in rows}


# ---------------------------------------------------------------------------
# Section builders (each returns (filename, bytes))
# ---------------------------------------------------------------------------


def _dashboard_section(
    session: Session, portfolio_id: str | None, to_date: dt.date,
) -> tuple[str, bytes]:
    payload = build_summary(session, portfolio_id=portfolio_id, as_of=to_date)
    return "dashboard_summary.json", _json(payload).encode("utf-8")


def _pnl_summary_section(
    session: Session, portfolio: PaperPortfolio | None,
) -> tuple[str, bytes]:
    if portfolio is None:
        return "pnl_summary.json", _json({"portfolio_id": None}).encode("utf-8")
    p = portfolio_pnl(session, portfolio)
    payload = {
        "portfolio_id": p.portfolio_id,
        "starting_cash": _dec_str(p.starting_cash),
        "cash": _dec_str(p.cash),
        "invested": _dec_str(p.invested),
        "nav": _dec_str(p.nav),
        "cumulative_pnl": _dec_str(p.cumulative_pnl),
        "daily_pnl": _dec_str(p.daily_pnl),
        "realized_pnl": _dec_str(p.realized_pnl),
        "unrealized_pnl": _dec_str(p.unrealized_pnl),
        "open_positions": p.open_positions_count,
        "closed_trades": p.closed_trade_count,
        "wins": p.wins, "losses": p.losses, "breakeven": p.breakeven,
        "win_rate": _dec_str(p.win_rate),
        "avg_win": _dec_str(p.avg_win),
        "avg_loss": _dec_str(p.avg_loss),
    }
    return "pnl_summary.json", _json(payload).encode("utf-8")


def _pnl_by_symbol_section(
    session: Session, portfolio: PaperPortfolio | None,
) -> tuple[str, bytes]:
    if portfolio is None:
        return "pnl_by_symbol.csv", rows_to_csv([], SYMBOL_PNL_COLUMNS).encode("utf-8")
    rows = per_symbol_pnl(session, portfolio)
    dicts = [
        {
            "symbol": r.symbol,
            "asset_id": r.asset_id,
            "status": r.status,
            "quantity": r.quantity,
            "avg_cost": r.avg_cost,
            "mark": r.mark,
            "realized_pnl": r.realized_pnl,
            "unrealized_pnl": r.unrealized_pnl,
            "total_pnl": r.total_pnl,
            "holding_days": r.holding_days,
            "entry_composite_score": r.entry_composite_score,
            "entry_confidence": r.entry_confidence,
            "entry_market_trend": r.entry_market_trend,
            "entry_vol_regime": r.entry_vol_regime,
        }
        for r in rows
    ]
    return "pnl_by_symbol.csv", rows_to_csv(dicts, SYMBOL_PNL_COLUMNS).encode("utf-8")


def _pnl_by_bucket_section(
    session: Session, portfolio: PaperPortfolio | None,
) -> tuple[str, bytes]:
    if portfolio is None:
        return "pnl_by_score_bucket.json", _json({"buckets": []}).encode("utf-8")
    rows = attribution_by_score_bucket(session, portfolio)
    payload = {
        "portfolio_id": portfolio.id,
        "buckets": [
            {
                "bucket": b.bucket, "trade_count": b.trade_count,
                "wins": b.wins,
                "realized_pnl": _dec_str(b.realized_pnl),
                "unrealized_pnl": _dec_str(b.unrealized_pnl),
                "total_pnl": _dec_str(b.total_pnl),
                "avg_pnl_per_trade": _dec_str(b.avg_pnl_per_trade),
            }
            for b in rows
        ],
    }
    return "pnl_by_score_bucket.json", _json(payload).encode("utf-8")


def _pnl_by_regime_section(
    session: Session, portfolio: PaperPortfolio | None,
) -> tuple[str, bytes]:
    if portfolio is None:
        return "pnl_by_regime.json", _json({"regimes": []}).encode("utf-8")
    rows = attribution_by_regime(session, portfolio)
    payload = {
        "portfolio_id": portfolio.id,
        "regimes": [
            {
                "market_trend": s.market_trend, "vol_regime": s.vol_regime,
                "trade_count": s.trade_count,
                "realized_pnl": _dec_str(s.realized_pnl),
                "unrealized_pnl": _dec_str(s.unrealized_pnl),
                "total_pnl": _dec_str(s.total_pnl),
                "avg_pnl_per_trade": _dec_str(s.avg_pnl_per_trade),
            }
            for s in rows
        ],
    }
    return "pnl_by_regime.json", _json(payload).encode("utf-8")


def _blocked_alpha_section(
    session: Session, start: dt.date, end: dt.date,
) -> tuple[str, bytes]:
    report = blocked_alpha_sim(
        session,
        min_score=DEFAULT_BLOCKED_MIN_SCORE,
        horizon_days=DEFAULT_BLOCKED_HORIZON_DAYS,
        from_date=start, to_date=end,
    )
    payload = {
        "min_score": _dec_str(report.min_score),
        "horizon_days": report.horizon_days,
        "from": report.from_date.isoformat(),
        "to": report.to_date.isoformat(),
        "simulated_count": report.simulated_count,
        "skipped_count": report.skipped_count,
        "avg_return": _dec_str(report.avg_return),
        "total_return": _dec_str(report.total_return),
        "wins": report.wins, "losses": report.losses,
        "win_rate": _dec_str(report.win_rate),
        "top_winners": [
            {
                "symbol": s.symbol, "as_of_date": s.as_of_date.isoformat(),
                "return_pct": _dec_str(s.return_pct),
                "rejection_reason": s.rejection_reason,
            }
            for s in report.top_winners
        ],
        "top_losers": [
            {
                "symbol": s.symbol, "as_of_date": s.as_of_date.isoformat(),
                "return_pct": _dec_str(s.return_pct),
                "rejection_reason": s.rejection_reason,
            }
            for s in report.top_losers
        ],
    }
    return "blocked_alpha_sim.json", _json(payload).encode("utf-8")


def _candidates_section(
    session: Session, start: dt.date, end: dt.date,
    asset_ids_filter: set[str] | None,
) -> tuple[str, bytes]:
    stmt = (
        select(CandidateIdea, Asset.symbol)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(
            CandidateIdea.as_of_date >= start,
            CandidateIdea.as_of_date <= end,
        )
        .order_by(CandidateIdea.as_of_date.asc(), Asset.symbol.asc())
    )
    if asset_ids_filter is not None:
        stmt = stmt.where(CandidateIdea.asset_id.in_(list(asset_ids_filter)))
    rows = []
    for c, sym in session.execute(stmt).all():
        rows.append({
            "as_of_date": c.as_of_date.isoformat(),
            "symbol": sym,
            "asset_id": c.asset_id,
            "status": c.status,
            "action": c.action,
            "rejection_reason": c.rejection_reason,
            "composite_score": c.composite_score,
            "confidence": c.confidence,
            "model_version": c.model_version,
            "engine": c.engine,
        })
    return "candidate_ideas.csv", rows_to_csv(rows, CANDIDATE_COLUMNS).encode("utf-8")


def _rejection_summary_section(
    session: Session, end: dt.date,
) -> tuple[str, bytes]:
    return (
        "rejection_summary.json",
        _json(rejection_summary(session, end)).encode("utf-8"),
    )


def _regime_history_section(
    session: Session, start: dt.date, end: dt.date,
) -> tuple[str, bytes]:
    stmt = (
        select(RegimeSnapshot)
        .where(
            RegimeSnapshot.as_of_date >= start,
            RegimeSnapshot.as_of_date <= end,
        )
        .order_by(RegimeSnapshot.as_of_date.asc())
    )
    rows = []
    for r in session.scalars(stmt):
        rows.append({
            "as_of_date": r.as_of_date.isoformat(),
            "benchmark_symbol": r.benchmark_symbol,
            "market_trend": r.market_trend,
            "vol_regime": r.vol_regime,
            "breadth_regime": r.breadth_regime,
            "sma50_over_sma200": r.sma50_over_sma200,
            "realized_vol_20d": _dec_str(r.realized_vol_20d),
            "atr_pctile_1y": _dec_str(r.atr_pctile_1y),
        })
    return (
        "regime_history.json",
        _json({"from": start.isoformat(), "to": end.isoformat(),
               "count": len(rows), "snapshots": rows}).encode("utf-8"),
    )


def _paper_trades_section(
    session: Session, portfolio: PaperPortfolio | None,
    start: dt.date, end: dt.date,
    asset_ids_filter: set[str] | None,
) -> tuple[str, bytes]:
    if portfolio is None:
        return "paper_trades.csv", rows_to_csv([], PAPER_TRADE_COLUMNS).encode("utf-8")
    upper = dt.datetime.combine(
        end + dt.timedelta(days=1),
        dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
    )
    lower = dt.datetime.combine(
        start, dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
    )
    stmt = (
        select(PaperTrade, Asset.symbol)
        .join(Asset, Asset.id == PaperTrade.asset_id)
        .where(
            PaperTrade.portfolio_id == portfolio.id,
            PaperTrade.fill_ts >= lower,
            PaperTrade.fill_ts < upper,
        )
        .order_by(PaperTrade.fill_ts.asc())
    )
    if asset_ids_filter is not None:
        stmt = stmt.where(PaperTrade.asset_id.in_(list(asset_ids_filter)))
    rows = []
    for t, sym in session.execute(stmt).all():
        rows.append({
            "fill_ts": t.fill_ts.isoformat() if t.fill_ts else None,
            "side": t.side,
            "symbol": sym,
            "asset_id": t.asset_id,
            "quantity": t.quantity,
            "fill_price": t.fill_price,
            "slippage_bps": t.slippage_bps,
            "commission": t.commission,
            "realized_pnl": t.realized_pnl,
            "reason": t.reason,
            "recommendation_id": t.recommendation_id,
        })
    return "paper_trades.csv", rows_to_csv(rows, PAPER_TRADE_COLUMNS).encode("utf-8")


def _job_status_section(session: Session) -> tuple[str, bytes]:
    scheds = list(session.scalars(select(JobSchedule)))
    rows: list[dict[str, Any]] = []
    for s in scheds:
        last = session.scalars(
            select(JobRun)
            .where(JobRun.job_schedule_id == s.id)
            .order_by(desc(JobRun.started_at))
            .limit(1)
        ).first()
        rows.append({
            "name": s.name, "cron": s.cron_expr, "enabled": s.enabled,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
            "last_status": last.status if last else None,
            "last_duration_seconds": _dec_str(last.duration_seconds) if last else None,
            "last_error": last.error_message if last else None,
        })
    return "job_status.json", _json({"jobs": rows}).encode("utf-8")


def _factor_snapshots_section(
    session: Session, start: dt.date, end: dt.date,
    asset_ids_filter: set[str] | None,
) -> tuple[str, bytes]:
    stmt = (
        select(FactorSnapshot, Asset.symbol)
        .join(Asset, Asset.id == FactorSnapshot.asset_id)
        .where(
            FactorSnapshot.as_of_date >= start,
            FactorSnapshot.as_of_date <= end,
        )
        .order_by(FactorSnapshot.as_of_date.asc(), Asset.symbol.asc())
    )
    if asset_ids_filter is not None:
        stmt = stmt.where(FactorSnapshot.asset_id.in_(list(asset_ids_filter)))
    else:
        stmt = stmt.limit(FACTOR_ROW_CAP)
    rows = []
    for f, sym in session.execute(stmt).all():
        rows.append({
            "as_of_date": f.as_of_date.isoformat(),
            "symbol": sym,
            "asset_id": f.asset_id,
            "residual_momentum_20d": f.residual_momentum_20d,
            "residual_momentum_60d": f.residual_momentum_60d,
            "sector_relative_rank": f.sector_relative_rank,
            "trend_strength_20d": f.trend_strength_20d,
            "price_vs_200sma": f.price_vs_200sma,
            "atr_percent_14": f.atr_percent_14,
            "earnings_proximity_days": f.earnings_proximity_days,
            "avg_dollar_volume_20d": f.avg_dollar_volume_20d,
            "enough_data": f.enough_data,
            "stale_data": f.stale_data,
            "feature_set_hash": f.feature_set_hash,
        })
    return "factor_snapshots.csv", rows_to_csv(rows, FACTOR_COLUMNS).encode("utf-8")


# ---------------------------------------------------------------------------
# Bundle assembler
# ---------------------------------------------------------------------------


def build_diagnostic_bundle(
    session: Session,
    *,
    from_date: dt.date,
    to_date: dt.date,
    portfolio_id: str | None = None,
    symbols: Sequence[str] | None = None,
    include_factors: bool = True,
    include_candidates: bool = True,
    include_pnl: bool = True,
    include_jobs: bool = True,
) -> tuple[bytes, dict[str, Any]]:
    """Produce a zip blob + metadata dict summarizing the bundle."""
    portfolio = resolve_portfolio(session, portfolio_id)
    asset_ids_filter = _resolve_symbol_filter(session, symbols)

    files: list[tuple[str, bytes]] = []
    files.append(_dashboard_section(session, portfolio_id, to_date))

    if include_pnl:
        files.append(_pnl_summary_section(session, portfolio))
        files.append(_pnl_by_symbol_section(session, portfolio))
        files.append(_pnl_by_bucket_section(session, portfolio))
        files.append(_pnl_by_regime_section(session, portfolio))
        files.append(_blocked_alpha_section(session, from_date, to_date))
        files.append(
            _paper_trades_section(
                session, portfolio, from_date, to_date, asset_ids_filter,
            )
        )

    if include_candidates:
        files.append(
            _candidates_section(session, from_date, to_date, asset_ids_filter)
        )
        files.append(_rejection_summary_section(session, to_date))

    files.append(_regime_history_section(session, from_date, to_date))

    if include_jobs:
        files.append(_job_status_section(session))

    if include_factors:
        files.append(
            _factor_snapshots_section(
                session, from_date, to_date, asset_ids_filter,
            )
        )

    # Write zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, payload in files:
            z.writestr(name, payload)

    manifest = {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "portfolio_id": portfolio.id if portfolio is not None else None,
        "symbols": list(symbols) if symbols else None,
        "include_factors": include_factors,
        "include_candidates": include_candidates,
        "include_pnl": include_pnl,
        "include_jobs": include_jobs,
        "files": [name for name, _ in files],
        "factor_row_cap_applied": (
            include_factors and asset_ids_filter is None
        ),
        "factor_row_cap": FACTOR_ROW_CAP,
    }
    return buf.getvalue(), manifest
