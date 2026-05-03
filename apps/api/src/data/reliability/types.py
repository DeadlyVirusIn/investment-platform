"""Typed containers for reliable-value plumbing.

Every feature that feeds an engine should arrive as a `ReliableValue[T]`.
Engines consume the bundle and can:
  * gate on `bundle.confidence_score`
  * skip themselves if `bundle.has_missing_critical()`
  * degrade size if `bundle.stale_flags` non-empty
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ReliableValue(Generic[T]):
    """A single feature value carrying provenance + freshness + confidence."""

    name: str                                 # e.g. "10y_yield_5d_chg"
    value: T | None                           # None if missing
    source: str                               # provider key: "yahoo", "finnhub"
    as_of: dt.datetime | None                 # upstream timestamp
    fetched_at: dt.datetime                   # when WE observed it
    confidence: float                         # 0..1 — source-attested quality
    missing: bool = False                     # True if we fell through all providers
    stale: bool = False                       # True if older than tolerated age
    error: str | None = None                  # last provider error if any
    critical: bool = False                    # engine must skip if missing

    @property
    def usable(self) -> bool:
        return not self.missing and self.value is not None

    def degrade(self, factor: float) -> "ReliableValue[T]":
        """Return a copy with confidence scaled down (for cascaded uncertainty)."""
        new_conf = max(0.0, min(1.0, self.confidence * factor))
        return ReliableValue(
            name=self.name, value=self.value, source=self.source,
            as_of=self.as_of, fetched_at=self.fetched_at,
            confidence=new_conf, missing=self.missing, stale=self.stale,
            error=self.error, critical=self.critical,
        )


@dataclass
class DataQuality:
    """Roll-up quality stats for a bundle — stored alongside every decision."""

    confidence: float                         # bundle-level avg 0..1
    missing_fields: list[str] = field(default_factory=list)
    stale_fields: list[str] = field(default_factory=list)
    degraded_fields: list[str] = field(default_factory=list)
    provider_usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": round(self.confidence, 4),
            "missing_fields": list(self.missing_fields),
            "stale_fields": list(self.stale_fields),
            "degraded_fields": list(self.degraded_fields),
            "provider_usage": dict(self.provider_usage),
        }

    def has_missing_critical(self) -> bool:
        return len(self.missing_fields) > 0


@dataclass
class ReliableBundle:
    """Named collection of reliable values produced for a single engine run."""

    values: dict[str, ReliableValue[Any]] = field(default_factory=dict)

    def put(self, rv: ReliableValue[Any]) -> None:
        self.values[rv.name] = rv

    def get(self, name: str) -> ReliableValue[Any] | None:
        return self.values.get(name)

    def raw(self, name: str, default: Any = None) -> Any:
        rv = self.values.get(name)
        if rv is None or not rv.usable:
            return default
        return rv.value

    def quality(self) -> DataQuality:
        if not self.values:
            return DataQuality(confidence=0.0)
        missing = [n for n, v in self.values.items() if v.missing]
        stale = [n for n, v in self.values.items() if v.stale]
        degraded = [n for n, v in self.values.items()
                    if v.confidence < 1.0 and not v.missing]
        usage: dict[str, int] = {}
        usable_confidences: list[float] = []
        for v in self.values.values():
            usage[v.source] = usage.get(v.source, 0) + 1
            if v.usable:
                usable_confidences.append(v.confidence)
        conf = (sum(usable_confidences) / len(usable_confidences)
                if usable_confidences else 0.0)
        # Missing criticals hard-cap confidence
        critical_missing = [v for v in self.values.values()
                            if v.missing and v.critical]
        if critical_missing:
            conf = 0.0
        return DataQuality(
            confidence=conf,
            missing_fields=[n for n, v in self.values.items()
                            if v.missing and v.critical] + [
                            n for n, v in self.values.items()
                            if v.missing and not v.critical],
            stale_fields=stale,
            degraded_fields=degraded,
            provider_usage=usage,
        )

    def critical_missing(self) -> list[str]:
        return [n for n, v in self.values.items() if v.missing and v.critical]
