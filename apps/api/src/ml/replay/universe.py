"""Historical replay universe — explicit, small, survivorship-aware."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

DEFAULT_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "SPY", "QQQ",
]


@dataclass(frozen=True)
class Universe:
    symbols: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_list(self) -> list[str]:
        return list(self.symbols)


def resolve_universe(
    *,
    explicit: Sequence[str] | None = None,
    max_symbols: int | None = None,
) -> Universe:
    """Build a universe for replay. Explicit list wins; else env var;
    else DEFAULT_UNIVERSE. Always surfaces survivorship-bias warning."""
    warnings: list[str] = []

    if explicit:
        symbols = [s.strip().upper() for s in explicit if s.strip()]
    else:
        env = os.getenv("ML_REPLAY_UNIVERSE", "").strip()
        if env:
            symbols = [s.strip().upper() for s in env.split(",") if s.strip()]
        else:
            symbols = list(DEFAULT_UNIVERSE)

    if not symbols:
        warnings.append("universe resolved to empty — replay will no-op")
    if max_symbols is not None and max_symbols > 0:
        cap = int(max_symbols)
        if len(symbols) > cap:
            warnings.append(
                f"universe capped from {len(symbols)} to {cap}"
            )
            symbols = symbols[:cap]

    # Survivorship-bias warning — current watchlist applied to historical dates
    warnings.append(
        "survivorship bias: current-era symbols applied to historical "
        "dates; delisted/renamed names missing; replay is for system "
        "calibration, not academic proof"
    )
    return Universe(
        symbols=tuple(dict.fromkeys(symbols)),   # preserve order, unique
        warnings=tuple(warnings),
    )
