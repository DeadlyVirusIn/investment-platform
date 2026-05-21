"""Canary-1 constitutional lint — write-gateway + boundary invariants.

Enforces the Gate 3 §11 invariants:

  L1. The only legal `INSERT INTO options_trade_lifecycle_event` is inside
      apps/api/src/options/canary/engine.py:_append_lifecycle_event.
  L2. The only legal `INSERT INTO options_canary_lifecycle_run` is inside
      apps/api/src/options/canary/engine.py:_write_canary_telemetry.
  L3. No `UPDATE options_trade_lifecycle_event` or
      `DELETE FROM options_trade_lifecycle_event` anywhere — append-only
      audit trail.
  L4. No `UPDATE options_canary_lifecycle_run` or
      `DELETE FROM options_canary_lifecycle_run` anywhere — append-only
      telemetry.
  L5. The two canary worker job modules MUST NOT import each other.
  L6. The two canary worker job modules MUST NOT import
      apps.api.src.options.canary.operator_event (operator surface is
      job-callable-NEVER).

Stdlib-only. Runs under Python 3.12. Exit codes:
  0 — all invariants hold.
  1 — one or more violations; details printed to stderr.

Usage:
  python infra/ci/constitutional_checklist/canary_gateway_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

# Path constants.
ENGINE_FILE = REPO_ROOT / "apps" / "api" / "src" / "options" / "canary" / "engine.py"
JOB_PROPOSAL = REPO_ROOT / "apps" / "worker" / "src" / "jobs" / "options_canary_proposal.py"
JOB_LIFECYCLE = REPO_ROOT / "apps" / "worker" / "src" / "jobs" / "options_canary_lifecycle.py"

# Patterns to detect direct table access (case-insensitive, whitespace-tolerant).
RX_INSERT_EVENT = re.compile(
    r"INSERT\s+INTO\s+options_trade_lifecycle_event",
    re.IGNORECASE,
)
RX_INSERT_TELEMETRY = re.compile(
    r"INSERT\s+INTO\s+options_canary_lifecycle_run",
    re.IGNORECASE,
)
RX_UPDATE_EVENT = re.compile(
    r"UPDATE\s+options_trade_lifecycle_event",
    re.IGNORECASE,
)
RX_DELETE_EVENT = re.compile(
    r"DELETE\s+FROM\s+options_trade_lifecycle_event",
    re.IGNORECASE,
)
RX_UPDATE_TELEMETRY = re.compile(
    r"UPDATE\s+options_canary_lifecycle_run",
    re.IGNORECASE,
)
RX_DELETE_TELEMETRY = re.compile(
    r"DELETE\s+FROM\s+options_canary_lifecycle_run",
    re.IGNORECASE,
)
RX_IMPORT_OPERATOR_EVENT = re.compile(
    r"^\s*(?:from|import)\s+apps\.api\.src\.options\.canary\.operator_event\b",
    re.MULTILINE,
)
RX_IMPORT_PROPOSAL = re.compile(
    r"^\s*(?:from|import)\s+apps\.worker\.src\.jobs\.options_canary_proposal\b",
    re.MULTILINE,
)
RX_IMPORT_LIFECYCLE = re.compile(
    r"^\s*(?:from|import)\s+apps\.worker\.src\.jobs\.options_canary_lifecycle\b",
    re.MULTILINE,
)

# Pre-existing options modules that write to options_trade_lifecycle_event
# directly. These predate the canary write gateway (Phase Opt-C2 era).
# Refactoring them to route through engine._append_lifecycle_event is a
# separate, intentional follow-up — NOT a Gate 4 deliverable. Listed here
# explicitly so the allowlist is a visible scope decision rather than a
# hidden bypass. Any NEW file writing to the table will still trip L1.
LEGACY_LIFECYCLE_WRITERS = frozenset({
    REPO_ROOT / "apps" / "api" / "src" / "options" / "lifecycle.py",
    REPO_ROOT / "apps" / "api" / "src" / "options" / "paper" / "engine.py",
})

# Source roots to scan. We deliberately exclude:
#   - infra/alembic/versions/*  (migrations are allowed to do anything;
#     they predate / define the tables)
#   - tests under */tests/*     (tests may use raw SQL to set up state)
#   - this lint file itself     (contains the pattern literals)
#   - docs/                     (documentation may contain SQL examples)
SOURCE_GLOBS = ["apps/**/*.py"]
EXCLUDED_PARTS = ("tests", "test_", "__pycache__")


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for pattern in SOURCE_GLOBS:
        for p in REPO_ROOT.glob(pattern):
            if any(part in EXCLUDED_PARTS or part.startswith("test_")
                   for part in p.parts):
                continue
            files.append(p)
    return files


def _check_table_writes() -> list[str]:
    """L1-L4: write-gateway exclusivity and append-only."""
    violations: list[str] = []
    for path in _iter_python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue

        # L1: INSERT INTO options_trade_lifecycle_event only inside engine.py.
        # LEGACY_LIFECYCLE_WRITERS are explicitly allowlisted — Phase Opt-C2
        # predates the canary write gateway; refactoring is a deferred
        # follow-up, not a Gate 4 deliverable.
        if (
            RX_INSERT_EVENT.search(src)
            and path != ENGINE_FILE
            and path not in LEGACY_LIFECYCLE_WRITERS
        ):
            violations.append(
                f"L1 VIOLATION {rel}: direct `INSERT INTO "
                f"options_trade_lifecycle_event` outside engine."
                f"_append_lifecycle_event."
            )

        # L2: INSERT INTO options_canary_lifecycle_run only inside engine.py.
        if RX_INSERT_TELEMETRY.search(src) and path != ENGINE_FILE:
            violations.append(
                f"L2 VIOLATION {rel}: direct `INSERT INTO "
                f"options_canary_lifecycle_run` outside engine."
                f"_write_canary_telemetry."
            )

        # L3: append-only event audit trail.
        if RX_UPDATE_EVENT.search(src):
            violations.append(
                f"L3 VIOLATION {rel}: `UPDATE options_trade_lifecycle_event` "
                f"forbidden — table is append-only."
            )
        if RX_DELETE_EVENT.search(src):
            violations.append(
                f"L3 VIOLATION {rel}: `DELETE FROM "
                f"options_trade_lifecycle_event` forbidden — table is "
                f"append-only."
            )

        # L4: append-only telemetry.
        if RX_UPDATE_TELEMETRY.search(src):
            violations.append(
                f"L4 VIOLATION {rel}: `UPDATE options_canary_lifecycle_run` "
                f"forbidden — table is append-only."
            )
        if RX_DELETE_TELEMETRY.search(src):
            violations.append(
                f"L4 VIOLATION {rel}: `DELETE FROM "
                f"options_canary_lifecycle_run` forbidden — table is "
                f"append-only."
            )

    return violations


def _check_module_imports() -> list[str]:
    """L5-L6: module-boundary invariants."""
    violations: list[str] = []

    # L5a: proposal must not import lifecycle.
    if JOB_PROPOSAL.exists():
        src = JOB_PROPOSAL.read_text(encoding="utf-8")
        if RX_IMPORT_LIFECYCLE.search(src):
            violations.append(
                "L5 VIOLATION apps/worker/src/jobs/options_canary_proposal.py: "
                "imports options_canary_lifecycle (worker→worker forbidden)."
            )
        if RX_IMPORT_OPERATOR_EVENT.search(src):
            violations.append(
                "L6 VIOLATION apps/worker/src/jobs/options_canary_proposal.py: "
                "imports operator_event (operator surface is job-callable-NEVER)."
            )

    # L5b: lifecycle must not import proposal.
    if JOB_LIFECYCLE.exists():
        src = JOB_LIFECYCLE.read_text(encoding="utf-8")
        if RX_IMPORT_PROPOSAL.search(src):
            violations.append(
                "L5 VIOLATION apps/worker/src/jobs/options_canary_lifecycle.py: "
                "imports options_canary_proposal (worker→worker forbidden)."
            )
        if RX_IMPORT_OPERATOR_EVENT.search(src):
            violations.append(
                "L6 VIOLATION apps/worker/src/jobs/options_canary_lifecycle.py: "
                "imports operator_event (operator surface is job-callable-NEVER)."
            )

    return violations


def main() -> int:
    all_violations: list[str] = []
    all_violations.extend(_check_table_writes())
    all_violations.extend(_check_module_imports())

    if all_violations:
        print(
            "Canary gateway lint FAILED — invariants violated:\n",
            file=sys.stderr,
        )
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        print(
            f"\nTotal violations: {len(all_violations)}",
            file=sys.stderr,
        )
        return 1

    print("Canary gateway lint OK — all invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
