"""Phase L truth-banner catalog.

Per PHASE_L_3_V_VOCABULARY.md §X: 8 closed-stable banner causes with
operator-authored content. One-banner-per-surface priority rule
(L.4-F §VI Pattern 5 / L.4-R §5) enforced at render layer.

Priority order (most-severe first; the first match wins per surface):
  1. engine_error                 P0
  2. stale_data_universe_wide     P1
  3. pre_canary_options           P2 (options surfaces only)
  4. engine_dormant               P2
  5. incomplete_lifecycle         P3
  6. stale_data_single_name       P3
  7. operator_intervention_active P3
  8. post_loss_position           P4
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TruthBannerCause(str, Enum):
    ENGINE_ERROR = "engine_error"
    STALE_DATA_UNIVERSE_WIDE = "stale_data_universe_wide"
    PRE_CANARY_OPTIONS = "pre_canary_options"
    ENGINE_DORMANT = "engine_dormant"
    INCOMPLETE_LIFECYCLE = "incomplete_lifecycle"
    STALE_DATA_SINGLE_NAME = "stale_data_single_name"
    OPERATOR_INTERVENTION_ACTIVE = "operator_intervention_active"
    POST_LOSS_POSITION = "post_loss_position"


# Priority order — lower number = higher severity = wins under
# one-banner-per-surface rule.
PRIORITY: dict[TruthBannerCause, int] = {
    TruthBannerCause.ENGINE_ERROR: 1,
    TruthBannerCause.STALE_DATA_UNIVERSE_WIDE: 2,
    TruthBannerCause.PRE_CANARY_OPTIONS: 3,
    TruthBannerCause.ENGINE_DORMANT: 4,
    TruthBannerCause.INCOMPLETE_LIFECYCLE: 5,
    TruthBannerCause.STALE_DATA_SINGLE_NAME: 6,
    TruthBannerCause.OPERATOR_INTERVENTION_ACTIVE: 7,
    TruthBannerCause.POST_LOSS_POSITION: 8,
}


@dataclass(frozen=True)
class BannerContent:
    cause: TruthBannerCause
    short_label: str
    long_text: str


# Locked, operator-authored copy. Tonal range per L.2-E §VII:
# carefully honest, never apologetic.
CATALOG: dict[TruthBannerCause, BannerContent] = {
    TruthBannerCause.ENGINE_ERROR: BannerContent(
        cause=TruthBannerCause.ENGINE_ERROR,
        short_label="The engine had a problem",
        long_text=(
            "Something interrupted the AI's reasoning today. We've paused "
            "decisions until it's resolved. What you see below may be "
            "stale."
        ),
    ),
    TruthBannerCause.STALE_DATA_UNIVERSE_WIDE: BannerContent(
        cause=TruthBannerCause.STALE_DATA_UNIVERSE_WIDE,
        short_label="Data is behind",
        long_text=(
            "We're a few hours behind on market data. The numbers below "
            "are the latest we have — they may not reflect right now."
        ),
    ),
    TruthBannerCause.PRE_CANARY_OPTIONS: BannerContent(
        cause=TruthBannerCause.PRE_CANARY_OPTIONS,
        short_label="Options not in service yet",
        long_text=(
            "Options paper-trading isn't live yet. What you see below "
            "is research the AI is doing, not trades it's making."
        ),
    ),
    TruthBannerCause.ENGINE_DORMANT: BannerContent(
        cause=TruthBannerCause.ENGINE_DORMANT,
        short_label="The AI's been quiet",
        long_text=(
            "We haven't traded in a while. The tape hasn't given us "
            "anything we'd act on. We'll let you know when that changes."
        ),
    ),
    TruthBannerCause.INCOMPLETE_LIFECYCLE: BannerContent(
        cause=TruthBannerCause.INCOMPLETE_LIFECYCLE,
        short_label="Part of this is still being built",
        long_text=(
            "This surface is in progress. What you see is honest about "
            "what's working today — and clear about what isn't."
        ),
    ),
    TruthBannerCause.STALE_DATA_SINGLE_NAME: BannerContent(
        cause=TruthBannerCause.STALE_DATA_SINGLE_NAME,
        short_label="One quote is behind",
        long_text=(
            "We're waiting on a fresh quote for this position. The "
            "value shown is the last good price."
        ),
    ),
    TruthBannerCause.OPERATOR_INTERVENTION_ACTIVE: BannerContent(
        cause=TruthBannerCause.OPERATOR_INTERVENTION_ACTIVE,
        short_label="A human is intervening",
        long_text=(
            "An operator is currently making a manual adjustment. "
            "Normal AI decisions will resume shortly."
        ),
    ),
    TruthBannerCause.POST_LOSS_POSITION: BannerContent(
        cause=TruthBannerCause.POST_LOSS_POSITION,
        short_label="We took a loss here",
        long_text=(
            "This position closed at a loss. The Decision Detail page "
            "explains what we missed."
        ),
    ),
}


def resolve_priority(causes: list[TruthBannerCause]) -> TruthBannerCause | None:
    """Apply one-banner-per-surface rule: return the highest-priority cause."""
    if not causes:
        return None
    return min(causes, key=lambda c: PRIORITY[c])
