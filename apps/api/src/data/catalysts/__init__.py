"""Catalyst intelligence — compress news + earnings into trade-policy hints.

Free-tier providers first (Finnhub, Yahoo). Paid providers pluggable via the
`CATALYST_PROVIDER_PRIORITY` env var once keys are available.
"""

from apps.api.src.data.catalysts.types import (
    CatalystSummary, Headline, UpcomingEvent, TradePolicy,
)
from apps.api.src.data.catalysts.service import CatalystService, get_catalyst_service

__all__ = [
    "CatalystSummary", "Headline", "UpcomingEvent", "TradePolicy",
    "CatalystService", "get_catalyst_service",
]
