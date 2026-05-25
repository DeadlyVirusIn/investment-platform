"""Phase L deterministic reasoning renderer.

Pure function. Same envelope → same output. Bit-stable across runs.

Renders a ReasoningEnvelope into structured user-facing output by:
  1. Looking up the skeleton template.
  2. Resolving every vocabulary canonical_name to its display_label
     via the vocabulary_entry table.
  3. Substituting placeholders into the template.
  4. Appending invalidation, thesis, and uncertainty marker sections
     using operator-authored locked copy.

There is NO freeform text generation in this module. The output text
is determined entirely by:
  * the skeleton template (locked in skeletons.py)
  * the vocabulary display_labels (locked in DB, governed by
    vocabulary_version)
  * the uncertainty marker copy (locked in uncertainty_markers.py)
  * the thesis horizon / expected_signal phrasing (locked below)
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.reasoning.envelope import (
    ExpectedSignal, ReasoningEnvelope, ThesisHorizon,
)
from apps.api.src.reasoning.skeletons import get_skeleton
from apps.api.src.reasoning.uncertainty_markers import MARKER_COPY


# Locked operator-authored phrasing for thesis components.
_HORIZON_PHRASE: dict[ThesisHorizon, str] = {
    ThesisHorizon.INTRADAY: "within today's session",
    ThesisHorizon.SHORT_TERM: "over the next 2-5 trading days",
    ThesisHorizon.SWING: "over the next 1-3 weeks",
    ThesisHorizon.POSITION: "over multi-week horizon",
}


_EXPECTED_PHRASE: dict[ExpectedSignal, str] = {
    ExpectedSignal.PRICE_UP: "price moves higher",
    ExpectedSignal.PRICE_DOWN: "price moves lower",
    ExpectedSignal.VOLATILITY_EXPANSION: "implied volatility expands",
    ExpectedSignal.VOLATILITY_COMPRESSION: "implied volatility compresses",
    ExpectedSignal.RANGE_HOLD: "price holds the established range",
}


class RenderError(RuntimeError):
    """Raised when a vocabulary canonical_name in the envelope cannot
    be resolved against the vocabulary_entry table."""


import re as _re

_OPTIONAL_BLOCK_RE = _re.compile(r"\[\[([^\[\]]+?)\]\]")
_PLACEHOLDER_RE = _re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _resolve_optional_blocks(template: str, filled_slots: set[str]) -> str:
    """Drop [[...]] blocks whose placeholders aren't all filled; keep
    the inner text (without brackets) for blocks where every placeholder
    is filled.
    """
    def repl(m: _re.Match[str]) -> str:
        inner = m.group(1)
        needed = set(_PLACEHOLDER_RE.findall(inner))
        if needed.issubset(filled_slots):
            return inner
        return ""
    return _OPTIONAL_BLOCK_RE.sub(repl, template)


@dataclass(frozen=True)
class RenderedReasoning:
    setup: str
    thesis: str
    uncertainty: list[str]


def _resolve_labels(
    session: Session, canonical_names: set[str],
) -> dict[str, str]:
    """Batch-resolve canonical_names -> display_labels."""
    if not canonical_names:
        return {}
    rows = session.execute(
        text(
            "SELECT canonical_name, display_label FROM vocabulary_entry "
            "WHERE canonical_name = ANY(:names) AND status = 'active'"
        ),
        {"names": list(canonical_names)},
    ).all()
    return {r[0]: r[1] for r in rows}


def _collect_canonical_names(envelope: ReasoningEnvelope) -> set[str]:
    names: set[str] = set()
    for v in envelope.slot_fills.values():
        if isinstance(v, list):
            names.update(v)
        else:
            names.add(v)
    names.add(envelope.invalidation.condition_vocab)
    return names


def render(session: Session, envelope: ReasoningEnvelope) -> RenderedReasoning:
    """Render an envelope. Pure, deterministic w.r.t. (envelope, DB state)."""
    spec = get_skeleton(envelope.skeleton_id)
    names = _collect_canonical_names(envelope)
    labels = _resolve_labels(session, names)
    missing = names - labels.keys()
    if missing:
        raise RenderError(
            f"unresolved vocabulary canonical_names: {sorted(missing)}"
        )

    # Substitute slot placeholders with labels.
    sub: dict[str, str] = {}
    filled: set[str] = set()
    for slot in spec.slots:
        fill = envelope.slot_fills.get(slot.name)
        if fill is None or (isinstance(fill, list) and not fill):
            sub[slot.name] = ""
            continue
        filled.add(slot.name)
        if isinstance(fill, list):
            sub[slot.name] = ", ".join(labels[c] for c in fill)
        else:
            sub[slot.name] = labels[fill]

    # Resolve [[...]] optional blocks: keep block if all slots inside are
    # filled; drop the entire block otherwise.
    setup_text = _resolve_optional_blocks(spec.template, filled)
    setup_text = setup_text.format(**sub)
    # Collapse residual double spaces.
    setup_text = " ".join(setup_text.split())

    thesis_text = (
        f"Expectation: {_EXPECTED_PHRASE[envelope.thesis.expected_signal]} "
        f"{_HORIZON_PHRASE[envelope.thesis.horizon]}."
    )

    uncertainty_lines = [MARKER_COPY[m] for m in envelope.uncertainty_markers]

    return RenderedReasoning(
        setup=setup_text,
        thesis=thesis_text,
        uncertainty=uncertainty_lines,
    )
