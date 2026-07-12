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


# ---------------------------------------------------------------------------
# Incident 2026-07-11 — Polygon apiKey leak. Hostile cases the prior
# case-sensitive pattern missed (apiKey capital-K + underscore in value).
# ---------------------------------------------------------------------------

# realistic shape: 32 chars including an underscore (bare-token regex misses
# it; only the query-param scrub catches it)
_POLY_KEY = "5lXPS8ka_mXSB2HcNt1HfZ35JLhIxLG0"


def test_polygon_apikey_mixed_case_query_scrubbed():
    url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/minute/2026-07-11/2026-07-11?adjusted=true&sort=desc&limit=30&apiKey={_POLY_KEY}"
    out = redact_token(url)
    assert _POLY_KEY not in out
    assert "apiKey=<REDACTED>" in out
    # host + path + non-secret params preserved
    assert "api.polygon.io" in out and "adjusted=true" in out and "limit=30" in out


def test_httpx_raise_for_status_string_scrubbed():
    # the exact leak format seen in prod logs
    s = (f"Client error '403 Forbidden' for url "
         f"'https://api.polygon.io/v2/aggs/ticker/QQQ/range/1/minute/"
         f"2026-07-11/2026-07-11?adjusted=true&apiKey={_POLY_KEY}'")
    out = redact_token(s)
    assert _POLY_KEY not in out
    assert "403 Forbidden" in out  # useful diagnostic preserved


def test_param_order_independent():
    a = redact_token(f"?apiKey={_POLY_KEY}&sort=asc")
    b = redact_token(f"?sort=asc&apiKey={_POLY_KEY}")
    assert _POLY_KEY not in a and _POLY_KEY not in b


def test_percent_encoded_key_scrubbed():
    enc = "AbC%2Fd3f%2BXX99kkllmmnnoopp00112233"
    out = redact_token(f"https://x.io/a?api_key={enc}&z=1")
    assert enc not in out and "api_key=<REDACTED>" in out and "z=1" in out


def test_duplicate_secret_params_all_scrubbed():
    out = redact_token(f"?apiKey={_POLY_KEY}&other=1&apikey={_POLY_KEY[::-1]}")
    assert _POLY_KEY not in out and _POLY_KEY[::-1] not in out
    assert out.count("<REDACTED>") >= 2


def test_case_variants_of_param_names():
    for name in ("APIKEY", "Api_Key", "ACCESS_TOKEN", "Token", "KEY", "secret"):
        out = redact_token(f"?{name}={_FAKE_TOKEN_40}&keep=ok")
        assert _FAKE_TOKEN_40 not in out, name
        assert "keep=ok" in out


def test_header_form_secrets_scrubbed():
    for line in (f"X-Api-Key: {_FAKE_TOKEN_40}",
                 f'"token": "{_FAKE_TOKEN_40}"',
                 f"api_key={_FAKE_TOKEN_40}"):
        out = redact_token(line)
        assert _FAKE_TOKEN_40 not in out, line


def test_nested_exception_chain_scrubbed():
    # simulate a chained-exception repr string
    s = (f"ProviderError: fetch failed\n  caused by HTTPStatusError: 403 for "
         f"url 'https://api.polygon.io/x?apiKey={_POLY_KEY}'\n  "
         f"during retry 2 header Authorization: Bearer {_FAKE_TOKEN_40}")
    out = redact_token(s)
    assert _POLY_KEY not in out and _FAKE_TOKEN_40 not in out
    assert "retry 2" in out  # non-secret retry diagnostic preserved


def test_redirect_location_url_scrubbed():
    s = f"302 -> Location: https://api.polygon.io/v3/next?cursor=abc&apiKey={_POLY_KEY}"
    out = redact_token(s)
    assert _POLY_KEY not in out and "cursor=abc" in out


def test_output_is_bounded():
    huge = "?apiKey=" + ("a" * 100000)
    out = redact_token(huge)
    assert len(out) <= 4000


def test_non_secret_key_names_preserved():
    # sort_key / ticker / order_key must NOT be scrubbed (only exact 'key')
    src = "?sort_key=asc&ticker=SPY&limit=30"
    assert redact_token(src) == src


def test_global_patcher_scrubs_at_sink(capfd):
    from apps.api.src.options.data_provider._redact import install_global_redaction
    logger.remove()
    logger.add(io.StringIO())  # keep default too; capfd catches stderr
    sink = io.StringIO()
    logger.remove()
    logger.add(sink, level="INFO")
    install_global_redaction(logger)
    logger.warning(
        "Polygon minute aggs fetch failed for SPY: Client error '403' for "
        "url 'https://api.polygon.io/x?apiKey={}'", _POLY_KEY)
    out = sink.getvalue()
    assert _POLY_KEY not in out and "403" in out
    logger.remove()
    logger.configure(patcher=None)  # reset for other tests


def test_redact_error_for_storage_scrubs_and_bounds():
    from apps.api.src.options.data_provider._redact import redact_error_for_storage
    s = f"Traceback ... url 'https://x?apiKey={_POLY_KEY}'"
    out = redact_error_for_storage(s)
    assert _POLY_KEY not in out and len(out) <= 4000
