"""Phase L state-label substates — locked enum.

Per PHASE_L_3_V_VOCABULARY.md §X: 6 closed-frozen substates that drive
every user-facing surface's state banner.

DO NOT extend without constitutional amendment.
"""

from __future__ import annotations

from enum import Enum


class StateLabelSubstate(str, Enum):
    """Six locked substates. Surface state-banner content derives from this."""

    LIVE_FRESH = "live_fresh"
    """AI is paper-trading; latest decision within 24 trading hours."""

    LIVE_STALE = "live_stale"
    """AI is paper-trading; latest decision 24-72 trading hours ago."""

    LIVE_DORMANT = "live_dormant"
    """Engine alive but no decisions > 72 trading hours."""

    OBSERVING = "observing"
    """Today is a trading day; engine healthy; no decisions yet today."""

    LEARNING = "learning"
    """Educational/reference content surface (Concepts, Playbooks)."""

    EXPERIMENTAL = "experimental"
    """Research preview or pre-canary (e.g. options surfaces pre-Phase-1A/1B)."""


# Mapping to user-facing labels (locked vocabulary; do not paraphrase).
SUBSTATE_LABELS: dict[StateLabelSubstate, str] = {
    StateLabelSubstate.LIVE_FRESH: "Live",
    StateLabelSubstate.LIVE_STALE: "Live · data lagging",
    StateLabelSubstate.LIVE_DORMANT: "Observing · AI quiet",
    StateLabelSubstate.OBSERVING: "Observing",
    StateLabelSubstate.LEARNING: "Learning",
    StateLabelSubstate.EXPERIMENTAL: "Experimental",
}
