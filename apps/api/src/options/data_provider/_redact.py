"""Token / credential redaction for options-provider adapter logs.

Three layers of defense-in-depth so a leaked token cannot escape the
adapter boundary via:

  1. raw log messages              → `redact_token()` regex scrub
  2. exception messages re-raised  → `redact_token()` applied at boundary
  3. URLs printed in tracebacks    → `safe_url()` strips query string
  4. loguru bound extras           → `safe_logger` wrapper applies same
                                     scrub to extras before emit

Token regex matches:
  * `Bearer <token>` headers (case-insensitive)
  * `?token=…` / `?access_token=…` / `?api_key=…` query params
  * any bare 32–80 char alphanumeric block (catches typical API tokens
    of length 40, AWS-style 20-char IDs are intentionally NOT matched
    to avoid false-positives on short identifiers)

NEVER imports any I/O / DB / network module. Pure-fn.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from loguru import logger as _loguru_logger


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# `Bearer <token>` — group(1) captures the token portion
_BEARER_RE = re.compile(
    r"(?i)\bBearer\s+([A-Za-z0-9._\-+/=]{8,})"
)

# Query-string secret params — group(2) is the param name, group(3) the value.
# CASE-INSENSITIVE (Polygon uses `apiKey` with a capital K — the prior
# case-sensitive pattern missed it, which is how a live key reached the logs).
# Value class includes % + . _ - so percent-encoded values AND keys containing
# underscores/dots are matched. Param name is anchored right after ? or & so
# `sort_key=` / `ticker=` are NOT falsely matched.
_QUERY_PARAM_RE = re.compile(
    r"(?i)([?&])("
    r"api[-_]?key|apikey|access[-_]?token|refresh[-_]?token|token|"
    r"client[-_]?secret|secret|signature|sig|password|passwd|pwd|auth|key"
    r")=([^&#\s\"'<>]+)"
)

# Bare long alphanumeric tokens (32–80 chars). Bounded by word boundaries
# so embedded ID-style substrings (e.g. 'orderId12345') are unaffected.
# Lower bound 32 is high enough to skip typical UUIDs (length 36 fits;
# UUIDs also contain dashes so the alnum-only pattern usually skips
# them — confirmed by the unit tests).
_BARE_TOKEN_RE = re.compile(
    r"\b[A-Za-z0-9]{32,80}\b"
)

# Authorization / api-key header lines (logs / repr / dict output). Matches
# `Authorization: Bearer X`, `X-Api-Key: X`, `api_key: X`, `"token": "X"`.
_AUTH_HEADER_RE = re.compile(
    r"(?i)(Authorization\s*:\s*Bearer\s+)([A-Za-z0-9._\-+/=]+)"
)
_HEADER_SECRET_RE = re.compile(
    r"(?i)((?:x-api-key|api[-_]?key|x-auth-token|access[-_]?token|token|secret)"
    r"[\"']?\s*[:=]\s*[\"']?)([A-Za-z0-9._\-+/=]{6,})"
)

# Bounded output — a single log line / stored error can never exceed this.
_MAX_REDACTED_LEN = 4000


# ---------------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------------

def redact_token(text: str | None) -> str:
    """Scrub any token-shaped substring from `text`. Returns a NEW
    string; never mutates input.

    Replacement strategy:
      * `Bearer XXXX`             → `Bearer <REDACTED>`
      * `?token=XXXX`             → `?token=<REDACTED>`
      * `Authorization: Bearer X` → `Authorization: Bearer <REDACTED>`
      * bare 32–80 char alnum     → `<REDACTED:N>` where N=len
    """
    if text is None:
        return ""
    s = str(text)
    s = _AUTH_HEADER_RE.sub(r"\1<REDACTED>", s)
    s = _BEARER_RE.sub("Bearer <REDACTED>", s)
    s = _QUERY_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}=<REDACTED>", s)
    s = _HEADER_SECRET_RE.sub(lambda m: f"{m.group(1)}<REDACTED>", s)
    s = _BARE_TOKEN_RE.sub(lambda m: f"<REDACTED:{len(m.group(0))}>", s)
    return s[:_MAX_REDACTED_LEN]


def safe_url(url: Any) -> str:
    """Strip query string from a URL repr. Path-only.

    Accepts anything with `__str__`. Returns a string that contains
    scheme + netloc + path + (optional fragment) but NEVER the query.
    """
    if url is None:
        return ""
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))


# ---------------------------------------------------------------------------
# safe_logger — loguru wrapper that scrubs every emitted message + extras
# ---------------------------------------------------------------------------

class _SafeLogger:
    """Thin proxy over loguru.logger that applies `redact_token` to
    every message (string OR f-string template substituted args) and
    to every value in `bind(...)` extras.

    Methods exposed: `info`, `warning`, `error`, `debug`, `bind`.
    Anything else falls through to the wrapped logger (read-only).
    """

    __slots__ = ("_logger",)

    def __init__(self, wrapped=None) -> None:
        self._logger = wrapped or _loguru_logger

    # -------- log-level methods --------

    def _emit(self, level: str, msg: Any, *args, **kwargs) -> None:
        # Format the message; substitute any positional args first
        # (loguru supports `.info("x={}", v)` style). Then scrub.
        try:
            if args:
                text = str(msg).format(*args)
            else:
                text = str(msg)
        except (IndexError, KeyError):
            # Bad format string — preserve raw to aid debugging,
            # but still scrub.
            text = str(msg)
        scrubbed = redact_token(text)
        # Drop any kwargs that smell like leaked tokens before emit
        getattr(self._logger, level)(scrubbed, **_scrub_kwargs(kwargs))

    def info(self, msg, *a, **kw):    self._emit("info",    msg, *a, **kw)
    def warning(self, msg, *a, **kw): self._emit("warning", msg, *a, **kw)
    def error(self, msg, *a, **kw):   self._emit("error",   msg, *a, **kw)
    def debug(self, msg, *a, **kw):   self._emit("debug",   msg, *a, **kw)

    # -------- bind() --------

    def bind(self, **kwargs):
        """Return a new SafeLogger whose underlying logger has the
        (scrubbed) extras bound. Token-shaped values are redacted
        BEFORE binding so they cannot reach the sink unredacted."""
        clean = {k: redact_token(str(v)) if isinstance(v, str) else v
                 for k, v in kwargs.items()}
        return _SafeLogger(self._logger.bind(**clean))


def _scrub_kwargs(kw: dict) -> dict:
    """Drop / redact any kwarg whose value looks like a token.
    Loguru's `**kwargs` to logging methods are bound as extras."""
    out: dict[str, Any] = {}
    for k, v in kw.items():
        if isinstance(v, str):
            out[k] = redact_token(v)
        else:
            out[k] = v
    return out


