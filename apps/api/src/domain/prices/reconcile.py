"""Dedupe + source-priority policy.

Two stages:
  1. dedupe_payload: collapse a single provider's payload down to one bar per
     date (in case the provider returns dupes). Keep the most complete row.
  2. should_upsert: decide whether an incoming bar should overwrite an
     existing DB row based on source priority + completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from apps.api.src.domain.prices.canonical import CanonicalBar, source_priority


def _completeness(bar: CanonicalBar) -> tuple[int, int]:
    """Higher-is-better completeness tuple: (adj_close_present, volume_present)."""
    return (
        1 if bar.adjusted_close is not None else 0,
        1 if bar.volume is not None else 0,
    )


def dedupe_payload(bars: Iterable[CanonicalBar]) -> list[CanonicalBar]:
    """Collapse dupes per trade_date. Keep highest-completeness row; tie-break
    to higher source priority, then last-seen."""
    best: dict = {}
    for b in bars:
        key = b.trade_date
        existing = best.get(key)
        if existing is None:
            best[key] = b
            continue
        # Prefer completeness, then higher source priority
        if (
            _completeness(b) > _completeness(existing)
            or (
                _completeness(b) == _completeness(existing)
                and source_priority(b.source) > source_priority(existing.source)
            )
        ):
            best[key] = b
    return sorted(best.values(), key=lambda b: b.trade_date)


@dataclass
class ExistingBar:
    """Lean view of a DB row used by should_upsert."""
    source: str
    open: Decimal | None
    close: Decimal | None
    adjusted_close: Decimal | None
    volume: int | None


def is_complete(b: ExistingBar | CanonicalBar) -> bool:
    if isinstance(b, ExistingBar):
        return (
            b.open is not None
            and b.close is not None
            and b.close > 0
            and b.adjusted_close is not None
        )
    return (
        b.open is not None
        and b.close is not None
        and b.close > 0
        and b.adjusted_close is not None
    )


def should_upsert(incoming: CanonicalBar, existing: ExistingBar | None) -> bool:
    """Decide whether to write the incoming bar.

    Rules:
      - If no existing row → write.
      - Same source → always overwrite (update with freshest data).
      - Higher source priority → overwrite.
      - Lower source priority → overwrite ONLY if existing is incomplete.
    """
    if existing is None:
        return True
    if incoming.source == existing.source:
        return True
    incoming_pri = source_priority(incoming.source)
    existing_pri = source_priority(existing.source)
    if incoming_pri > existing_pri:
        return True
    if incoming_pri < existing_pri:
        # Lower priority — only write if existing row is incomplete
        return not is_complete(existing)
    # Equal priority but different source name → prefer completeness
    return _completeness(incoming) > _completeness_of_existing(existing)


def _completeness_of_existing(e: ExistingBar) -> tuple[int, int]:
    return (
        1 if e.adjusted_close is not None else 0,
        1 if e.volume is not None else 0,
    )
