"""Deterministic feature computation from price_bar and ledger state.

Pure Decimal math. No external APIs. No randomness. No LLM.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import PriceBar


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Series:
    ts: list[dt.datetime]
    close: list[Decimal]   # prefer adjusted_close
    high: list[Decimal]
    low: list[Decimal]

    def __len__(self) -> int:
        return len(self.close)


@dataclass
class SignalOut:
    factor_key: str
    family: str
    score: Decimal        # [-1, +1]
    weight: Decimal       # weight within the family
    raw_value: Decimal | None
    threshold: Decimal | None
    direction: str        # bullish | bearish | neutral
    narrative: str


@dataclass
class FamilyOut:
    family: str
    score: Decimal        # family-weighted [-1, +1]
    signals: list[SignalOut]
    computable: bool      # False → exclude from composite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _clamp(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, v))


def _sma(values: list[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    return sum(values[-period:], Decimal("0")) / Decimal(period)


def _rsi(values: list[Decimal], period: int = 14) -> Decimal | None:
    if len(values) < period + 1:
        return None
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(len(values) - period, len(values)):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(Decimal("0"))
        else:
            gains.append(Decimal("0"))
            losses.append(-diff)
    avg_gain = sum(gains, Decimal("0")) / Decimal(period)
    avg_loss = sum(losses, Decimal("0")) / Decimal(period)
    if avg_loss == 0:
        return Decimal("100") if avg_gain > 0 else Decimal("50")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def _max_drawdown(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    peak = values[0]
    max_dd = Decimal("0")
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _atr(series: Series, period: int = 14) -> Decimal | None:
    if len(series) < period + 1:
        return None
    trs: list[Decimal] = []
    for i in range(len(series) - period, len(series)):
        high = series.high[i]
        low = series.low[i]
        prev_close = series.close[i - 1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs, Decimal("0")) / Decimal(period)


# ---------------------------------------------------------------------------
# Series loader
# ---------------------------------------------------------------------------


def load_series(
    session: Session,
    asset_id: str,
    days: int = 400,
    *,
    as_of: dt.date | None = None,
) -> Series | None:
    """Fetch the trailing daily series for an asset from price_bar.

    QW2-A: ``as_of`` makes the loader replay-correct. Default (None) is the
    exact legacy behaviour — trailing ``days`` window anchored to wall-clock
    now(), no upper bound (live: newest bar is same-day, so harmless). When
    ``as_of`` is set the window is anchored to the DECISION date instead and
    an upper bound is added so a past run never sees a bar stamped AFTER the
    decision date (lookahead). Live callers pass no as_of -> no behaviour
    change; only replay/backtest callers pass one.
    """
    stmt = select(PriceBar).where(
        PriceBar.asset_id == asset_id,
        PriceBar.timeframe == "1d",
    )
    if as_of is None:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        stmt = stmt.where(PriceBar.ts >= since)
    else:
        anchor = dt.datetime(
            as_of.year, as_of.month, as_of.day, tzinfo=dt.timezone.utc
        )
        since = anchor - dt.timedelta(days=days)
        end = anchor + dt.timedelta(days=1)   # exclusive: ts < start of as_of+1
        stmt = stmt.where(PriceBar.ts >= since, PriceBar.ts < end)
    stmt = stmt.order_by(PriceBar.ts.asc())
    bars = list(session.execute(stmt).scalars())
    if not bars:
        return None
    return Series(
        ts=[b.ts for b in bars],
        close=[_d(b.adjusted_close if b.adjusted_close is not None else b.close) for b in bars],
        high=[_d(b.high if b.high is not None else b.close) for b in bars],
        low=[_d(b.low if b.low is not None else b.close) for b in bars],
    )


# ---------------------------------------------------------------------------
# Trend / momentum
# ---------------------------------------------------------------------------


def compute_trend_momentum(series: Series, cfg: dict[str, Any]) -> FamilyOut:
    signals: list[SignalOut] = []
    if len(series) < 21:
        return FamilyOut("trend_momentum", Decimal("0"), [], computable=False)

    close = series.close
    current = close[-1]
    sig_cfg = cfg.get("signals", {})

    # Core trend measurements reused by multiple signals
    long_sma = _sma(close, 200) or _sma(close, min(len(close), 100))
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50) if len(close) >= 50 else None

    # Detect strong uptrend / downtrend (used to override RSI)
    strong_uptrend = bool(
        sma20 and sma50 and long_sma
        and sma20 > sma50
        and current > long_sma
    )
    strong_downtrend = bool(
        sma20 and sma50 and long_sma
        and sma20 < sma50
        and current < long_sma
    )

    # --- price_vs_sma_long ------------------------------------------------
    if long_sma and long_sma > 0:
        pct = (current - long_sma) / long_sma
        score = _clamp(pct * Decimal("5"), Decimal("-1"), Decimal("1"))
        direction = (
            "bullish" if pct > Decimal("0.01")
            else "bearish" if pct < Decimal("-0.01")
            else "neutral"
        )
        signals.append(SignalOut(
            factor_key="price_vs_sma_long",
            family="trend_momentum",
            score=score,
            weight=_d(sig_cfg.get("macd_signal", {}).get("weight", Decimal("0.35"))),
            raw_value=pct,
            threshold=Decimal("0"),
            direction=direction,
            narrative=(
                f"Price {current:.2f} vs long SMA {long_sma:.2f} "
                f"({pct * 100:.2f}%)"
            ),
        ))

    # --- sma_20_vs_50 -----------------------------------------------------
    if sma20 and sma50 and sma50 > 0:
        pct = (sma20 - sma50) / sma50
        score = _clamp(pct * Decimal("10"), Decimal("-1"), Decimal("1"))
        direction = (
            "bullish" if pct > Decimal("0.005")
            else "bearish" if pct < Decimal("-0.005")
            else "neutral"
        )
        signals.append(SignalOut(
            factor_key="sma_20_vs_50",
            family="trend_momentum",
            score=score,
            weight=_d(sig_cfg.get("ema_crossover", {}).get("weight", Decimal("0.35"))),
            raw_value=pct,
            threshold=Decimal("0"),
            direction=direction,
            narrative=(
                f"SMA(20)={sma20:.2f} vs SMA(50)={sma50:.2f} "
                f"({pct * 100:.2f}%)"
            ),
        ))

    # --- trend_strength ---------------------------------------------------
    # New signal: flags confirmed bullish / bearish regime.
    if strong_uptrend:
        ts_score = Decimal("1")
        ts_dir = "bullish"
        ts_note = "Strong uptrend (SMA20 > SMA50 and price > long SMA)."
    elif strong_downtrend:
        ts_score = Decimal("-1")
        ts_dir = "bearish"
        ts_note = "Strong downtrend (SMA20 < SMA50 and price < long SMA)."
    else:
        ts_score = Decimal("0")
        ts_dir = "neutral"
        ts_note = "No clear trend regime."
    signals.append(SignalOut(
        factor_key="trend_strength",
        family="trend_momentum",
        score=ts_score,
        weight=Decimal("0.25"),
        raw_value=None,
        threshold=None,
        direction=ts_dir,
        narrative=ts_note,
    ))

    # --- rsi_14 (with strong-trend override) ------------------------------
    rsi_cfg = sig_cfg.get("rsi", {})
    rsi = _rsi(close, int(rsi_cfg.get("period", 14)))
    if rsi is not None:
        oversold = _d(rsi_cfg.get("oversold", 35))
        overbought = _d(rsi_cfg.get("overbought", 68))
        rsi_override_applied = False

        if rsi <= oversold and not strong_downtrend:
            score = Decimal("0.8")
            direction = "bullish"
            note = f"RSI(14)={rsi:.2f} oversold -> bullish"
        elif rsi >= overbought:
            if strong_uptrend:
                # Override: do not penalize overbought within a confirmed uptrend.
                score = Decimal("0")
                direction = "neutral"
                note = (
                    f"RSI(14)={rsi:.2f} overbought but override active "
                    f"(strong uptrend): score neutralized"
                )
                rsi_override_applied = True
            else:
                score = Decimal("-0.8")
                direction = "bearish"
                note = f"RSI(14)={rsi:.2f} overbought -> bearish"
        else:
            mid = (oversold + overbought) / Decimal("2")
            span = (overbought - oversold) / Decimal("2")
            if span == 0:
                score = Decimal("0")
            else:
                score = -_clamp(
                    (rsi - mid) / span, Decimal("-1"), Decimal("1")
                ) * Decimal("0.5")
            direction = "neutral"
            note = f"RSI(14)={rsi:.2f} in neutral band"

        narrative = note
        if rsi_override_applied:
            narrative += " (strong-trend override)"
        signals.append(SignalOut(
            factor_key="rsi_14",
            family="trend_momentum",
            score=score,
            weight=_d(rsi_cfg.get("weight", Decimal("0.30"))),
            raw_value=rsi,
            threshold=oversold,
            direction=direction,
            narrative=narrative,
        ))

    total_w = sum((s.weight for s in signals), Decimal("0"))
    if total_w == 0:
        return FamilyOut("trend_momentum", Decimal("0"), signals, computable=False)
    agg = sum((s.score * s.weight for s in signals), Decimal("0")) / total_w
    return FamilyOut("trend_momentum", agg, signals, computable=True)


# ---------------------------------------------------------------------------
# Volatility / risk
# ---------------------------------------------------------------------------


def compute_volatility_risk(series: Series, cfg: dict[str, Any]) -> FamilyOut:
    signals: list[SignalOut] = []
    if len(series) < 30:
        return FamilyOut("volatility_risk", Decimal("0"), [], computable=False)

    sig_cfg = cfg.get("signals", {})
    current = series.close[-1]

    # ATR(14) / price
    atr = _atr(series, 14)
    if atr is not None and current > 0:
        atr_pct = atr / current
        score = -_clamp(atr_pct * Decimal("10"), Decimal("0"), Decimal("1"))
        signals.append(SignalOut(
            factor_key="atr_pct_14",
            family="volatility_risk",
            score=score,
            weight=_d(sig_cfg.get("atr_pct", {}).get("weight", Decimal("0.40"))),
            raw_value=atr_pct,
            threshold=Decimal("0.05"),
            direction="bearish" if score < Decimal("-0.20") else "neutral",
            narrative=f"ATR(14)/price = {atr_pct * 100:.2f}%",
        ))

    # Max drawdown over trailing lookback
    lookback = int(sig_cfg.get("max_drawdown", {}).get("lookback_days", 252))
    mdd_vals = series.close[-lookback:] if len(series.close) >= lookback else series.close
    mdd = _max_drawdown(mdd_vals)
    score_mdd = -_clamp(mdd * Decimal("2"), Decimal("0"), Decimal("1"))
    signals.append(SignalOut(
        factor_key="max_drawdown",
        family="volatility_risk",
        score=score_mdd,
        weight=_d(sig_cfg.get("max_drawdown", {}).get("weight", Decimal("0.25"))),
        raw_value=mdd,
        threshold=Decimal("0.20"),
        direction="bearish" if mdd > Decimal("0.20") else "neutral",
        narrative=f"Max drawdown (trailing {lookback}d) = {mdd * 100:.2f}%",
    ))

    # Beta vs SPY — not computed in v1 (no SPY benchmark loader yet)
    signals.append(SignalOut(
        factor_key="beta_vs_spy",
        family="volatility_risk",
        score=Decimal("0"),
        weight=_d(sig_cfg.get("beta", {}).get("weight", Decimal("0.35"))),
        raw_value=None,
        threshold=None,
        direction="neutral",
        narrative="Beta not computed in engine v1 (SPY benchmark pipeline pending).",
    ))

    total_w = sum((s.weight for s in signals), Decimal("0"))
    if total_w == 0:
        return FamilyOut("volatility_risk", Decimal("0"), signals, computable=False)
    agg = sum((s.score * s.weight for s in signals), Decimal("0")) / total_w
    return FamilyOut("volatility_risk", agg, signals, computable=True)


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------


def compute_exposure(
    session: Session,
    account_id: str,
    asset_id: str,
    cfg: dict[str, Any],
) -> FamilyOut:
    from apps.api.src.domain.ledger.pnl_calculator import compute_positions

    sig_cfg = cfg.get("signals", {})
    positions = compute_positions(session, account_id)

    total = Decimal("0")
    this_value = Decimal("0")
    found = False
    for p in positions:
        mv = p["market_value"] if p["market_value"] is not None else p["total_cost_basis"]
        total += mv
        if p["asset_id"] == asset_id:
            this_value = mv
            found = True

    if not found or total <= 0:
        return FamilyOut(
            "exposure",
            Decimal("0"),
            [SignalOut(
                factor_key="portfolio_weight",
                family="exposure",
                score=Decimal("0"),
                weight=_d(sig_cfg.get("portfolio_weight", {}).get("weight", Decimal("0.60"))),
                raw_value=None,
                threshold=None,
                direction="neutral",
                narrative="Asset not currently held; exposure neutral.",
            )],
            computable=True,
        )

    weight_pct = (this_value / total) * Decimal("100")
    max_single = _d(
        sig_cfg.get("portfolio_weight", {}).get("max_single_position_pct", Decimal("15.0"))
    )
    if weight_pct <= max_single:
        score = Decimal("0")
        direction = "neutral"
    else:
        over = (weight_pct - max_single) / max_single
        score = -_clamp(over, Decimal("0"), Decimal("1"))
        direction = "bearish"

    signal = SignalOut(
        factor_key="portfolio_weight",
        family="exposure",
        score=score,
        weight=_d(sig_cfg.get("portfolio_weight", {}).get("weight", Decimal("0.60"))),
        raw_value=weight_pct,
        threshold=max_single,
        direction=direction,
        narrative=(
            f"Position is {weight_pct:.2f}% of portfolio "
            f"(max target {max_single}%)."
        ),
    )
    return FamilyOut("exposure", score, [signal], computable=True)
