"""Deterministic prompt builder for agent insights.

`build_prompt(kind, payload) -> str` is the only public entry.
It composes a markdown prompt from:

  1. A canonical header (label, banner, source endpoint,
     optional disclaimer, missing-fields note).
  2. The kind's prompt template, read from the bundled
     `prompts/<kind>.md` file.
  3. A scrubbed JSON dump of the payload as the "Facts" block.
  4. A fixed instruction footer telling the future LLM to
     summarize only from the facts and to refuse trading
     suggestions.

NO LLM call. NO DB call. NO network call. NO import from any
execution / paper-trading / options-execution / replay-recovery
module. Only stdlib + this package's siblings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import safety
from .registry import AgentKind, AgentMeta, BANNER, REGISTRY


_PROMPTS_DIR = Path(__file__).parent / "prompts"


# Numeric constants that legitimately appear inside template
# bodies (grade ladders, component caps, percent base, default
# small-sample threshold). Declared here so the safety check
# can distinguish "template-fixed" from "fabricated by the
# narrator". Keep this list narrow.
_TEMPLATE_CONSTANTS: dict[AgentKind, tuple[int, ...]] = {
    AgentKind.TRADE_QUALITY: (
        # Grade ladder thresholds and total score cap.
        100, 85, 70, 55, 40,
        # Component caps: Entry, Return, Hold, Exit, Completeness.
        20, 30, 15, 25, 10,
    ),
    # `top_5_notional` field name embeds a literal `5`.
    AgentKind.RISK_COMMENTARY: (5,),
    # Template references `0` when stating "never imply a 0% rate".
    AgentKind.EXIT_REVIEW: (0,),
    AgentKind.OPTIONS_THESIS: (),
}


# Footer instructions appended verbatim to every prompt. These
# constrain how the future LLM must behave.
_INSTRUCTIONS = (
    "## Instructions\n"
    "- Summarize only from the facts above.\n"
    "- Do NOT invent numbers, dates, prices, or P&L values.\n"
    "- Do NOT recommend trades.\n"
    "- Do NOT suggest position sizing, threshold, or risk-rule "
    "edits.\n"
    "- If a field is null or missing, state the data as "
    "unavailable.\n"
    "- Preserve any small-sample-size caveats verbatim if "
    "present.\n"
)


def _read_template(meta: AgentMeta) -> str:
    path = _PROMPTS_DIR / meta.template_path
    return path.read_text(encoding="utf-8").strip()


def _missing_required(meta: AgentMeta, scrubbed: dict) -> list[str]:
    return [
        f for f in meta.required_payload_fields
        if f not in scrubbed
    ]


def _build_narrative(
    meta: AgentMeta, scrubbed: dict, template: str,
) -> str:
    """Header + template + instructions, WITHOUT the JSON facts
    block. Hallucination check runs over this section only,
    because the JSON block is a literal serialization that may
    contain date strings whose digit components must not be
    treated as fabricated."""
    lines: list[str] = []
    lines.append(f"# {meta.label}")
    lines.append(f"Banner: {BANNER}")
    lines.append(f"Source endpoint: {meta.source_endpoint}")
    if meta.extra_disclaimer:
        lines.append(f"Disclaimer: {meta.extra_disclaimer}")
    missing = _missing_required(meta, scrubbed)
    if missing:
        lines.append(
            "Missing payload fields: "
            + ", ".join(missing)
            + " — state these as unavailable in the summary."
        )
    lines.append("")
    lines.append("## Template")
    lines.append(template)
    lines.append("")
    lines.append(_INSTRUCTIONS)
    return "\n".join(lines)


def build_prompt(kind: AgentKind, payload: dict) -> str:
    """Return a deterministic markdown prompt for `kind`.

    `payload` is expected to be the JSON-decoded body of the
    kind's source endpoint (or a single item from it). The
    payload is scrubbed before any character lands in the
    prompt; UUIDs are redacted; ID fields are replaced with
    "[redacted]"; the JSON dump uses `default=str` so any
    non-trivially-serializable values become their str() form
    rather than raising.
    """
    if not isinstance(kind, AgentKind):
        raise TypeError(
            f"kind must be AgentKind, got {type(kind).__name__}"
        )
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    meta = REGISTRY[kind]

    scrubbed = safety.scrub_sensitive_ids(payload)
    template = _read_template(meta)
    narrative = _build_narrative(meta, scrubbed, template)

    # Hard safety on the narrative (template + header +
    # instructions). The JSON facts block is checked only for
    # forbidden execution phrases, since its numeric content is
    # by construction the payload itself.
    safety.validate_no_forbidden_terms(narrative)
    safety.assert_banner_present(narrative)
    safety.assert_no_hallucinated_numbers(
        narrative, scrubbed,
        allowed_constants=_TEMPLATE_CONSTANTS[kind],
    )

    facts_json = json.dumps(
        scrubbed, indent=2, sort_keys=True, default=str,
    )
    full = (
        narrative
        + "\n## Facts (scrubbed payload)\n"
        + "```json\n"
        + facts_json
        + "\n```\n"
    )
    # Forbidden-term sweep across the full prompt — catches a
    # forbidden phrase smuggled in through a payload string
    # field (e.g., a `reason` containing "place trade").
    safety.validate_no_forbidden_terms(full)
    return full
