"""GET-only WebUI endpoint audit.

Hits the read-only endpoints that the WebUI consumes and prints a
status table. Exits non-zero when:

  * A pinned endpoint is unreachable.
  * Schema keys the UI relies on are missing from the response.
  * A consistency check fails (e.g. paper/executed/summary reports
    `has_replay_recovered_rows=true` while `replay_trades_count=0`).

Hard rules:
  * GET only. NO POST/PUT/PATCH/DELETE issued.
  * NO auth bypass except local dev mode (`AUDIT_BASE_URL` defaults
    to http://localhost:8000 — operator must point this at a running
    dev API; this script does not start one).
  * NO writes. NO scheduling. NO ML toggle changes.

Usage:

  python -m scripts.audit_webui_endpoints
  AUDIT_BASE_URL=http://localhost:8000 python -m scripts.audit_webui_endpoints

Exit codes:
  0  every audited endpoint reachable and schema-valid
  1  one or more endpoints failed reachability or schema check
  2  base URL not reachable at all
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE = "http://localhost:8000"
TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class Audit:
    label: str
    path: str
    required_keys: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
    note: str | None = None


# Endpoint set — pinned. Extend when new pages add read-only fetches.
AUDITS: tuple[Audit, ...] = (
    # ----- Paper / executed (Phase 11Z) -----
    Audit(
        label="paper/executed/summary (default)",
        path="/api/paper/executed/summary",
        required_keys=(
            "trades_total", "open_positions",
            "live_trades_count", "replay_trades_count",
            "live_open_positions_count", "replay_open_positions_count",
            "has_replay_recovered_rows", "include_replay",
        ),
    ),
    Audit(
        label="paper/executed/summary?include_replay=true",
        path="/api/paper/executed/summary?include_replay=true",
        required_keys=(
            "trades_total", "include_replay",
            "live_trades_count", "replay_trades_count",
        ),
    ),
    Audit(
        label="paper/executed/trades (live only)",
        path="/api/paper/executed/trades",
        required_keys=("count", "trades", "include_replay"),
    ),
    Audit(
        label="paper/executed/positions (open + live)",
        path="/api/paper/executed/positions?is_open=true",
        required_keys=("count", "positions", "include_replay"),
    ),
    # ----- Selector path -----
    Audit(label="paper/summary", path="/api/paper/summary",
          required_keys=("equity",)),
    Audit(label="paper/state", path="/api/paper/state"),
    Audit(label="paper/trades", path="/api/paper/trades"),
    Audit(label="paper/equity", path="/api/paper/equity"),
    Audit(label="paper/performance", path="/api/paper/performance"),
    # ----- Options -----
    Audit(label="options/health", path="/api/options/health",
          required_keys=("status", "paper_only", "ml_can_affect_trades")),
    Audit(
        label="options/pipeline-status",
        path="/api/options/pipeline-status",
        required_keys=(
            "options_chain_snapshot_count",
            "options_paper_trade_count",
        ),
    ),
    Audit(
        label="options/shadow/summary",
        path="/api/options/shadow/summary",
        required_keys=("active", "total_runs", "freshness_warnings"),
    ),
    # ----- Health / jobs -----
    Audit(label="system/health", path="/api/system/health"),
    Audit(label="jobs/status", path="/api/jobs/status"),
    Audit(label="scheduler/health", path="/api/scheduler/health"),
    # ----- Anomalies -----
    Audit(label="anomalies/summary", path="/api/anomalies/summary"),
)


def _fetch(base: str, path: str) -> tuple[int, Any | None, str | None]:
    url = f"{base.rstrip('/')}{path}"
    req = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json",
        "User-Agent": "audit-webui-endpoints/1",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body) if body else None
            except json.JSONDecodeError as exc:
                return status, None, f"JSON decode error: {exc}"
            return status, payload, None
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return 0, None, f"URLError: {exc.reason}"
    except TimeoutError:
        return 0, None, "timeout"
    except OSError as exc:  # connection refused, etc.
        return 0, None, f"{type(exc).__name__}: {exc}"


def _check_keys(
    payload: Any, required: tuple[str, ...]
) -> tuple[bool, list[str]]:
    """Only enforce dict shape when there are required keys to look for.

    Some endpoints legitimately return JSON arrays (e.g. /paper/trades,
    /paper/equity); those declare no required_keys and pass this check
    as long as the payload decoded."""
    missing: list[str] = []
    if not required:
        return True, []
    if not isinstance(payload, dict):
        return False, [f"not a dict (got {type(payload).__name__})"]
    for k in required:
        if k not in payload:
            missing.append(k)
    return not missing, missing


def _consistency_check_executed_summary(payload: dict) -> list[str]:
    """Cross-field invariants on /paper/executed/summary."""
    errors: list[str] = []
    has_flag = bool(payload.get("has_replay_recovered_rows"))
    replay_count = int(payload.get("replay_trades_count", 0) or 0)
    live_count = int(payload.get("live_trades_count", 0) or 0)
    total = int(payload.get("trades_total", 0) or 0)
    include_replay = bool(payload.get("include_replay"))
    if has_flag and replay_count == 0:
        errors.append(
            "has_replay_recovered_rows=true but replay_trades_count=0"
        )
    if not has_flag and replay_count > 0:
        errors.append(
            f"has_replay_recovered_rows=false but replay_trades_count="
            f"{replay_count}"
        )
    # When include_replay=False, trades_total should equal live_count.
    if not include_replay and live_count != total:
        errors.append(
            f"include_replay=false: trades_total={total} != "
            f"live_trades_count={live_count}"
        )
    return errors


def _consistency_check_options_paper_only(payload: dict) -> list[str]:
    """Options must remain paper-only for safety."""
    errors: list[str] = []
    if payload.get("paper_only") is not True:
        errors.append("options/health.paper_only must be true")
    if payload.get("ml_can_affect_trades") is not False:
        errors.append("options/health.ml_can_affect_trades must be false")
    return errors


def main(argv: list[str] | None = None) -> int:
    base = os.environ.get("AUDIT_BASE_URL", DEFAULT_BASE)
    sys.stdout.write(f"Auditing WebUI endpoints against {base}\n")
    sys.stdout.write("=" * 70 + "\n")

    # Reachability sentinel.
    status, _, err = _fetch(base, "/api/health")
    if status == 0 and err:
        sys.stderr.write(
            f"REFUSED: cannot reach {base}/api/health: {err}\n"
            f"Hint: start the API container (docker compose up api) or "
            f"override AUDIT_BASE_URL.\n"
        )
        return 2

    failures = 0
    for a in AUDITS:
        status, payload, err = _fetch(base, a.path)
        if err or status >= 400 or payload is None:
            sys.stdout.write(
                f"[FAIL] {a.label:55s} {status} {err or ''}\n"
            )
            failures += 1
            continue
        ok, missing = _check_keys(payload, a.required_keys)
        if not ok:
            sys.stdout.write(
                f"[FAIL] {a.label:55s} 200 missing keys: {missing}\n"
            )
            failures += 1
            continue
        # Per-endpoint consistency checks.
        consistency_errors: list[str] = []
        if a.path.startswith("/api/paper/executed/summary"):
            consistency_errors = _consistency_check_executed_summary(payload)
        elif a.path == "/api/options/health":
            consistency_errors = _consistency_check_options_paper_only(payload)
        if consistency_errors:
            for e in consistency_errors:
                sys.stdout.write(f"[FAIL] {a.label:55s} 200 {e}\n")
            failures += len(consistency_errors)
            continue
        # Surface the headline numbers so operators can spot-check.
        snippet = ""
        if a.path.startswith("/api/paper/executed/summary"):
            snippet = (
                f"live={payload.get('live_trades_count')} "
                f"replay={payload.get('replay_trades_count')} "
                f"total={payload.get('trades_total')}"
            )
        elif a.path == "/api/options/pipeline-status":
            snippet = (
                f"chain={payload.get('options_chain_snapshot_count')} "
                f"opt_paper={payload.get('options_paper_trade_count')}"
            )
        elif a.path == "/api/options/shadow/summary":
            snippet = (
                f"runs={payload.get('total_runs')} "
                f"latest={payload.get('latest_run_date')}"
            )
        sys.stdout.write(f"[ ok ] {a.label:55s} 200  {snippet}\n")

    sys.stdout.write("=" * 70 + "\n")
    if failures:
        sys.stdout.write(f"FAILED: {failures} check(s) did not pass.\n")
        return 1
    sys.stdout.write("OK: all audited endpoints reachable + schema-valid.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
