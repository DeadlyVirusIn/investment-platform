"""Entry quality + paper-slippage simulation.

Slippage applied ONLY to analytics by default. Execution path untouched.
`PAPER_APPLY_SLIPPAGE_EXECUTION=false` (hard default) — the code path to
change live behavior requires explicit operator toggle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EntryQuality:
    symbol: str
    entry_price: float
    next_price: float | None
    adverse_move_bps: float | None
    slippage_estimate_bps: float | None
    quality_score: float                     # 0..1 higher = better
    flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "next_price": self.next_price,
            "adverse_move_bps": self.adverse_move_bps,
            "slippage_estimate_bps": self.slippage_estimate_bps,
            "quality_score": round(self.quality_score, 4),
            "flags": list(self.flags),
        }


def compute_entry_quality(
    *,
    symbol: str,
    entry_price: float,
    next_price: float | None,
    configured_slippage_bps: float = 5.0,
    chase_threshold_bps: float = 30.0,
    late_entry_threshold_bps: float = 50.0,
) -> EntryQuality:
    flags: list[str] = []
    if entry_price is None or entry_price <= 0:
        return EntryQuality(
            symbol=symbol, entry_price=entry_price or 0.0,
            next_price=next_price, adverse_move_bps=None,
            slippage_estimate_bps=None, quality_score=0.0,
            flags=["invalid_entry_price"],
        )
    adverse_bps: float | None = None
    if next_price is not None and next_price > 0:
        move = (next_price / entry_price) - 1.0
        adverse_bps = move * 10_000.0
        if adverse_bps <= -late_entry_threshold_bps:
            flags.append("late_entry_adverse_move")
        elif adverse_bps <= -chase_threshold_bps:
            flags.append("possible_chase")

    # Quality score: 1.0 baseline, penalise adverse moves + slippage
    q = 1.0
    if adverse_bps is not None and adverse_bps < 0:
        q += adverse_bps / 200.0        # -100 bps → -0.5
    q -= configured_slippage_bps / 200.0
    q = max(0.0, min(1.0, q))

    return EntryQuality(
        symbol=symbol,
        entry_price=entry_price,
        next_price=next_price,
        adverse_move_bps=adverse_bps,
        slippage_estimate_bps=configured_slippage_bps,
        quality_score=q,
        flags=flags,
    )


def simulate_paper_slippage(
    *, raw_price: float, side: str,
    slippage_bps: float,
) -> float:
    """Return adjusted fill price. 'buy' → worse=higher, 'sell' → worse=lower."""
    if raw_price <= 0:
        return raw_price
    factor = slippage_bps / 10_000.0
    if side.lower() in {"buy", "long", "enter_long"}:
        return raw_price * (1.0 + factor)
    return raw_price * (1.0 - factor)
