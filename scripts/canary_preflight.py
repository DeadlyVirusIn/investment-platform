"""Canary-1 pre-flight — operational tool (Gate 5 real implementation).

Run BEFORE flipping OPTIONS_CANARY_ENABLED. Exits 0 only if every gate
passes. Implements all four checks specified in
docs/research/OPTIONS_CANARY_1_GATE_5_BLAST_RADIUS.md §6.

Stdlib-only (subprocess, hashlib, re, json). Requires docker CLI on
PATH and access to the running compose stack.

Usage:
  python scripts/canary_preflight.py
  python scripts/canary_preflight.py --json     # machine-readable
  python scripts/canary_preflight.py --strict   # any stub = fail

Exit codes:
  0 — all checks passed.
  1 — any check failed (or stub seen in --strict).
  2 — operational error (cannot reach docker / DB / containers).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal


REPO_ROOT = Path(__file__).resolve().parents[1]

CRITICAL_FILES = [
    "apps/worker/src/jobs/options_chain_snapshot.py",
    "apps/worker/src/jobs/options_canary_proposal.py",
    "apps/worker/src/jobs/options_canary_lifecycle.py",
    "apps/api/src/options/data/chain_ingest.py",
    "apps/api/src/options/data_provider/tradier_adapter.py",
    "apps/api/src/options/canary/engine.py",
    "apps/api/src/config/__init__.py",
    "apps/api/src/db/models.py",
]

WORKER_CONTAINERS = [
    "compose-worker-cron-1",
    "compose-worker-tickloop-1",
]

DB_CONTAINER = "compose-db-1"
DB_USER_ENV = "POSTGRES_USER"
DB_NAME_ENV = "POSTGRES_DB"

ALEMBIC_VERSIONS_DIR = REPO_ROOT / "infra" / "alembic" / "versions"

# Gate 5 EXCEPTION: 240-minute window + anchor on actual chain data
# (MAX(snapshot_at_utc) for SPY), not on ingest_run.started_at. See
# OPTIONS_CANARY_1_GATE_5_BLAST_RADIUS.md §6 "Gate 5 freshness exception".
# Revert to 90 min + tighter semantics at Gate 6+.
CHAIN_FRESHNESS_MAX_AGE_MINUTES = 240


CheckStatus = Literal["pass", "fail", "stub", "operational_error"]


@dataclasses.dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _host_md5(rel_path: str) -> str | None:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return None
    h = hashlib.md5()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _docker_exec(container: str, *args: str) -> tuple[int, str, str]:
    """Run `docker exec <container> <args>`. Returns (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["docker", "exec", container, *args],
            check=False, capture_output=True, text=True, timeout=15,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "docker CLI not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "docker exec timed out (15s)"


def _container_md5(container: str, rel_path: str) -> str | None:
    rc, out, err = _docker_exec(container, "md5sum", f"/app/{rel_path}")
    if rc != 0:
        return None
    m = re.match(r"^([0-9a-f]{32})\s", out.strip())
    return m.group(1) if m else None


def _host_alembic_head() -> str | None:
    """Find the latest alembic revision id by scanning versions/.

    Looks for the revision that no other file declares as down_revision.
    """
    if not ALEMBIC_VERSIONS_DIR.exists():
        return None
    revisions: dict[str, str | None] = {}
    rx_rev = re.compile(
        r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE,
    )
    rx_down = re.compile(
        r"^down_revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE,
    )
    for p in ALEMBIC_VERSIONS_DIR.glob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m_rev = rx_rev.search(text)
        m_down = rx_down.search(text)
        if not m_rev:
            continue
        revisions[m_rev.group(1)] = m_down.group(1) if m_down else None

    downs = {v for v in revisions.values() if v is not None}
    heads = [r for r in revisions if r not in downs]
    if not heads:
        return None
    if len(heads) > 1:
        # Multiple heads — pathological for our use. Return None to fail
        # the parity check loudly.
        return None
    return heads[0]


def _container_alembic_head(container: str) -> str | None:
    """Read alembic_version table directly via psql exec into DB container."""
    rc, out, err = _docker_exec(
        DB_CONTAINER, "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A '
        '-c "SELECT version_num FROM alembic_version;"',
    )
    if rc != 0:
        return None
    return out.strip() or None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_md5_parity() -> CheckResult:
    """Each CRITICAL_FILE must have identical md5 on host + every worker
    container."""
    mismatches: list[dict] = []
    examined: list[dict] = []
    for rel in CRITICAL_FILES:
        host_hash = _host_md5(rel)
        if host_hash is None:
            mismatches.append({"file": rel, "host_md5": None,
                               "reason": "missing_on_host"})
            continue
        row: dict = {"file": rel, "host": host_hash[:12]}
        ok = True
        for c in WORKER_CONTAINERS:
            ch = _container_md5(c, rel)
            row[c] = (ch[:12] if ch else "MISSING")
            if ch != host_hash:
                ok = False
        examined.append(row)
        if not ok:
            mismatches.append({"file": rel, "row": row})
    if mismatches:
        return CheckResult(
            name="md5_parity",
            status="fail",
            detail={"mismatches": mismatches, "examined_count": len(examined)},
        )
    return CheckResult(
        name="md5_parity",
        status="pass",
        detail={"files_checked": len(examined),
                "containers": WORKER_CONTAINERS},
    )


def check_alembic_head() -> CheckResult:
    host_head = _host_alembic_head()
    if host_head is None:
        return CheckResult(
            name="alembic_head", status="operational_error",
            detail={"reason": "could_not_determine_host_head"},
        )
    db_head = _container_alembic_head(DB_CONTAINER)
    if db_head is None:
        return CheckResult(
            name="alembic_head", status="operational_error",
            detail={"reason": "could_not_read_alembic_version_table"},
        )
    if db_head != host_head:
        return CheckResult(
            name="alembic_head", status="fail",
            detail={"host_head": host_head, "db_head": db_head,
                    "remediation": "alembic upgrade head"},
        )
    return CheckResult(
        name="alembic_head", status="pass",
        detail={"head": host_head},
    )


def check_canary_portfolio_active() -> CheckResult:
    rc, out, err = _docker_exec(
        DB_CONTAINER, "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -F"|" '
        "-c \"SELECT name, active, cash_initial, cash_current "
        "FROM options_paper_portfolio WHERE name='canary-spy-v1';\"",
    )
    if rc != 0:
        return CheckResult(
            name="canary_portfolio_active", status="operational_error",
            detail={"stderr": err.strip()[:200]},
        )
    line = out.strip()
    if not line:
        return CheckResult(
            name="canary_portfolio_active", status="fail",
            detail={"reason": "portfolio_row_missing"},
        )
    parts = line.split("|")
    name, active, cash_i, cash_c = parts[0], parts[1], parts[2], parts[3]
    if active != "t":
        return CheckResult(
            name="canary_portfolio_active", status="fail",
            detail={"name": name, "active": active,
                    "cash_initial": cash_i, "cash_current": cash_c},
        )
    return CheckResult(
        name="canary_portfolio_active", status="pass",
        detail={"name": name, "cash_initial": cash_i,
                "cash_current": cash_c},
    )


def check_chain_freshness() -> CheckResult:
    """Gate 5 truth-driven freshness: anchor on the chain data we'd act
    on (MAX snapshot_at_utc for SPY), not on ingest_run.started_at.

    Rationale: the proposal selector queries `options_chain_snapshot`
    directly. If actionable SPY rows exist within the window, freshness
    is satisfied regardless of whether the most recent ingest_run
    inserted new rows or classified as no_new_data.

    Tighten at Gate 6+ to a 90-minute or market-session-aware bound.
    """
    rc, out, err = _docker_exec(
        DB_CONTAINER, "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -F"|" '
        "-c \"SELECT MAX(snapshot_at_utc), "
        "EXTRACT(EPOCH FROM (NOW() - MAX(snapshot_at_utc)))/60.0 AS age_min "
        "FROM options_chain_snapshot WHERE underlying='SPY';\"",
    )
    if rc != 0:
        return CheckResult(
            name="chain_freshness", status="operational_error",
            detail={"stderr": err.strip()[:200]},
        )
    line = out.strip()
    if not line or line == "|":
        return CheckResult(
            name="chain_freshness", status="fail",
            detail={"reason": "no_spy_chain_rows"},
        )
    parts = line.split("|")
    latest_snapshot, age_min_s = parts[0], parts[1]
    try:
        age_min = float(age_min_s)
    except ValueError:
        return CheckResult(
            name="chain_freshness", status="operational_error",
            detail={"reason": "age_min_parse_failed", "raw": line},
        )
    if age_min > CHAIN_FRESHNESS_MAX_AGE_MINUTES:
        return CheckResult(
            name="chain_freshness", status="fail",
            detail={"latest_snapshot": latest_snapshot,
                    "age_minutes": round(age_min, 2),
                    "max_age_minutes": CHAIN_FRESHNESS_MAX_AGE_MINUTES},
        )
    return CheckResult(
        name="chain_freshness", status="pass",
        detail={"latest_snapshot": latest_snapshot,
                "age_minutes": round(age_min, 2),
                "note": "Gate 5 truth-anchor: MAX(snapshot_at_utc) "
                        "for SPY in options_chain_snapshot"},
    )


CHECKS = [
    check_md5_parity,
    check_alembic_head,
    check_canary_portfolio_active,
    check_chain_freshness,
]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Canary-1 pre-flight checks.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat any 'stub' result as a failure.",
    )
    args = parser.parse_args(argv)

    results: list[CheckResult] = [check() for check in CHECKS]

    if args.json:
        print(json.dumps(
            {"results": [dataclasses.asdict(r) for r in results]},
            indent=2,
            default=str,
        ))
    else:
        for r in results:
            status_marker = {
                "pass": "[ PASS ]",
                "fail": "[ FAIL ]",
                "stub": "[ STUB ]",
                "operational_error": "[ ERR  ]",
            }[r.status]
            print(f"{status_marker} {r.name}")
            for k, v in r.detail.items():
                print(f"         {k}: {v}")

    any_failed = any(r.status == "fail" for r in results)
    any_op_err = any(r.status == "operational_error" for r in results)
    any_stub = any(r.status == "stub" for r in results)

    if any_op_err:
        return 2
    if any_failed:
        return 1
    if args.strict and any_stub:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
