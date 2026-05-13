"""Gating tests for credential-redaction safeguards.

These tests MUST pass before any adapter is permitted to log or raise.
Cover the five requirements listed in user approval:
  1. Bearer tokens scrubbed
  2. query-string tokens scrubbed
  3. stack traces cannot leak tokens
  4. loguru extras cannot leak tokens
  5. safe_url() strips query params entirely
"""

from __future__ import annotations

import io
import re

from loguru import logger

from apps.api.src.options.data_provider._redact import (
    redact_token,
    safe_url,
    safe_logger,
)


# Test fixtures — synthetic non-secret tokens (40-char fake)
_FAKE_TOKEN_40 = "abcdefghij0123456789abcdefghij0123456789"
_FAKE_TOKEN_60 = "x" * 60
_TOKEN_SHAPE_RE = re.compile(r"\b[A-Za-z0-9]{32,80}\b")


# ---------------------------------------------------------------------------
# 1. Bearer tokens scrubbed
# ---------------------------------------------------------------------------

def test_bearer_token_scrubbed_inline():
    out = redact_token(f"Authorization: Bearer {_FAKE_TOKEN_40}")
    assert _FAKE_TOKEN_40 not in out
    assert "<REDACTED>" in out


def test_bearer_lowercase_scrubbed():
    out = redact_token(f"sent header: bearer {_FAKE_TOKEN_40} to api")
    assert _FAKE_TOKEN_40 not in out


def test_bearer_in_traceback_repr_scrubbed():
    fake_trace = (
        "Traceback ...\n"
        f"  raise HTTPStatusError('401 for /api?token={_FAKE_TOKEN_40}')\n"
        f"  Authorization: Bearer {_FAKE_TOKEN_40}\n"
    )
    out = redact_token(fake_trace)
    assert _FAKE_TOKEN_40 not in out, out


# ---------------------------------------------------------------------------
# 2. Query-string tokens scrubbed
# ---------------------------------------------------------------------------

def test_query_token_param_scrubbed():
    url = f"https://finnhub.io/api/v1/x?symbol=SPY&token={_FAKE_TOKEN_40}"
    out = redact_token(url)
    assert _FAKE_TOKEN_40 not in out
    assert "token=<REDACTED>" in out


def test_query_access_token_scrubbed():
    out = redact_token(f"GET /x?access_token={_FAKE_TOKEN_40}&foo=bar")
    assert _FAKE_TOKEN_40 not in out
    assert "access_token=<REDACTED>" in out


def test_query_api_key_param_scrubbed():
    out = redact_token(f"https://x.com/?apikey={_FAKE_TOKEN_40}")
    assert _FAKE_TOKEN_40 not in out


# ---------------------------------------------------------------------------
# 3. Stack-trace-style strings — bare tokens scrubbed
# ---------------------------------------------------------------------------

def test_bare_token_in_arbitrary_text_scrubbed():
    out = redact_token(f"unexpected value: {_FAKE_TOKEN_40} in body")
    assert _FAKE_TOKEN_40 not in out
    assert "<REDACTED:40>" in out


def test_long_token_scrubbed():
    out = redact_token(f"key: {_FAKE_TOKEN_60} done")
    assert _FAKE_TOKEN_60 not in out


def test_short_identifier_not_scrubbed():
    # UUID with dashes — should not match the bare-token pattern
    uuid_ish = "550e8400-e29b-41d4-a716-446655440000"
    out = redact_token(f"asset_id={uuid_ish}")
    assert uuid_ish in out, "UUIDs are not tokens; do not redact"


def test_normal_short_strings_preserved():
    src = "engine_state=dormant scheduler_jobs_count=0 options_enabled=False"
    assert redact_token(src) == src


# ---------------------------------------------------------------------------
# 4. loguru extras (bind kwargs) — cannot leak tokens
# ---------------------------------------------------------------------------

def test_safe_logger_message_scrubbed_at_emit(capfd):
    """When safe_logger.info embeds a token in the message, the sink
    output must NOT contain the token. Uses loguru's default stderr sink."""
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")
    try:
        safe_logger.info(f"calling api with token {_FAKE_TOKEN_40}")
    finally:
        logger.remove(handler_id)
    out = sink.getvalue()
    assert _FAKE_TOKEN_40 not in out, out


def test_safe_logger_bind_extras_scrubbed():
    sink = io.StringIO()
    handler_id = logger.add(
        sink,
        format="{message} | extras={extra}",
    )
    try:
        bound = safe_logger.bind(secret=_FAKE_TOKEN_40, normal="ok")
        bound.info("event happened")
    finally:
        logger.remove(handler_id)
    out = sink.getvalue()
    assert _FAKE_TOKEN_40 not in out, out
    assert "normal" in out, "non-secret bind extras still emitted"


def test_safe_logger_positional_args_scrubbed():
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")
    try:
        safe_logger.warning("status={} key={}", 200, _FAKE_TOKEN_40)
    finally:
        logger.remove(handler_id)
    out = sink.getvalue()
    assert _FAKE_TOKEN_40 not in out


# ---------------------------------------------------------------------------
# 5. safe_url() strips query entirely
# ---------------------------------------------------------------------------

def test_safe_url_strips_query():
    u = f"https://finnhub.io/api/v1/stock/option-chain?symbol=SPY&token={_FAKE_TOKEN_40}"
    out = safe_url(u)
    assert "token=" not in out
    assert _FAKE_TOKEN_40 not in out
    assert out == "https://finnhub.io/api/v1/stock/option-chain"


def test_safe_url_preserves_path_and_fragment():
    u = f"https://x.com/a/b/c?secret={_FAKE_TOKEN_40}#section-1"
    out = safe_url(u)
    assert out == "https://x.com/a/b/c#section-1"


def test_safe_url_handles_none():
    assert safe_url(None) == ""


def test_safe_url_accepts_httpx_url(monkeypatch):
    # httpx.URL objects are stringifiable — ensure safe_url handles them
    class _FakeURL:
        def __str__(self) -> str:
            return f"https://x.com/p?token={_FAKE_TOKEN_40}"

    assert safe_url(_FakeURL()) == "https://x.com/p"


# ---------------------------------------------------------------------------
# Cross-check: combined message types
# ---------------------------------------------------------------------------

def test_multiple_tokens_all_scrubbed():
    msg = (
        f"auth=Bearer {_FAKE_TOKEN_40} "
        f"and url=?token={_FAKE_TOKEN_40[::-1]} "
        f"and stray={_FAKE_TOKEN_60}"
    )
    out = redact_token(msg)
    assert _FAKE_TOKEN_40 not in out
    assert _FAKE_TOKEN_40[::-1] not in out
    assert _FAKE_TOKEN_60 not in out


def test_redact_preserves_non_token_chars():
    """Whitespace, punctuation, normal-length idents preserved."""
    src = "GET /v1/markets/clock\nstatus: 200\nbody: ok"
    assert redact_token(src) == src
