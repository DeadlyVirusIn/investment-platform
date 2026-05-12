#!/usr/bin/env python3
"""Phase 15i.D — read-only daily-pipeline freshness check.

Reads /api/freshness and exits 0/1/2/3/4. Wire into cron / CI /
manual call. NEVER writes, NEVER retries, NEVER triggers
scheduler interaction, NEVER auto-fixes anything.

Exit codes:
    0  OK            — overall=fresh
    1  DEGRADED      — overall=degraded
    2  STALE         — overall=stale
    3  UNREACHABLE   — endpoint connect/transport failure
    4  MALFORMED     — endpoint returned a payload we cannot parse

Usage:
    python scripts/check_daily_pipeline_health.py
    python scripts/check_daily_pipeline_health.py \
        --base-url http://api.example.com:8000
    python scripts/check_daily_pipeline_health.py --json
    python scripts/check_daily_pipeline_health.py --quiet
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8000"
PATH = "/api/freshness"
TIMEOUT_S = 10.0

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_STALE = 2
EXIT_UNREACHABLE = 3
EXIT_MALFORMED = 4

PRIMARY_CHANNELS = ("recommendations", "portfolio", "events", "risk")
INFORMATIONAL_CHANNELS = ("options", "ml")
ALL_CHANNELS = PRIMARY_CHANNELS + INFORMATIONAL_CHANNELS

# Display labels — chosen for the alignment in §9.4 output spec.
LABELS = {
    "recommendations": "recommendations",
    "portfolio":       "paper portfolio",
    "events":          "events",
    "options":         "options",
    "risk":            "risk",
    "ml":              "ML shadow",
}

STATUS_TAG = {
    "fresh":    "[OK]   ",
    "degraded": "[WARN] ",
    "stale":    "[STALE]",
    "unknown":  "[?]    ",
}


def _fetch(base_url: str) -> tuple[int, dict[str, Any] | str]:
    """Fetch /api/freshness. Returns (exit_hint, body_or_error_str)."""
    url = base_url.rstrip("/") + PATH
    req = urllib.request.Request(
        url, headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return EXIT_UNREACHABLE, f"transport error: {e!r}"
    except TimeoutError as e:
        return EXIT_UNREACHABLE, f"timeout: {e!r}"
    except Exception as e:  # pragma: no cover — defensive only
        return EXIT_UNREACHABLE, f"unexpected error: {e!r}"

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        return EXIT_MALFORMED, f"json decode failed: {e!r}"

    if not isinstance(body, dict):
        return EXIT_MALFORMED, "response is not a JSON object"
    return 0, body


def _validate(body: dict[str, Any]) -> str | None:
    """Return None if shape OK, else an error string."""
    for key in ("trading_date", "overall", "channels"):
        if key not in body:
            return f"missing top-level key: {key}"
    if not isinstance(body["channels"], dict):
        return "channels is not an object"
    for name in ALL_CHANNELS:
        ch = body["channels"].get(name)
        if not isinstance(ch, dict):
            return f"channel {name!r} missing or not an object"
        if "status" not in ch:
            return f"channel {name!r} missing status"
    return None


def _age_string(as_of_iso: str | None) -> str:
    """Render a human age like `3h`, `12m`, `4d` — or 'unknown'."""
    if not as_of_iso:
        return "unknown"
    try:
        ts = dt.datetime.fromisoformat(as_of_iso.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    delta = dt.datetime.now(dt.timezone.utc) - ts
    secs = max(0, int(delta.total_seconds()))
    if secs < 3600:
        mins = secs // 60
        return f"{mins}m"
    if secs < 48 * 3600:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _exit_code_from_overall(overall: str) -> int:
    return {
        "fresh":    EXIT_OK,
        "degraded": EXIT_DEGRADED,
        "stale":    EXIT_STALE,
        # Unknown is not an error per se — treat it as degraded so
        # operators see something needs attention without escalating
        # to STALE (which implies the SLA was definitively broken).
        "unknown":  EXIT_DEGRADED,
    }.get(overall, EXIT_MALFORMED)


def _print_human(body: dict[str, Any]) -> None:
    chans = body["channels"]
    label_w = max(len(LABELS[n]) for n in ALL_CHANNELS)
    for name in ALL_CHANNELS:
        ch = chans[name]
        status = ch.get("status", "unknown")
        tag = STATUS_TAG.get(status, "[?]    ")
        as_of = ch.get("as_of")
        age = _age_string(as_of)
        last_str = as_of if as_of else "n/a"
        label = LABELS[name].ljust(label_w)
        age_col = age.ljust(6)
        print(f"{tag} {label}  age={age_col}  last={last_str}")

    print()
    print(f"trading_date    : {body.get('trading_date')}")
    print(f"last_cycle_at   : {body.get('last_successful_cycle_at')}")
    print(f"overall         : {str(body.get('overall', '')).upper()}")


def _print_summary_line(body: dict[str, Any], exit_code: int) -> None:
    overall = str(body.get("overall", "")).upper()
    print(
        f"trading_date={body.get('trading_date')} "
        f"overall={overall} exit={exit_code}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only daily-pipeline freshness check. Reads "
            "/api/freshness and exits 0/1/2/3/4. Wire into cron / "
            "CI / manual call."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the raw JSON response instead of the table.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the summary line and exit code.",
    )
    args = parser.parse_args(argv)

    rc, body = _fetch(args.base_url)
    if rc == EXIT_UNREACHABLE:
        if not args.quiet:
            print(f"[UNREACHABLE] {body}", file=sys.stderr)
        else:
            print(f"unreachable exit={EXIT_UNREACHABLE}", file=sys.stderr)
        return EXIT_UNREACHABLE
    if rc == EXIT_MALFORMED:
        if not args.quiet:
            print(f"[MALFORMED] {body}", file=sys.stderr)
        else:
            print(f"malformed exit={EXIT_MALFORMED}", file=sys.stderr)
        return EXIT_MALFORMED

    assert isinstance(body, dict)
    err = _validate(body)
    if err is not None:
        if not args.quiet:
            print(f"[MALFORMED] {err}", file=sys.stderr)
        else:
            print(
                f"malformed exit={EXIT_MALFORMED}",
                file=sys.stderr,
            )
        return EXIT_MALFORMED

    overall = str(body.get("overall", "")).lower()
    exit_code = _exit_code_from_overall(overall)

    if args.json:
        print(json.dumps(body, indent=2, sort_keys=True))
    elif args.quiet:
        _print_summary_line(body, exit_code)
    else:
        _print_human(body)
        print(f"exit            : {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
