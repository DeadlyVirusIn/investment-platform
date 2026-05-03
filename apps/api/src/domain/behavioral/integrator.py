"""Behavioral integrator — runs all three Phase-B1 providers.

Pure orchestration. Does NOT merge into the model pipeline; callers
consume the returned list separately (model-only / behavioral-only /
combined evaluation is decided elsewhere).

Signature:
    generate_behavioral_signals(as_of, universe, market_context) -> list[BehavioralSignal]
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.domain.behavioral.base import (
    AssetHistory,
    BehavioralSignal,
    BehavioralSignalProvider,
    MarketContext,
    safe_mean,
)
from apps.api.src.domain.behavioral.breadth import BreadthV1, SMA_WINDOW
from apps.api.src.domain.behavioral.price_acceleration import PriceAccelerationV1
from apps.api.src.domain.behavioral.volume_anomaly import VolumeAnomalyV1

# Registry — one instance per provider. Stateless so singletons are fine.
DEFAULT_PROVIDERS: tuple[BehavioralSignalProvider, ...] = (
    VolumeAnomalyV1(),
    PriceAccelerationV1(),
    BreadthV1(),
)


# ---------------------------------------------------------------------------
# Breadth computation helper (pure — no DB)
# ---------------------------------------------------------------------------


def compute_breadth_pct_above_ma50(
    universe: list[AssetHistory], sma_window: int = SMA_WINDOW,
) -> float | None:
    """Return the fraction of the universe trading above its own `sma_window`-bar
    SMA. Returns None if fewer than 20 assets have enough history — breadth
    needs a minimum sample to be meaningful.
    """
    eligible = 0
    above = 0
    for a in universe:
        if len(a.bars) < sma_window + 1:
            continue
        closes = a.closes(sma_window)
        if len(closes) < sma_window:
            continue
        sma = safe_mean(closes)
        if sma <= 0 or a.latest is None or a.latest.close <= 0:
            continue
        eligible += 1
        if a.latest.close > sma:
            above += 1
    if eligible < 20:
        return None
    return above / eligible


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def generate_behavioral_signals(
    as_of_date: dt.date,
    universe: list[AssetHistory],
    market_context: MarketContext,
    *,
    providers: tuple[BehavioralSignalProvider, ...] | None = None,
) -> list[BehavioralSignal]:
    """Run all Phase-B1 behavioral providers and merge outputs.

    - `universe`: pre-loaded trailing price history per symbol.
    - `market_context`: market-level aggregates (breadth already computed).
    - `providers`: optional override — defaults to Phase-B1 trio.

    Does NOT touch DB. Does NOT write anywhere. Caller decides persistence.
    """
    provs = providers if providers is not None else DEFAULT_PROVIDERS
    all_signals: list[BehavioralSignal] = []
    for p in provs:
        try:
            sigs = p.generate(as_of_date, universe, market_context)
            all_signals.extend(sigs)
            logger.info(
                "[behavioral] provider={} signals={} date={}",
                p.strategy_id, len(sigs), as_of_date,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[behavioral] provider={} raised {} — skipped",
                p.strategy_id, type(exc).__name__,
            )
            continue
    return all_signals
