"""Phase 11Z incident-response — CI guard against destructive
`docker compose down -v` and `docker volume rm compose_pgdata`
appearing in source code.

Allowed locations:
  * `scripts/safe_compose_down.sh` — the wrapper that gates the
    destructive command behind dual confirmation
  * `docs/ops/DB_VOLUME_SAFETY.md` — the documentation that
    describes the wrapper

Anywhere else in the repo, the literal string is treated as a
build break.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_DESTRUCTIVE_PATTERNS = (
    re.compile(r"docker\s+compose\s+down\s+(?:[^\n]*\s)?-v\b"),
    re.compile(r"docker\s+volume\s+rm\s+compose_pgdata\b"),
)

_ALLOWED = (
    Path("scripts/safe_compose_down.sh"),
    Path("docs/ops/DB_VOLUME_SAFETY.md"),
    Path("apps/api/tests/unit/test_db_volume_safety_guard.py"),
)

_ALLOWED_DIRS = (
    Path("docs/ops"),
)

_SCAN_DIRS = (
    Path("Makefile"),  # single file, handled below
    Path("scripts"),
    Path("docs"),
    Path("apps/api/src"),
    Path("apps/worker/src"),
    Path("apps/web/src"),
    Path("infra"),
)


def _is_allowed(p: Path) -> bool:
    p = p.resolve()
    for ok in _ALLOWED:
        try:
            if p.samefile(ok.resolve()):
                return True
        except FileNotFoundError:
            continue
    for d in _ALLOWED_DIRS:
        try:
            if d.resolve() in p.parents:
                return True
        except FileNotFoundError:
            continue
    return False


def _iter_files():
    for top in _SCAN_DIRS:
        if not top.exists():
            continue
        if top.is_file():
            yield top
            continue
        for p in top.rglob("*"):
            if p.is_file() and p.suffix in (
                ".sh", ".py", ".md", ".yml", ".yaml", ".txt",
                ".tsx", ".ts", ".dockerfile", "",
            ):
                yield p


@pytest.mark.parametrize("pattern", _DESTRUCTIVE_PATTERNS)
def test_no_unsafe_compose_volume_destruction_in_source(pattern):
    bad: list[tuple[str, int, str]] = []
    for f in _iter_files():
        if _is_allowed(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            # Allow comments mentioning the command for documentation
            # purposes — but only when the line is clearly a comment.
            stripped = line.lstrip()
            is_comment = (
                stripped.startswith("#")
                or stripped.startswith("//")
                or stripped.startswith("--")
                or stripped.startswith("*")
            )
            if pattern.search(line) and not is_comment:
                bad.append((str(f), i, line.strip()))
    assert not bad, (
        f"forbidden destructive DB command found in non-allowed "
        f"file(s): {bad[:5]}"
    )
