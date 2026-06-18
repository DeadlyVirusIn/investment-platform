"""MVP — model portfolios API + track-record compute + curated seed.

Endpoints (read-only here; follow→paper lives in Phase 4):
  GET /model-portfolios            list published + latest perf summary
  GET /model-portfolios/{slug}     detail: holdings + perf series

Track record is computed from the source-priority total-return panel
(adjusted_close, tiingo>yahoo>polygon) into model_portfolio_perf.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset,
    ModelPortfolio,
    ModelPortfolioHolding,
    ModelPortfolioPerf,
    PaperPortfolio,
    PortfolioFollow,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    PaperTradeRejected,
    submit_trade,
)
from apps.api.src.domain.paper_trading.paper_service import (
    PortfolioCreate,
    create_portfolio,
)

router = APIRouter(prefix="/model-portfolios", tags=["model-portfolios"])


# ---------------------------------------------------------------------------
# Per-user identity + portfolio ownership (MVP auth layer)
# ---------------------------------------------------------------------------


def require_user_id(
    x_auth_user_id: str | None = Header(default=None, alias="X-Auth-User-Id"),
) -> str:
    """MVP auth: the edge/frontend supplies a stable per-user identity via the
    ``X-Auth-User-Id`` header (a device id today; swap for the IdP subject when
    a full auth provider lands). Write endpoints REQUIRE it so every paper book
    is per-user and no two users ever share state."""
    uid = (x_auth_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="authentication required")
    return uid[:64]


def _resolve_user_portfolio(db: Session, user_id: str) -> str:
    """Get-or-create the user's OWN stock paper book — the per-user replacement
    for the old shared canonical portfolio. Returns its id."""
    name = f"user:{user_id}:stock"
    pf = db.scalars(select(PaperPortfolio).where(PaperPortfolio.name == name)).first()
    if pf is None:
        pf = create_portfolio(
            db,
            PortfolioCreate(name=name, starting_cash=Decimal("100000"),
                            max_open_positions=100),
        )
    return pf.id


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


def _fill_submitted_at(session: Session, asset_id: str) -> "dt.datetime | None":
    """A ``submitted_at`` that makes the engine's strict next-bar rule
    (``PriceBar.ts > submitted_at``) resolve to the LATEST available 1d bar.
    Returns (latest_bar_ts - 1s) so a live 'follow/add now' fills at today's
    close instead of a non-existent future bar. None if the asset has no bars."""
    ts = session.execute(
        text("SELECT max(ts) FROM price_bar WHERE asset_id=:a AND timeframe='1d'"),
        {"a": asset_id},
    ).scalar()
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts - dt.timedelta(seconds=1)


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


@router.get("/social/summary")
def social_summary(db: Session = Depends(get_session)) -> dict[str, Any]:
    """Social proof for the Discover feed: most-followed portfolios, trending
    (followed in the last 7 days), and most-added single ideas. Each block is
    defensive — empty when there is no activity yet (honest, no fabrication)."""
    def _rows(sql: str) -> list[Any]:
        try:
            return list(db.execute(text(sql)).all())
        except Exception:  # noqa: BLE001 — missing table/col → empty, never 500
            return []

    most_followed = [
        {"slug": r[0], "name": r[1], "follows": int(r[2])}
        for r in _rows(
            "SELECT mp.slug, mp.name, count(*) n FROM portfolio_follow f "
            "JOIN model_portfolio mp ON mp.id=f.model_portfolio_id "
            "GROUP BY mp.slug, mp.name ORDER BY n DESC LIMIT 5"
        )
    ]
    trending = [
        {"slug": r[0], "name": r[1], "follows": int(r[2])}
        for r in _rows(
            "SELECT mp.slug, mp.name, count(*) n FROM portfolio_follow f "
            "JOIN model_portfolio mp ON mp.id=f.model_portfolio_id "
            "WHERE f.followed_at >= now() - interval '7 days' "
            "GROUP BY mp.slug, mp.name ORDER BY n DESC LIMIT 5"
        )
    ]
    most_added = [
        {"symbol": str(r[0]).replace("idea:", ""), "adds": int(r[1])}
        for r in _rows(
            "SELECT reason, count(*) n FROM paper_trade "
            "WHERE reason LIKE 'idea:%' GROUP BY reason ORDER BY n DESC LIMIT 8"
        )
    ]
    return {"most_followed": most_followed, "trending": trending, "most_added": most_added}


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
# Follow → paper portfolio (Phase 4)
# ---------------------------------------------------------------------------


class FollowRequest(BaseModel):
    starting_cash: Decimal = Decimal("10000")


@router.post("/{slug}/follow")
def follow_model_portfolio(
    slug: str,
    body: FollowRequest | None = None,
    db: Session = Depends(get_session),
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Create a paper portfolio that mirrors the model portfolio's weights —
    one BUY per holding, sized to weight × starting_cash. Reuses the existing
    paper engine (create_portfolio + submit_trade). Idempotency is by design
    loose: each follow makes a fresh paper book (a user may follow more than
    once over time)."""
    pf = db.scalars(select(ModelPortfolio).where(ModelPortfolio.slug == slug)).first()
    if pf is None:
        raise HTTPException(status_code=404, detail="model portfolio not found")
    holdings = list(pf.holdings)
    if not holdings:
        raise HTTPException(status_code=400, detail="portfolio has no holdings")

    capital = (body or FollowRequest()).starting_cash
    if capital <= 0:
        raise HTTPException(status_code=400, detail="starting_cash must be positive")

    name = f"Follow:{user_id}:{pf.name} · {uuid4().hex[:6]}"
    paper = create_portfolio(
        db,
        PortfolioCreate(
            name=name,
            starting_cash=capital,
            max_open_positions=max(len(holdings), 20),
        ),
    )

    opened: list[str] = []
    skipped: dict[str, str] = {}
    for h in holdings:
        asset = db.scalars(select(Asset).where(Asset.symbol == h.symbol.upper())).first()
        if asset is None:
            skipped[h.symbol] = "no asset"
            continue
        usd = (Decimal(str(h.weight)) * capital).quantize(Decimal("0.01"))
        if usd <= 0:
            skipped[h.symbol] = "zero allocation"
            continue
        sa = _fill_submitted_at(db, asset.id)
        if sa is None:
            skipped[h.symbol] = "no price data"
            continue
        try:
            submit_trade(
                db,
                portfolio_id=paper.id,
                asset_id=asset.id,
                side="buy",
                usd_amount=usd,
                submitted_at=sa,
                reason=f"follow:{slug}",
                merge_positions=False,
            )
            opened.append(h.symbol)
        except PaperTradeRejected as exc:
            skipped[h.symbol] = str(exc)

    db.add(PortfolioFollow(
        model_portfolio_id=pf.id, paper_portfolio_id=paper.id, user_id=user_id,
    ))
    db.commit()

    return {
        "paper_portfolio_id": paper.id,
        "name": name,
        "slug": slug,
        "opened": opened,
        "skipped": skipped,
        "starting_cash": float(capital),
    }


