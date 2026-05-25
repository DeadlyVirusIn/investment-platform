"""Phase L reasoning skeleton catalog — locked.

A skeleton is a fixed template for how the AI's reasoning about a
single decision is structured. Slots are filled with vocabulary entries
(from vocabulary_entry) at render time. There is NO freeform LLM prose.

MVP locks 6 skeletons. Each one corresponds to a recognizable trade
shape. Adding a skeleton requires a constitutional amendment.

Slots are typed by VocabularyType (signal | regime | strategy_family |
invalidation_trigger).

Render templates use {slot_name} placeholders that the deterministic
renderer (apps/api/src/reasoning/renderer.py) substitutes with the
vocabulary entry's display_label.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SkeletonId(str, Enum):
    MOMENTUM_BREAKOUT = "momentum_breakout"
    MEAN_REVERSION_PULLBACK = "mean_reversion_pullback"
    BREADTH_THRUST_ENTRY = "breadth_thrust_entry"
    IV_COMPRESSION_SETUP = "iv_compression_setup"
    CATALYST_ANTICIPATION = "catalyst_anticipation"
    REGIME_ALIGNED_CONTINUATION = "regime_aligned_continuation"


class SlotVocabType(str, Enum):
    """Which vocabulary table a slot draws from."""
    SIGNAL = "signal"
    REGIME = "regime"
    STRATEGY_FAMILY = "strategy_family"
    INVALIDATION_TRIGGER = "invalidation_trigger"


@dataclass(frozen=True)
class SlotSpec:
    name: str
    vocab_type: SlotVocabType
    required: bool
    multi: bool = False           # True => list of vocab refs
    max_items: int | None = None  # only meaningful when multi=True


@dataclass(frozen=True)
class SkeletonSpec:
    id: SkeletonId
    display_name: str
    slots: tuple[SlotSpec, ...]
    template: str                 # render template with {slot} placeholders


CATALOG: dict[SkeletonId, SkeletonSpec] = {
    SkeletonId.MOMENTUM_BREAKOUT: SkeletonSpec(
        id=SkeletonId.MOMENTUM_BREAKOUT,
        display_name="Momentum breakout",
        slots=(
            SlotSpec("trigger_signal", SlotVocabType.SIGNAL, required=True),
            SlotSpec("confirming_signals", SlotVocabType.SIGNAL, required=False, multi=True, max_items=3),
            SlotSpec("invalidation_condition", SlotVocabType.INVALIDATION_TRIGGER, required=True),
        ),
        template=(
            "Entered on {trigger_signal}. "
            "[[Confirmed by: {confirming_signals}.]] "
            "Exits if {invalidation_condition}."
        ),
    ),
    SkeletonId.MEAN_REVERSION_PULLBACK: SkeletonSpec(
        id=SkeletonId.MEAN_REVERSION_PULLBACK,
        display_name="Mean-reversion pullback",
        slots=(
            SlotSpec("trigger_signal", SlotVocabType.SIGNAL, required=True),
            SlotSpec("regime_context", SlotVocabType.REGIME, required=True),
            SlotSpec("invalidation_condition", SlotVocabType.INVALIDATION_TRIGGER, required=True),
        ),
        template=(
            "Pullback entry on {trigger_signal} inside {regime_context}. "
            "Exits if {invalidation_condition}."
        ),
    ),
    SkeletonId.BREADTH_THRUST_ENTRY: SkeletonSpec(
        id=SkeletonId.BREADTH_THRUST_ENTRY,
        display_name="Breadth-thrust entry",
        slots=(
            SlotSpec("trigger_signal", SlotVocabType.SIGNAL, required=True),
            SlotSpec("confirming_signals", SlotVocabType.SIGNAL, required=False, multi=True, max_items=2),
            SlotSpec("invalidation_condition", SlotVocabType.INVALIDATION_TRIGGER, required=True),
        ),
        template=(
            "Breadth thrust: {trigger_signal}. "
            "[[Supported by: {confirming_signals}.]] "
            "Exits if {invalidation_condition}."
        ),
    ),
    SkeletonId.IV_COMPRESSION_SETUP: SkeletonSpec(
        id=SkeletonId.IV_COMPRESSION_SETUP,
        display_name="IV compression setup",
        slots=(
            SlotSpec("trigger_signal", SlotVocabType.SIGNAL, required=True),
            SlotSpec("invalidation_condition", SlotVocabType.INVALIDATION_TRIGGER, required=True),
        ),
        template=(
            "Setup: {trigger_signal} — option premium has compressed. "
            "Position closes if {invalidation_condition}."
        ),
    ),
    SkeletonId.CATALYST_ANTICIPATION: SkeletonSpec(
        id=SkeletonId.CATALYST_ANTICIPATION,
        display_name="Catalyst anticipation",
        slots=(
            SlotSpec("trigger_signal", SlotVocabType.SIGNAL, required=True),
            SlotSpec("invalidation_condition", SlotVocabType.INVALIDATION_TRIGGER, required=True),
        ),
        template=(
            "Anticipating {trigger_signal}. "
            "Position closes if {invalidation_condition}."
        ),
    ),
    SkeletonId.REGIME_ALIGNED_CONTINUATION: SkeletonSpec(
        id=SkeletonId.REGIME_ALIGNED_CONTINUATION,
        display_name="Regime-aligned continuation",
        slots=(
            SlotSpec("regime_context", SlotVocabType.REGIME, required=True),
            SlotSpec("trigger_signal", SlotVocabType.SIGNAL, required=True),
            SlotSpec("invalidation_condition", SlotVocabType.INVALIDATION_TRIGGER, required=True),
        ),
        template=(
            "Continuation inside {regime_context} on {trigger_signal}. "
            "Exits if {invalidation_condition}."
        ),
    ),
}


def get_skeleton(skeleton_id: SkeletonId | str) -> SkeletonSpec:
    """Resolve a SkeletonSpec from either enum or canonical string id."""
    if isinstance(skeleton_id, str):
        skeleton_id = SkeletonId(skeleton_id)
    spec = CATALOG.get(skeleton_id)
    if spec is None:
        raise KeyError(f"unknown skeleton_id: {skeleton_id}")
    return spec
