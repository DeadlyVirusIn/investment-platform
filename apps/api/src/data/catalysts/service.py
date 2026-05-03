"""CatalystService — fetches per-symbol summary with provider fallback + cache.

Priority order comes from `settings.CATALYST_PROVIDER_PRIORITY`
(comma-separated). Unknown providers are skipped. Empty priority →
everything neutral, system still works.

This service is the ONLY place engines / API endpoints call for catalyst
data. It never raises — it returns a neutral `CatalystSummary` on total
failure with `partial=True` so callers can log data_confidence.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

from loguru import logger

from apps.api.src.data.catalysts.providers.finnhub import FinnhubProvider
from apps.api.src.data.catalysts.providers.yahoo import YahooProvider
from apps.api.src.data.catalysts.providers.base import CatalystProvider
from apps.api.src.data.catalysts.scoring import build_summary
from apps.api.src.data.catalysts.types import (
    CatalystSummary, Headline, UpcomingEvent, TradePolicy,
)
from apps.api.src.data.reliability.cache import TimedCache
from apps.api.src.data.reliability.chain import ProviderError

# Per-process cache. Symbol-level. Covers duplicate requests inside a single
# /api/catalysts/top call + short browser-refresh bursts.
_EVENT_CACHE: TimedCache[UpcomingEvent | None] = TimedCache(dt.timedelta(minutes=45))
_NEWS_CACHE: TimedCache[list[Headline]] = TimedCache(dt.timedelta(minutes=20))
_SUMMARY_CACHE: TimedCache[CatalystSummary] = TimedCache(dt.timedelta(minutes=10))

_PROVIDER_BUILDERS: dict[str, Any] = {
    "finnhub": lambda: FinnhubProvider(os.getenv("FINNHUB_API_KEY", "")),
    "yahoo":   lambda: YahooProvider(),
}


def _default_priority() -> list[str]:
    raw = os.getenv("CATALYST_PROVIDER_PRIORITY", "finnhub,yahoo")
    return [p.strip() for p in raw.split(",") if p.strip()]


class CatalystService:
    def __init__(self, priority: list[str] | None = None):
        order = priority or _default_priority()
        self._providers: list[CatalystProvider] = []
        for key in order:
            builder = _PROVIDER_BUILDERS.get(key)
            if builder is None:
                logger.warning("catalyst: unknown provider '{}' skipped", key)
                continue
            try:
                self._providers.append(builder())
            except Exception as e:
                logger.warning(
                    "catalyst: provider '{}' init failed: {}", key, e,
                )
        if not self._providers:
            logger.warning("catalyst: no providers available — neutral output only")

    # ------ public ------

    def summary_for(self, symbol: str) -> CatalystSummary:
        """Return a catalyst summary for a single symbol. Never raises."""
        symbol = symbol.upper()
        return _SUMMARY_CACHE.get_or_build(
            key=symbol, build=lambda: self._compute(symbol),
        )

    def summaries_for(self, symbols: list[str]) -> list[CatalystSummary]:
        return [self.summary_for(s) for s in symbols]

    # ------ internal ------

    def _compute(self, symbol: str) -> CatalystSummary:
        now = dt.datetime.now(dt.timezone.utc)
        providers_used: list[str] = []
        partial = False

        # Earnings — try providers in order
        next_event: UpcomingEvent | None = None
        for p in self._providers:
            try:
                next_event = _EVENT_CACHE.get_or_build(
                    key=f"{p.name}:{symbol}:event",
                    build=lambda p=p: p.fetch_next_event(symbol),
                )
                providers_used.append(f"{p.name}:event")
                break
            except ProviderError as e:
                logger.debug("catalyst: {} event {}: {}", p.name, symbol, e)
                partial = True
                continue
            except Exception as e:
                logger.warning(
                    "catalyst: {} crashed on {} event: {}", p.name, symbol, e,
                )
                partial = True
                continue
        else:
            # No provider returned an event — not fatal
            pass

        # Headlines — aggregate (keep first non-empty batch)
        headlines: list[Headline] = []
        for p in self._providers:
            try:
                got = _NEWS_CACHE.get_or_build(
                    key=f"{p.name}:{symbol}:news",
                    build=lambda p=p: p.fetch_recent_headlines(symbol, limit=3),
                )
                if got:
                    headlines = got
                    providers_used.append(f"{p.name}:news")
                    break
            except ProviderError as e:
                logger.debug("catalyst: {} news {}: {}", p.name, symbol, e)
                partial = True
                continue
            except Exception as e:
                logger.warning(
                    "catalyst: {} crashed on {} news: {}", p.name, symbol, e,
                )
                partial = True
                continue

        data_conf = _confidence_from_providers(
            has_event=next_event is not None,
            has_news=bool(headlines),
            partial=partial,
            any_provider_up=bool(providers_used),
        )

        return build_summary(
            symbol=symbol,
            now=now,
            next_event=next_event,
            headlines=headlines,
            data_confidence=data_conf,
            providers_used=providers_used,
            partial=partial,
        )


def _confidence_from_providers(
    *, has_event: bool, has_news: bool,
    partial: bool, any_provider_up: bool,
) -> float:
    if not any_provider_up:
        return 0.0
    score = 0.6                                      # baseline when a provider responded
    if has_event: score += 0.25
    if has_news:  score += 0.15
    if partial:   score *= 0.85
    return max(0.0, min(1.0, score))


# ---- module-level singleton accessor ----

_singleton: CatalystService | None = None


def get_catalyst_service() -> CatalystService:
    global _singleton
    if _singleton is None:
        _singleton = CatalystService()
    return _singleton


# Re-export for convenience
__all__ = [
    "CatalystService", "get_catalyst_service",
    "CatalystSummary", "TradePolicy",
]
