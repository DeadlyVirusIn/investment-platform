"""In-process TTL cache — cheap, thread-unsafe, sufficient for single-worker API.

DB-backed cache lives elsewhere (market_series_observation, features_daily etc.).
This is only for request-scoped provider reuse — e.g., Finnhub's earnings endpoint
called several times inside one /api/catalysts/top call.
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: dt.datetime


class TimedCache(Generic[T]):
    def __init__(self, ttl: dt.timedelta):
        self._ttl = ttl
        self._store: dict[str, _Entry[T]] = {}
        self._lock = threading.Lock()

    def get_or_build(self, key: str, build: Callable[[], T]) -> T:
        now = dt.datetime.now(dt.timezone.utc)
        with self._lock:
            entry = self._store.get(key)
            if entry and entry.expires_at > now:
                return entry.value
        # Build outside lock
        value = build()
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=now + self._ttl)
        return value

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"size": len(self._store)}
