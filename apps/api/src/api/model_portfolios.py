"""MVP — model portfolios API + track-record compute + curated seed.

Endpoints (read-only here; follow→paper lives in Phase 4):
  GET /model-portfolios            list published + latest perf summary
  GET /model-portfolios/{slug}     detail: holdings + perf series

Track record is computed from the source-priority total-return panel
(adjusted_close, tiingo>yahoo>polygon) into model_portfolio_perf.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    ModelPortfolio,
    ModelPortfolioHolding,
    ModelPortfolioPerf,
)

router = APIRouter(prefix="/model-portfolios", tags=["model-portfolios"])


# ---------------------------------------------------------------------------
# Pure track-record math (unit-testable, no DB)
# ---------------------------------------------------------------------------


def compute_nav_series(
    price_map: dict[str, dict[dt.date, float]],
    weights: dict[str, float],
) -> list[tuple[dt.date, float, float | None]]:
    """Weighted total-return NAV indexed to 1.0 at the common start date.

    ``price_map[symbol][date] = adjusted_close``. Start = the latest first-date
    across held symbols (so every holding has data). Missing intermediate dates
    are forward-filled per symbol. Returns [(date, nav, daily_return)]."""
    syms = [s for s in weights if s in price_map and price_map[s]]
    if not syms:
        return []
    wsum = sum(weights[s] for s in syms)
    if wsum <= 0:
        return []
    w = {s: weights[s] / wsum for s in syms}                  # renormalize

    start = max(min(price_map[s]) for s in syms)              # intersection start
    all_dates = sorted({d for s in syms for d in price_map[s] if d >= start})
    base = {s: _on_or_before(price_map[s], start) for s in syms}
    if any(v is None for v in base.values()):
        return []

    out: list[tuple[dt.date, float, float | None]] = []
    last: dict[str, float] = dict(base)  # forward-fill state
    prev_nav: float | None = None
    for d in all_dates:
        for s in syms:
            if d in price_map[s]:
                last[s] = price_map[s][d]
        nav = sum(w[s] * (last[s] / base[s]) for s in syms)
        ret = None if prev_nav is None else (nav / prev_nav - 1.0)
        out.append((d, nav, ret))
        prev_nav = nav
    return out


def _on_or_before(series: dict[dt.date, float], d: dt.date) -> float | None:
    cands = [k for k in series if k <= d]
    return series[max(cands)] if cands else None


# ---------------------------------------------------------------------------
# DB compute + read
# ---------------------------------------------------------------------------

_PANEL_SQL = text(
    "SELECT DISTINCT ON (a.symbol, p.ts::date) a.symbol AS symbol, p.ts::date AS d, "
    "p.adjusted_close::float AS adj "
    "FROM price_bar p JOIN asset a ON a.id=p.asset_id "
    "WHERE p.timeframe='1d' AND a.symbol = ANY(:syms) AND p.adjusted_close IS NOT NULL "
    "ORDER BY a.symbol, p.ts::date, "
    "(CASE p.provider WHEN 'tiingo' THEN 100 WHEN 'yahoo' THEN 50 WHEN 'polygon' THEN 40 ELSE 0 END) DESC"
)


def compute_and_store(session: Session, portfolio: ModelPortfolio) -> int:
    """(Re)compute the track record for one portfolio; upsert perf rows.
    Returns the number of perf days written. Safe to call repeatedly."""
    holdings = list(portfolio.holdings)
    weights = {h.symbol.upper(): float(h.weight) for h in holdings}
    syms = list(weights)
    if not syms:
        return 0
    price_map: dict[str, dict[dt.date, float]] = {s: {} for s in syms}
    for row in session.execute(_PANEL_SQL, {"syms": syms}):
        price_map[row.symbol.upper()][row.d] = row.adj
    series = compute_nav_series(price_map, weights)

    session.execute(
        text("DELETE FROM model_portfolio_perf WHERE model_portfolio_id=:p"),
        {"p": portfolio.id},
    )
    for d, nav, ret in series:
        session.add(ModelPortfolioPerf(model_portfolio_id=portfolio.id, d=d, nav=nav, ret=ret))
    session.flush()
    return len(series)


def _summary(perf: list[ModelPortfolioPerf]) -> dict[str, Any]:
    if not perf:
        return {"return_pct": None, "max_drawdown_pct": None, "since": None, "points": 0}
    navs = [float(p.nav) for p in perf]
    peak, mdd = navs[0], 0.0
    for n in navs:
        peak = max(peak, n)
        mdd = min(mdd, n / peak - 1.0)
    return {
        "return_pct": round((navs[-1] - 1.0) * 100, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "since": perf[0].d.isoformat(),
        "points": len(perf),
    }


@router.get("")
def list_model_portfolios(db: Session = Depends(get_session)) -> dict[str, Any]:
    pfs = db.scalars(
        select(ModelPortfolio).where(ModelPortfolio.is_published.is_(True))
        .order_by(ModelPortfolio.name.asc())
    ).all()
    items = []
    for pf in pfs:
        perf = db.scalars(
            select(ModelPortfolioPerf).where(ModelPortfolioPerf.model_portfolio_id == pf.id)
            .order_by(ModelPortfolioPerf.d.asc())
        ).all()
        items.append({
            "slug": pf.slug, "name": pf.name, "thesis": pf.thesis,
            "risk_label": pf.risk_label, "holdings_count": len(pf.holdings),
            **_summary(perf),
            "spark": [round(float(p.nav), 4) for p in perf[::max(1, len(perf) // 40)]],
        })
    return {"portfolios": items}


@router.get("/{slug}")
def model_portfolio_detail(slug: str, db: Session = Depends(get_session)) -> dict[str, Any]:
    pf = db.scalars(select(ModelPortfolio).where(ModelPortfolio.slug == slug)).first()
    if pf is None:
        raise HTTPException(status_code=404, detail="model portfolio not found")
    perf = db.scalars(
        select(ModelPortfolioPerf).where(ModelPortfolioPerf.model_portfolio_id == pf.id)
        .order_by(ModelPortfolioPerf.d.asc())
    ).all()
    return {
        "slug": pf.slug, "name": pf.name, "thesis": pf.thesis, "risk_label": pf.risk_label,
        "holdings": [
            {"symbol": h.symbol, "weight_pct": round(float(h.weight) * 100, 1)}
            for h in sorted(pf.holdings, key=lambda h: -float(h.weight))
        ],
        **_summary(perf),
        "curve": [{"d": p.d.isoformat(), "nav": round(float(p.nav), 4)} for p in perf],
    }


# ---------------------------------------------------------------------------
# Curated seed (3–5 beginner-friendly portfolios)
# ---------------------------------------------------------------------------

CURATED: list[dict[str, Any]] = [
    {
        "slug": "steady-compounders", "name": "Steady Compounders", "risk_label": "balanced",
        "thesis": "Large, durable businesses that have compounded for decades — the boring core of a beginner portfolio.",
        "holdings": {"AAPL": 0.2, "MSFT": 0.2, "JNJ": 0.15, "PG": 0.15, "V": 0.15, "KO": 0.15},
    },
    {
        "slug": "dividend-growers", "name": "Dividend Growers", "risk_label": "conservative",
        "thesis": "Companies that raise their dividend year after year — income that grows while you learn.",
        "holdings": {"JNJ": 0.2, "PG": 0.2, "KO": 0.2, "PEP": 0.2, "MCD": 0.2},
    },
    {
        "slug": "american-megacaps", "name": "American Megacaps", "risk_label": "growth",
        "thesis": "The biggest US companies driving the index — concentrated, higher-beta, higher-reward.",
        "holdings": {"AAPL": 0.2, "MSFT": 0.2, "NVDA": 0.2, "AMZN": 0.2, "GOOGL": 0.2},
    },
    {
        "slug": "everyday-brands", "name": "Everyday Brands", "risk_label": "balanced",
        "thesis": "Products you already use — a relatable first portfolio you can reason about.",
        "holdings": {"AAPL": 0.2, "MCD": 0.2, "KO": 0.2, "NKE": 0.2, "DIS": 0.2},
    },
]


def seed_curated(session: Session, *, recompute: bool = True) -> list[str]:
    """Idempotent: insert any missing curated portfolios (by slug); optionally
    compute their track records. Returns slugs seeded/updated."""
    touched: list[str] = []
    for spec in CURATED:
        pf = session.scalars(
            select(ModelPortfolio).where(ModelPortfolio.slug == spec["slug"])
        ).first()
        if pf is None:
            pf = ModelPortfolio(
                slug=spec["slug"], name=spec["name"], thesis=spec["thesis"],
                risk_label=spec["risk_label"], is_published=True,
            )
            session.add(pf)
            session.flush()
            for sym, wt in spec["holdings"].items():
                session.add(ModelPortfolioHolding(
                    model_portfolio_id=pf.id, symbol=sym, weight=wt))
            session.flush()
            touched.append(spec["slug"])
        if recompute:
            compute_and_store(session, pf)
    session.commit()
    return touched
