"""Data reliability layer — every value carries source/freshness/confidence.

Goal: Engine C (and any future engine) MUST NEVER crash on missing or stale
upstream data. Feature values flow through this layer as `ReliableValue`
objects carrying enough metadata to degrade gracefully.
"""

from apps.api.src.data.reliability.types import (
    ReliableValue, ReliableBundle, DataQuality,
)
from apps.api.src.data.reliability.chain import (
    FallbackChain, ProviderResult, ProviderError, StaleData, MissingData,
)
from apps.api.src.data.reliability.cache import TimedCache

__all__ = [
    "ReliableValue", "ReliableBundle", "DataQuality",
    "FallbackChain", "ProviderResult",
    "ProviderError", "StaleData", "MissingData",
    "TimedCache",
]
