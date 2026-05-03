"""Bar validation. Hard rejects return False; soft warnings are listed."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from apps.api.src.domain.prices.canonical import CanonicalBar

LARGE_MOVE_THRESHOLD = Decimal("0.30")  # 30% day-over-day = suspicious


@dataclass
class ValidationResult:
    ok: bool
    reject_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def validate_bar(
    bar: CanonicalBar,
    *,
    prior_close: Decimal | None = None,
) -> ValidationResult:
    # Hard rejects
    if bar.trade_date is None:
        return ValidationResult(False, "missing trade_date")
    if bar.open is None or bar.high is None or bar.low is None or bar.close is None:
        return ValidationResult(False, "missing OHLC")
    if bar.open <= 0:
        return ValidationResult(False, "open <= 0")
    if bar.close <= 0:
        return ValidationResult(False, "close <= 0")
    if bar.high < bar.low:
        return ValidationResult(False, "high < low")
    if bar.high < max(bar.open, bar.close):
        return ValidationResult(False, "high < max(open, close)")
    if bar.low > min(bar.open, bar.close):
        return ValidationResult(False, "low > min(open, close)")

    warnings: list[str] = []
    if bar.volume is None:
        warnings.append("missing volume")
    if bar.adjusted_close is None:
        warnings.append("missing adjusted_close")

    if prior_close is not None and prior_close > 0:
        change = abs(bar.close - prior_close) / prior_close
        if change >= LARGE_MOVE_THRESHOLD:
            warnings.append(f"large_move {change:.2%} vs prior close")

    return ValidationResult(True, None, warnings)


def validate_batch(
    bars: list[CanonicalBar],
) -> tuple[list[CanonicalBar], list[tuple[CanonicalBar, ValidationResult]]]:
    """Return (accepted, rejected_pairs). Soft warnings attach to accepted bars
    for logging elsewhere — ValidationResult can be carried by the caller if
    needed. Here we surface only the reject partition."""
    sorted_bars = sorted(bars, key=lambda b: b.trade_date)
    accepted: list[CanonicalBar] = []
    rejected: list[tuple[CanonicalBar, ValidationResult]] = []
    prior: Decimal | None = None
    for b in sorted_bars:
        res = validate_bar(b, prior_close=prior)
        if res.ok:
            accepted.append(b)
            prior = b.close
        else:
            rejected.append((b, res))
    return accepted, rejected
