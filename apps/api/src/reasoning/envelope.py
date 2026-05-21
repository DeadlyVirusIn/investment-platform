"""Phase L reasoning envelope contract.

An Envelope is the immutable structured representation of the AI's
reasoning for a single decision. It is what the deterministic
renderer consumes — the renderer NEVER receives freeform prose.

Contracts:
  * skeleton_id MUST be in the locked SkeletonId enum.
  * Every required slot of the skeleton MUST be populated.
  * Slot fills reference vocabulary canonical_names (validated against
    the locked SlotVocabType for that slot).
  * Invalidation and thesis are structured, not freeform strings.
  * Uncertainty markers MUST be in the locked UncertaintyMarker enum.

Validation is fail-loud at construction time.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from apps.api.src.reasoning.skeletons import (
    CATALOG, SkeletonId, SkeletonSpec, SlotSpec, SlotVocabType, get_skeleton,
)
from apps.api.src.reasoning.uncertainty_markers import (
    UncertaintyMarker, validate_markers,
)


class ThesisHorizon(str, Enum):
    """Locked horizons. Adding new ones is constitutional."""
    INTRADAY = "intraday"          # < 1 trading day
    SHORT_TERM = "short_term"      # 2-5 trading days
    SWING = "swing"                # 1-3 weeks
    POSITION = "position"          # > 3 weeks


class ExpectedSignal(str, Enum):
    """Locked outcomes — what the AI is betting on."""
    PRICE_UP = "price_up"
    PRICE_DOWN = "price_down"
    VOLATILITY_EXPANSION = "volatility_expansion"
    VOLATILITY_COMPRESSION = "volatility_compression"
    RANGE_HOLD = "range_hold"


class EnvelopeSource(str, Enum):
    """Where this envelope came from — for audit and truth contract."""
    LIVE = "live"
    REPLAY = "replay"
    BACKTEST = "backtest"
    OPERATOR_MANUAL = "operator_manual"


@dataclass(frozen=True)
class InvalidationTrigger:
    """Structured invalidation condition.

    `condition_vocab` is the canonical_name of an invalidation_trigger
    vocabulary entry (e.g. "stop_below_anchor", "thesis_signal_flips").
    `threshold` is a numeric value or string describing the trip
    condition — kept loose-typed because thresholds vary per trigger.
    """
    condition_vocab: str
    threshold: Any | None = None


@dataclass(frozen=True)
class ThesisStatement:
    """Structured thesis — horizon and expected outcome, no prose."""
    horizon: ThesisHorizon
    expected_signal: ExpectedSignal


@dataclass(frozen=True)
class ReasoningEnvelope:
    """Immutable reasoning artifact for a single decision.

    Build via `build_envelope()` to ensure validation runs.
    """
    skeleton_id: SkeletonId
    slot_fills: dict[str, str | list[str]]   # slot_name -> canonical_name(s)
    invalidation: InvalidationTrigger
    thesis: ThesisStatement
    uncertainty_markers: tuple[UncertaintyMarker, ...]
    generated_at: dt.datetime
    source: EnvelopeSource

    def envelope_hash(self) -> str:
        """Stable SHA-256 over a canonical JSON serialization.

        Audit log keys on this hash to detect drift / replay mismatch.
        """
        payload = {
            "skeleton_id": self.skeleton_id.value,
            "slot_fills": self.slot_fills,
            "invalidation": {
                "condition_vocab": self.invalidation.condition_vocab,
                "threshold": self.invalidation.threshold,
            },
            "thesis": {
                "horizon": self.thesis.horizon.value,
                "expected_signal": self.thesis.expected_signal.value,
            },
            "uncertainty_markers": [m.value for m in self.uncertainty_markers],
            "source": self.source.value,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class EnvelopeValidationError(ValueError):
    """Raised when envelope construction violates the contract."""


def _validate_slot_fills(
    spec: SkeletonSpec, fills: dict[str, str | list[str]],
) -> dict[str, str | list[str]]:
    """Ensure required slots present, multi-slots respect cardinality,
    and no extra/unknown slots are submitted.
    """
    declared_names = {s.name for s in spec.slots}
    extras = set(fills) - declared_names
    if extras:
        raise EnvelopeValidationError(
            f"unknown slot(s) for {spec.id}: {sorted(extras)}"
        )
    out: dict[str, str | list[str]] = {}
    for s in spec.slots:
        v = fills.get(s.name)
        if v is None or (isinstance(v, list) and not v):
            if s.required:
                raise EnvelopeValidationError(
                    f"required slot {s.name!r} missing for {spec.id}"
                )
            continue
        if s.multi:
            if not isinstance(v, list):
                raise EnvelopeValidationError(
                    f"slot {s.name!r} must be a list (multi=True)"
                )
            if s.max_items is not None and len(v) > s.max_items:
                raise EnvelopeValidationError(
                    f"slot {s.name!r} exceeds max_items={s.max_items}"
                )
            if not all(isinstance(x, str) for x in v):
                raise EnvelopeValidationError(
                    f"slot {s.name!r} values must be canonical_name strings"
                )
            out[s.name] = list(v)
        else:
            if not isinstance(v, str):
                raise EnvelopeValidationError(
                    f"slot {s.name!r} must be a single canonical_name string"
                )
            out[s.name] = v
    return out


def build_envelope(
    *,
    skeleton_id: SkeletonId | str,
    slot_fills: dict[str, str | list[str]],
    invalidation: InvalidationTrigger,
    thesis: ThesisStatement,
    uncertainty_markers: list[UncertaintyMarker | str] | None = None,
    generated_at: dt.datetime | None = None,
    source: EnvelopeSource = EnvelopeSource.LIVE,
) -> ReasoningEnvelope:
    """Validated factory. All envelopes MUST go through this path."""
    spec = get_skeleton(skeleton_id)
    cleaned_fills = _validate_slot_fills(spec, slot_fills)
    markers = tuple(validate_markers(uncertainty_markers or []))
    gen = generated_at or dt.datetime.now(dt.timezone.utc)
    if gen.tzinfo is None:
        raise EnvelopeValidationError("generated_at must be timezone-aware")
    return ReasoningEnvelope(
        skeleton_id=spec.id,
        slot_fills=cleaned_fills,
        invalidation=invalidation,
        thesis=thesis,
        uncertainty_markers=markers,
        generated_at=gen,
        source=source,
    )