# ---------------------------------------------------------------------------
# Add a single idea to the canonical paper portfolio (Phase 5)
# ---------------------------------------------------------------------------


class AddIdeaRequest(BaseModel):
    usd_amount: Decimal = Decimal("1000")


@router.post("/idea/{symbol}/add-to-paper")
def add_idea_to_paper(
    symbol: str,
    body: AddIdeaRequest | None = None,
    db: Session = Depends(get_session),
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Buy ``usd_amount`` of a single idea into THE USER'S OWN paper book
    (per-user, never the shared canonical). Reuses the paper engine; the idea
    detail's 'Add to paper' CTA calls this."""
    asset = db.scalars(select(Asset).where(Asset.symbol == symbol.upper())).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    usd = (body or AddIdeaRequest()).usd_amount
    if usd <= 0:
        raise HTTPException(status_code=400, detail="usd_amount must be positive")
    pid = _resolve_user_portfolio(db, user_id)
    sa = _fill_submitted_at(db, asset.id)
    if sa is None:
        raise HTTPException(status_code=409, detail=f"no price data for {symbol}")
    try:
        submit_trade(
            db, portfolio_id=pid, asset_id=asset.id, side="buy",
            usd_amount=usd, submitted_at=sa, reason=f"idea:{symbol.upper()}",
            merge_positions=True,
        )
    except PaperTradeRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"portfolio_id": pid, "symbol": symbol.upper(), "usd_amount": float(usd)}


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
