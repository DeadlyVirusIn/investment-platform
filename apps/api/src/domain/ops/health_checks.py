"""Health-check primitives invoked by the daily runner.

Each check returns a (ok: bool, details: dict) pair. The daily runner maps
results to Alerts based on severity rules.

All checks are read-only — no writes, no side effects.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    CandidateIdea,
    FactorSnapshot,
    PaperEquitySnapshot,
    PaperTrade,
    PriceBar,
    RegimeSnapshot,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

STALENESS_PRICE_DAYS = 3
STALENESS_FACTOR_DAYS = 3
STALENESS_REGIME_DAYS = 3

# Buy-skip reasons considered "healthy side effects" (tight portfolio + held
# names re-affirmed). Any skip outside this set escalates to WARNING.
SAFE_SKIP_REASONS: set[str] = {"duplicate_holding", "portfolio_full", "pending_sell_same_asset"}


# ---------------------------------------------------------------------------
# A. Data freshness
# ---------------------------------------------------------------------------


def check_data_freshness(
    session: Session, as_of: dt.date,
) -> tuple[bool, dict]:
    latest_price = session.execute(
        select(func.max(PriceBar.ts)).where(PriceBar.timeframe == "1d")
    ).scalar_one_or_none()
    latest_price_date = latest_price.date() if latest_price else None

    latest_factor = session.execute(
        select(func.max(FactorSnapshot.as_of_date))
    ).scalar_one_or_none()
    latest_regime = session.execute(
        select(func.max(RegimeSnapshot.as_of_date))
    ).scalar_one_or_none()

    price_lag = (as_of - latest_price_date).days if latest_price_date else 999
    factor_lag = (as_of - latest_factor).days if latest_factor else 999
    regime_lag = (as_of - latest_regime).days if latest_regime else 999

    ok = (
        price_lag <= STALENESS_PRICE_DAYS
        and factor_lag <= STALENESS_FACTOR_DAYS
        and regime_lag <= STALENESS_REGIME_DAYS
    )
    return ok, {
        "latest_price_date": str(latest_price_date) if latest_price_date else None,
        "latest_factor_date": str(latest_factor) if latest_factor else None,
        "latest_regime_date": str(latest_regime) if latest_regime else None,
        "price_lag_days": price_lag,
        "factor_lag_days": factor_lag,
        "regime_lag_days": regime_lag,
    }


# ---------------------------------------------------------------------------
# B. Engine output
# ---------------------------------------------------------------------------


def check_engine_output(
    session: Session, as_of: dt.date,
) -> tuple[bool, dict]:
    rows = list(session.execute(
        select(CandidateIdea.status, CandidateIdea.action)
        .where(CandidateIdea.as_of_date == as_of)
    ).all())
    total = len(rows)
    accepted = sum(1 for s, _ in rows if s == "accepted")
    rejected = sum(1 for s, _ in rows if s == "rejected")
    buys = sum(1 for s, a in rows if s == "accepted" and a == "Buy")
    trims = sum(1 for s, a in rows if s == "accepted" and a == "Trim")
    sells = sum(1 for s, a in rows if s == "accepted" and a == "Sell")

    ok = total > 0
    zero_but_healthy = total > 0 and buys == 0
    return ok, {
        "candidate_idea_total": total,
        "accepted": accepted,
        "rejected": rejected,
        "buys": buys,
        "trims": trims,
        "sells": sells,
        "zero_but_healthy": zero_but_healthy,
    }


# ---------------------------------------------------------------------------
# C. Paper trading
# ---------------------------------------------------------------------------


def check_paper_trading(
    session: Session, as_of: dt.date,
) -> tuple[bool, dict]:
    start = dt.datetime.combine(as_of, dt.time.min, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    trades = list(session.execute(
        select(PaperTrade.side, PaperTrade.portfolio_id)
        .where(PaperTrade.fill_ts >= start, PaperTrade.fill_ts < end)
    ).all())
    buys = sum(1 for side, _ in trades if side == "buy")
    sells = sum(1 for side, _ in trades if side == "sell")
    portfolios = len({pid for _, pid in trades})
    ok = True  # zero trades is legitimate on skip days — upstream decides
    return ok, {
        "trade_count": len(trades),
        "buys": buys,
        "sells": sells,
        "portfolios_touched": portfolios,
    }


def check_duplicate_execution(
    session: Session, as_of: dt.date,
) -> tuple[bool, dict]:
    """True (ok) when no duplicate trades for same day/portfolio/asset/side."""
    start = dt.datetime.combine(as_of, dt.time.min, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    dupes = session.execute(
        select(
            PaperTrade.portfolio_id, PaperTrade.asset_id, PaperTrade.side,
            func.count().label("n"),
        ).where(
            PaperTrade.fill_ts >= start, PaperTrade.fill_ts < end,
        ).group_by(
            PaperTrade.portfolio_id, PaperTrade.asset_id, PaperTrade.side,
        ).having(func.count() > 1)
    ).all()
    return len(dupes) == 0, {"duplicate_groups": len(dupes)}


# ---------------------------------------------------------------------------
# D. Equity snapshot
# ---------------------------------------------------------------------------


def check_equity_snapshot(
    session: Session, as_of: dt.date,
) -> tuple[bool, dict]:
    # Phase L M079: health check requires at least one live snapshot.
    count = session.execute(
        select(func.count()).select_from(PaperEquitySnapshot).where(
            PaperEquitySnapshot.snapshot_date == as_of,
            PaperEquitySnapshot.source == "live",
        )
    ).scalar_one()
    return count > 0, {"live_snapshots_on_date": int(count)}


# ---------------------------------------------------------------------------
# E. ML sizing log
# ---------------------------------------------------------------------------


def classify_buy_skips(as_of: dt.date) -> tuple[bool, dict]:
    """Read artifacts/paper_trading_skips/<as_of>.jsonl and aggregate skip
    reasons. Returns (all_safe, detail). ``all_safe`` means every skip code
    is in SAFE_SKIP_REASONS — daily_runner uses this to downgrade
    `buys_without_execution` to INFO.
    """
    import json
    from pathlib import Path

    path = Path("artifacts/paper_trading_skips") / f"{as_of.isoformat()}.jsonl"
    counts: dict[str, int] = {}
    total = 0
    if not path.exists():
        return True, {"skip_log_path": str(path), "exists": False, "counts": counts, "total": 0}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        reason = rec.get("reason", "unknown_reason")
        counts[reason] = counts.get(reason, 0) + 1
        total += 1
    all_safe = all(r in SAFE_SKIP_REASONS for r in counts)
    return all_safe, {
        "skip_log_path": str(path),
        "exists": True,
        "counts": counts,
        "total": total,
        "all_safe": all_safe,
        "unsafe_reasons": [r for r in counts if r not in SAFE_SKIP_REASONS],
    }


def check_ml_sizing_log(
    as_of: dt.date, expected_mode: str,
) -> tuple[bool, dict]:
    path = Path(f"artifacts/ml_sizing/{as_of.isoformat()}.jsonl")
    if not path.exists():
        return False, {"log_path": str(path), "exists": False, "expected_mode": expected_mode}
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        import json
        header = json.loads(first)
        mode = header.get("sizing_mode")
    except Exception as exc:  # noqa: BLE001
        return False, {"log_path": str(path), "parse_error": str(exc)}
    return mode == expected_mode, {
        "log_path": str(path),
        "sizing_mode_actual": mode,
        "sizing_mode_expected": expected_mode,
        "engine_version": MODEL_VERSION,
    }
