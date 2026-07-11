"""Honest paper-execution costs (Elite ArthOS Priority 3, default OFF).

Forensics (docs/research/MODEL_AND_DATA_FORENSICS.md §9): the canonical
nightly paper track records zero-cost next-bar-open fills — ``submit_trade``
has a ``commission`` param defaulting to 0 and no slippage model at all.
This module supplies a deterministic, liquidity-aware cost model that the
fill path applies ONLY when ``settings.PAPER_COST_MODEL_ENABLED`` is true.

Model (all Decimal, pure, no randomness — same-inputs → same-outputs):

    gross_notional = quantity * fill_price

    liquidity model (avg_dollar_volume known and > 0):
        raw_bps      = k_bps * sqrt(gross_notional / avg_dollar_volume)
        slippage_bps = clamp(raw_bps, floor=spread_floor_bps,
                                       cap=slippage_cap_bps)
    fallback (no volume data):
        slippage_bps = spread_floor_bps          # flat, deterministic

    commission     = gross_notional * commission_bps / 10_000
    effective fill = fill_price * (1 + sign * slippage_bps / 10_000)
        sign = +1 buy, -1 sell  →  slippage is ALWAYS adverse
        (buys fill higher, sells fill lower).

Concept lineage: the floor value mirrors the weekly-rebalance cost model
(``stock_engine/portfolio/cost_model.py`` — ``max(2bps, …)``); the impact
term here is the standard square-root participation law instead of the
linear ADV term because the bare nightly path has no same-bar H/L spread
proxy contract (open-only fills).

All costs are enforced non-negative. Nothing here touches the DB except
the explicit ``avg_dollar_volume_for_asset`` helper.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import PriceBar

_BPS = Decimal("10000")
_ZERO = Decimal("0")

# Version of THIS cost model implementation, stamped into
# paper_trade.execution_cost_json so every cost-enabled fill durably
# reconstructs even across model/config churn. Bump on ANY formula change.
COST_MODEL_VERSION = "pc-1"
# Quantization matched to the paper_trade columns so the stamped row
# round-trips exactly: fill_price/commission Numeric(20,6), slippage_bps
# Numeric(10,4).
_MONEY_Q = Decimal("0.000001")
_PRICE_Q = Decimal("0.000001")
_BPS_Q = Decimal("0.0001")

ADV_LOOKBACK_BARS = 20


def _dec(v: object) -> Decimal:
    if v is None:
        return _ZERO
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostConfig:
    """Cost-model knobs. Defaults mirror the settings defaults (OFF)."""

    enabled: bool = False
    commission_bps: Decimal = Decimal("0")
    spread_floor_bps: Decimal = Decimal("2")
    slippage_cap_bps: Decimal = Decimal("50")
    impact_k_bps: Decimal = Decimal("10")

    @classmethod
    def from_settings(cls, settings: object) -> "CostConfig":
        return cls(
            enabled=bool(getattr(settings, "PAPER_COST_MODEL_ENABLED", False)),
            commission_bps=_dec(getattr(settings, "PAPER_COMMISSION_BPS", 0)),
            spread_floor_bps=_dec(getattr(settings, "PAPER_SPREAD_FLOOR_BPS", 2)),
            slippage_cap_bps=_dec(getattr(settings, "PAPER_SLIPPAGE_CAP_BPS", 50)),
            impact_k_bps=_dec(getattr(settings, "PAPER_IMPACT_K_BPS", 10)),
        )


def load_cost_config() -> CostConfig:
    """Read the live settings singleton at call time (monkeypatch-friendly)."""
    from apps.api.src.config import settings  # local import — no cycle at import time

    return CostConfig.from_settings(settings)


# ---------------------------------------------------------------------------
# Breakdown
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostBreakdown:
    commission: Decimal
    slippage: Decimal
    total: Decimal
    gross_notional: Decimal
    net_notional: Decimal
    model: str  # 'liquidity' | 'fallback'
    slippage_bps: Decimal
    effective_fill_price: Decimal

    def as_stamp(self, *, raw_fill_price: Decimal, config: "CostConfig") -> dict[str, str]:
        """Durable JSON stamp for paper_trade.execution_cost_json — the full
        audit record for one cost-enabled fill. Everything a reconstruction
        needs, all as exact Decimal strings (never floats):
        gross/commission/slippage/total/net, the raw (pre-cost) and effective
        fill prices, and the model version + configuration that produced them.
        """
        return {
            "version": COST_MODEL_VERSION,
            "model": self.model,
            "raw_fill_price": str(raw_fill_price),
            "effective_fill_price": str(self.effective_fill_price),
            "slippage_bps": str(self.slippage_bps),
            "gross_notional": str(self.gross_notional),
            "commission": str(self.commission),
            "slippage_cost": str(self.slippage),
            "total_cost": str(self.total),
            "net_notional": str(self.net_notional),
            "config": {
                "commission_bps": str(config.commission_bps),
                "spread_floor_bps": str(config.spread_floor_bps),
                "slippage_cap_bps": str(config.slippage_cap_bps),
                "impact_k_bps": str(config.impact_k_bps),
            },
        }

    def as_log_fields(self) -> dict[str, str]:
        return {
            "model": self.model,
            "slippage_bps": str(self.slippage_bps),
            "commission": str(self.commission),
            "slippage": str(self.slippage),
            "total": str(self.total),
            "gross_notional": str(self.gross_notional),
            "net_notional": str(self.net_notional),
            "effective_fill_price": str(self.effective_fill_price),
        }


def compute_fill_costs(
    side: str,
    quantity: Decimal,
    fill_price: Decimal,
    *,
    avg_dollar_volume: Decimal | None,
    config: CostConfig,
) -> CostBreakdown:
    """Deterministic execution-cost breakdown for one fill.

    ``fill_price`` is the raw (pre-cost) next-bar-open price. Slippage is
    always adverse: the effective fill is above ``fill_price`` for buys and
    below it for sells. ``net_notional`` is the actual cash impact:
    buy → ``qty*effective + commission`` (cash out), sell →
    ``qty*effective - commission`` (cash in, floored at 0).
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"unknown side: {side!r}")
    qty = _dec(quantity)
    price = _dec(fill_price)
    if qty <= 0:
        raise ValueError("quantity must be positive")
    if price <= 0:
        raise ValueError("fill_price must be positive")

    gross = qty * price
    floor_bps = max(config.spread_floor_bps, _ZERO)
    cap_bps = max(config.slippage_cap_bps, _ZERO)

    adv = _dec(avg_dollar_volume) if avg_dollar_volume is not None else _ZERO
    if adv > 0:
        model = "liquidity"
        raw_bps = config.impact_k_bps * (gross / adv).sqrt()
        slippage_bps = max(raw_bps, floor_bps)
    else:
        model = "fallback"
        slippage_bps = floor_bps
    slippage_bps = min(slippage_bps, cap_bps)
    if slippage_bps < 0:
        slippage_bps = _ZERO
    slippage_bps = slippage_bps.quantize(_BPS_Q)

    sign = Decimal("1") if side == "buy" else Decimal("-1")
    effective = (price * (Decimal("1") + sign * slippage_bps / _BPS)).quantize(_PRICE_Q)
    if effective <= 0:
        raise ValueError(
            "effective fill price non-positive — slippage cap too large for price"
        )

    # Slippage cost = adverse price move × quantity; non-negative by
    # construction, clamped anyway (quantization safety).
    slippage_cost = (sign * (effective - price) * qty).quantize(_MONEY_Q)
    if slippage_cost < 0:
        slippage_cost = _ZERO

    commission = (gross * max(config.commission_bps, _ZERO) / _BPS).quantize(_MONEY_Q)
    if commission < 0:
        commission = _ZERO

    if side == "buy":
        net = qty * effective + commission
    else:
        net = qty * effective - commission
        if net < 0:
            net = _ZERO

    return CostBreakdown(
        commission=commission,
        slippage=slippage_cost,
        total=commission + slippage_cost,
        gross_notional=gross,
        net_notional=net,
        model=model,
        slippage_bps=slippage_bps,
        effective_fill_price=effective,
    )


# ---------------------------------------------------------------------------
# Liquidity lookup (only DB touchpoint — used by the submit_trade wiring)
# ---------------------------------------------------------------------------


def avg_dollar_volume_for_asset(
    session: Session,
    asset_id: str,
    as_of: dt.datetime,
    n_bars: int = ADV_LOOKBACK_BARS,
) -> Decimal | None:
    """Mean (volume × close) over the last ``n_bars`` daily bars with
    ``ts <= as_of`` (submission-time knowledge — no lookahead into the fill
    bar). Returns None when no bar has positive dollar volume, which routes
    the cost model to the deterministic fallback."""
    bars = session.scalars(
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts <= as_of,
        )
        .order_by(PriceBar.ts.desc())
        .limit(n_bars)
    ).all()
    dollar_volumes: list[Decimal] = []
    for bar in bars:
        if bar.volume is None:
            continue
        px = bar.close if bar.close is not None else bar.open
        if px is None:
            continue
        dv = _dec(bar.volume) * _dec(px)
        if dv > 0:
            dollar_volumes.append(dv)
    if not dollar_volumes:
        return None
    return sum(dollar_volumes, _ZERO) / Decimal(len(dollar_volumes))
