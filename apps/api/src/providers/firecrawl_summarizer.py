"""Firecrawl optional URL→summary helper.

Used to enrich news items with one-line summaries when the upstream
provider does not include them. NEVER the source of truth for an
event. Activated only when FIRECRAWL_API_KEY env var is set.

This is a placeholder hook — wire actual Firecrawl summarisation
when needed. For now the summarize() function is a no-op that
returns the original summary unchanged.
"""

from __future__ import annotations

import os


def _api_key() -> str:
    return os.environ.get("FIRECRAWL_API_KEY", "").strip()


def is_available() -> bool:
    return bool(_api_key())


def summarize(url: str, existing: str | None = None) -> str | None:
    """Return a one-line summary of the URL, or `existing` if disabled."""
    if not is_available():
        return existing
    # Placeholder — real Firecrawl integration goes here.
    # Until implemented, do not invent a summary.
    return existing
