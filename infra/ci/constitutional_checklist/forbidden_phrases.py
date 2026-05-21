"""Phase L constitutional check — forbidden Tier-A phrase scanner.

Per docs/research/PHASE_L_CONSTITUTION.md §VII and L.3-R §VIII:
the 15 Tier-A phrases listed in
apps/api/src/reasoning/validators/forbidden_phrases_tier_a.json
must NEVER appear in user-facing copy.

Scope:
  * Python files: scan string literals only (heuristic via regex on
    quoted segments). Comments and docstrings are NOT excluded because
    the scanner is a coarse first-line defense; refine later.
  * TSX/TS files: scan all text including JSX literals.
  * Allow-list: filenames matching ALLOW_LIST_GLOBS are skipped.
    Use for files that legitimately reference forbidden phrases
    (e.g., this scanner itself; the forbidden-phrase JSON; docs).

Exit codes:
  0 — clean.
  1 — at least one violation.

Usage:
  python infra/ci/constitutional_checklist/forbidden_phrases.py
"""

from __future__ import annotations

import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_FILE = (
    REPO_ROOT / "apps" / "api" / "src" / "reasoning" / "validators"
    / "forbidden_phrases_tier_a.json"
)

# Scan these directories for user-facing copy.
SCAN_DIRS = [
    "apps/api/src",
    "apps/web/src",
]
SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Skip these (legitimate references / external content).
ALLOW_LIST_GLOBS = [
    "**/__pycache__/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/.venv/**",
    "**/forbidden_phrases_tier_a.json",
    "**/forbidden_phrases.py",
    "**/tests/**",
    "**/test_*.py",
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/.git/**",
    # Phase L spec files reference forbidden phrases by name; out of scope
    # for the user-facing copy scanner.
    "**/docs/research/**",
]


def _is_allowed(path: Path) -> bool:
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    return any(fnmatch(rel, glob) for glob in ALLOW_LIST_GLOBS)


def _load_forbidden() -> list[str]:
    with FORBIDDEN_FILE.open() as f:
        phrases = json.load(f)
    if not isinstance(phrases, list) or len(phrases) == 0:
        raise RuntimeError(f"forbidden phrase list empty or malformed: {FORBIDDEN_FILE}")
    return [p.lower() for p in phrases]


def _scan_file(path: Path, phrases: list[str]) -> list[tuple[int, str, str]]:
    """Returns list of (line_number, phrase, matched_line)."""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return violations
    for i, line in enumerate(text.splitlines(), 1):
        lower = line.lower()
        for phrase in phrases:
            if phrase in lower:
                violations.append((i, phrase, line.strip()))
    return violations


def main() -> int:
    phrases = _load_forbidden()
    total_violations: list[tuple[Path, int, str, str]] = []

    for scan_dir in SCAN_DIRS:
        base = REPO_ROOT / scan_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SCAN_EXTENSIONS:
                continue
            if _is_allowed(path):
                continue
            v = _scan_file(path, phrases)
            for line_no, phrase, snippet in v:
                total_violations.append((path, line_no, phrase, snippet))

    if total_violations:
        print(f"FORBIDDEN PHRASE VIOLATIONS: {len(total_violations)}", file=sys.stderr)
        for path, line_no, phrase, snippet in total_violations:
            rel = path.relative_to(REPO_ROOT)
            print(f"  {rel}:{line_no}: '{phrase}' in: {snippet[:120]}", file=sys.stderr)
        print(
            "\nFix: remove or rephrase. Forbidden list lives at "
            f"{FORBIDDEN_FILE.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1

    print(f"Forbidden-phrase scan passed. ({len(phrases)} phrases checked across "
          f"{len(SCAN_DIRS)} dir(s).)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
