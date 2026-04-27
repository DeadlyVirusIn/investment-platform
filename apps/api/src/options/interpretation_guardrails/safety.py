"""Safety helpers (Phase 11K).

Pure-fn module. Stdlib only. NEVER mutates DB.

Provides:
  * `detect_selection_bias(filter_state)` — returns the list of
    triggers that flag a narrow review view (only HIGH_REVIEW_
    PRIORITY bucket, only one bucket selected, score-desc sort).
  * `is_recommendation_language(text)` — basic word scan helper
    used by the verification tests + by callers that want to
    sanity-check upstream text.
"""

from __future__ import annotations

import re
from typing import Any

from apps.api.src.options.decision_support.buckets import (
    BUCKET_HIGH_REVIEW_PRIORITY,
)


# Frozen list of trigger codes
TRIGGER_ONLY_HIGH_PRIORITY      = "ONLY_HIGH_REVIEW_PRIORITY_BUCKET"
TRIGGER_SCORE_DESC_SORT_ACTIVE  = "SCORE_DESC_SORT_ACTIVE"
TRIGGER_ONLY_ONE_BUCKET         = "ONLY_ONE_BUCKET_SELECTED"


def detect_selection_bias(filter_state: dict[str, Any]) -> list[str]:
    """Return the list of trigger codes that fire for the given
    filter state.

    `filter_state` keys recognised:
      * bucket_filter   — single bucket token, "ALL", or None
      * selected_buckets — list of bucket tokens (multi-select form)
      * sort_mode       — "SCORE_DESC" or other; default sort is desc

    The detector NEVER mutates state. It is deterministic.
    """
    triggers: list[str] = []
    bucket_filter = filter_state.get("bucket_filter")
    selected = filter_state.get("selected_buckets") or []
    sort_mode = filter_state.get("sort_mode") or "SCORE_DESC"

    if bucket_filter == BUCKET_HIGH_REVIEW_PRIORITY:
        triggers.append(TRIGGER_ONLY_HIGH_PRIORITY)
    elif (len(selected) == 1
          and selected[0] == BUCKET_HIGH_REVIEW_PRIORITY):
        triggers.append(TRIGGER_ONLY_HIGH_PRIORITY)

    if sort_mode == "SCORE_DESC":
        triggers.append(TRIGGER_SCORE_DESC_SORT_ACTIVE)

    if (bucket_filter and bucket_filter != "ALL"
            and bucket_filter != BUCKET_HIGH_REVIEW_PRIORITY):
        triggers.append(TRIGGER_ONLY_ONE_BUCKET)
    elif (len(selected) == 1
          and selected[0] != BUCKET_HIGH_REVIEW_PRIORITY):
        triggers.append(TRIGGER_ONLY_ONE_BUCKET)

    return triggers


# ---------------------------------------------------------------------------
# Recommendation-language scan helper (used by tests + sanity-checks)
# ---------------------------------------------------------------------------

_RECOMMENDATION_PATTERNS = (
    r"\brecommended\b",
    r"\brecommendation\b",
    r"\bbest trade\b",
    r"\btop pick\b",
    r"\btrade now\b",
    r"\bsignal\b",
    r"\bconfidence\b",
    r"\bauto-?trade\b",
    r"\bplace order\b",
    r"\benter (?:a |the )?trade\b",
    r"\bexit (?:a |the )?trade\b",
)


def is_recommendation_language(text: str) -> bool:
    """Return True if `text` contains recommendation/action wording
    that is NOT explicitly negated. Used in tests + caller sanity
    checks.

    Negation lookbehind window covers a single sentence (200 chars,
    bounded by `.`) so that "do not constitute X, Y, or Z" suppresses
    every match in the clause chain.
    """
    if not text:
        return False
    for pat in _RECOMMENDATION_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            preceding = text[max(0, m.start() - 200): m.start()].lower()
            last_period = preceding.rfind(".")
            scope = preceding[last_period + 1:] if last_period >= 0 else preceding
            if any(neg in scope for neg in (
                " not ", "n't ", "never ",
                "do not ", "does not ", "did not ",
                "is not ", "are not ", "was not ", "were not ",
                "not a ", "not an ", "not the ",
            )):
                continue
            return True
    return False
