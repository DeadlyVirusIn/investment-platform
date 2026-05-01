"""Phase 11W (Phase D.1) — controlled prompt templates.

Phase D.1 ships exactly ONE template. Future phases may add more
behind their own approval gates.

The template body is written WITHOUT any forbidden token, so a
generic source-grep CI gate would never flag this file. Where a
neutral concept is required, alternate wording is used (e.g.
"directional guidance" instead of the forbidden directional verbs).

Hash discipline: `prompt_hash` is computed over the FULLY-RENDERED
prompt (template + interpolated inputs). Computation lives in
`apps.api.src.research.provenance.compute_prompt_hash`. The LLM
payload's prompt-hash field, if any, is NEVER trusted at the
persister layer.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Final


PROMPT_TEMPLATE_ID: Final[str] = "single_asset_context_note_v1"
PROMPT_TEMPLATE_VERSION: Final[int] = 1


# The literal template. Mandatory constraints embedded in the
# instructions; the safety layer treats these as advisory and
# re-validates the model's output independently.
SINGLE_ASSET_CONTEXT_NOTE_V1: Final[str] = """\
You produce read-only research context for one equity ticker.

Inputs:
- Symbol: {symbol}
- As-of date: {as_of}
- Public asset metadata (JSON): {asset_meta_json}
- Macro context gates as-of (JSON): {context_gates_json}
- Linked candidate idea metadata (JSON, optional): {candidate_json}

Task:
Write one neutral paragraph (no more than 180 words) describing
data points and context differences relevant to the symbol on the
given date.

Mandatory constraints:
- Provide observation only.
- No directional guidance of any kind.
- No price thresholds, ranges, or numerical predictions.
- No sizing, weighting, or portfolio instructions.
- No reference to future transactions or carrying out trades.
- No language that could be interpreted as an instruction to act.
- Each material claim must be attributable to a data source listed
  in inputs.

Output format:
A single plain-text paragraph. No bullet lists. No headings.
"""


def render_single_asset_context_note(
    *,
    symbol: str,
    as_of: dt.date,
    asset_meta: dict[str, Any] | None,
    context_gates: dict[str, Any] | None,
    candidate: dict[str, Any] | None = None,
) -> str:
    """Render the template with bound inputs. Deterministic: same
    arguments → identical output bytes. Dicts are serialized with
    sorted keys so insertion order does not perturb the rendered
    string."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol must be a non-empty str")
    if not isinstance(as_of, dt.date):
        raise ValueError("as_of must be a datetime.date")

    return SINGLE_ASSET_CONTEXT_NOTE_V1.format(
        symbol=symbol,
        as_of=as_of.isoformat(),
        asset_meta_json=json.dumps(
            asset_meta or {}, sort_keys=True, default=str,
        ),
        context_gates_json=json.dumps(
            context_gates or {}, sort_keys=True, default=str,
        ),
        candidate_json=json.dumps(
            candidate or {}, sort_keys=True, default=str,
        ),
    )