# Singleton import target — adapters do `from ._redact import safe_logger`
safe_logger = _SafeLogger()


# ---------------------------------------------------------------------------
# Global boundary — a loguru patcher that scrubs EVERY emitted record's
# message, regardless of which module logged it. This is the single choke
# point that guarantees a provider exception string (e.g. an httpx
# `raise_for_status()` error carrying `…apiKey=…` in the URL) can never reach
# a sink unredacted, without every call site having to remember to scrub.
# Install once at process start (api + worker main), AFTER logger.add().
# ---------------------------------------------------------------------------
def _redaction_patcher(record: "dict") -> None:  # loguru Record is a dict
    msg = record.get("message")
    if msg:
        record["message"] = redact_token(msg)


def install_global_redaction(target_logger=None):
    """Attach the redaction patcher to loguru globally. Idempotent:
    re-calling replaces the patcher with the same function. Does not touch
    existing sinks (configure only sets the patcher when handlers is omitted)."""
    lg = target_logger or _loguru_logger
    lg.configure(patcher=_redaction_patcher)
    return lg


def redact_error_for_storage(text: str | None) -> str:
    """Scrub + bound a string destined for durable storage (job_run.
    error_message, agent_audit, etc.) — the DB path does NOT pass through the
    loguru patcher, so writers must call this explicitly."""
    return redact_token(text)


__all__ = [
    "redact_token",
    "safe_url",
    "safe_logger",
    "install_global_redaction",
    "redact_error_for_storage",
]
