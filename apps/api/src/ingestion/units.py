"""Value-unit enum + canonical normalization for consensus/actual values.

Canonical units:
  - EPS:     `usd_per_share`  (stored value == reported EPS in USD)
  - Revenue: `usd_raw`         (stored value == revenue in USD, NOT millions)

Rationale for `usd_raw`: eliminates the "in what multiple?" question at
read time. `Numeric(20,6)` can hold trillions with room; no precision loss.

STRICT policy: ingestion MUST carry an explicit unit. Missing or ambiguous
unit → record is quarantined, never silently coerced.
"""

from __future__ import annotations

from enum import Enum


class ValueUnit(str, Enum):
    USD_PER_SHARE = "usd_per_share"   # EPS canonical
    USD_RAW = "usd_raw"                # Revenue canonical
    USD_MILLIONS = "usd_millions"      # source unit for revenue; converted
    USD_BILLIONS = "usd_billions"      # source unit for revenue; converted
    USD_THOUSANDS = "usd_thousands"    # source unit for revenue; converted


# Allowed unit per metric (metric → set of acceptable input units)
_ALLOWED_UNITS: dict[str, set[ValueUnit]] = {
    "eps": {ValueUnit.USD_PER_SHARE},
    "revenue": {
        ValueUnit.USD_RAW,
        ValueUnit.USD_MILLIONS,
        ValueUnit.USD_BILLIONS,
        ValueUnit.USD_THOUSANDS,
    },
}

_CANONICAL: dict[str, ValueUnit] = {
    "eps": ValueUnit.USD_PER_SHARE,
    "revenue": ValueUnit.USD_RAW,
}


class UnitError(ValueError):
    """Raised when unit is missing, ambiguous, or incompatible with metric."""


def canonical_unit_for(metric: str) -> ValueUnit:
    return _CANONICAL[metric]


def normalize_to_canonical(
    metric: str, value: float, unit: ValueUnit,
) -> tuple[float, ValueUnit]:
    """Return (normalized_value, canonical_unit). Raises UnitError if the
    input unit is not allowed for the metric (cross-check).
    """
    allowed = _ALLOWED_UNITS.get(metric)
    if allowed is None:
        raise UnitError(f"unknown metric: {metric!r}")
    if unit not in allowed:
        raise UnitError(
            f"unit {unit.value!r} not allowed for metric {metric!r}; "
            f"allowed: {[u.value for u in allowed]}"
        )

    canonical = _CANONICAL[metric]
    if unit == canonical:
        return float(value), canonical

    # Revenue scale conversions → USD_RAW
    if canonical == ValueUnit.USD_RAW:
        if unit == ValueUnit.USD_MILLIONS:
            return float(value) * 1e6, canonical
        if unit == ValueUnit.USD_BILLIONS:
            return float(value) * 1e9, canonical
        if unit == ValueUnit.USD_THOUSANDS:
            return float(value) * 1e3, canonical

    # Anything else is an unhandled mapping — fail fast
    raise UnitError(
        f"no conversion from {unit.value!r} to {canonical.value!r}"
    )


def parse_unit(v) -> ValueUnit:
    """Strict parser: accepts ValueUnit instance or exact string enum value.
    Missing / bad → UnitError."""
    if v is None or v == "":
        raise UnitError("missing value_unit")
    if isinstance(v, ValueUnit):
        return v
    try:
        return ValueUnit(v)
    except ValueError:
        raise UnitError(f"unknown value_unit: {v!r}")
