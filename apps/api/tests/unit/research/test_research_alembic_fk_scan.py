"""Phase 11W (Phase B) — Alembic FK direction scan.

CI gate: every Alembic migration is scanned for `op.create_foreign_key`
calls. Any migration that creates an FK from `public.*` to
`research_ro.*` fails the build.
"""

from __future__ import annotations

import re
from pathlib import Path


VERSIONS_DIR = Path("infra/alembic/versions")


def test_no_public_to_research_ro_fk_in_any_migration():
    """Source-level grep over all migration files."""
    bad: list[tuple[str, str]] = []
    for f in VERSIONS_DIR.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        # Any create_foreign_key whose argument tuple references
        # research_ro on the *target* side AND has a source schema of
        # public (or unspecified, which defaults to public).
        for m in re.finditer(
            r"create_foreign_key\s*\(.*?\)",
            src, flags=re.DOTALL,
        ):
            block = m.group(0)
            mentions_research_ro = "research_ro" in block
            # source_schema kwarg explicitly research_ro means the FK
            # is research_ro.* -> public.*  (allowed direction). If
            # source_schema is not "research_ro", and the block
            # mentions research_ro at all, that's the forbidden
            # direction.
            if not mentions_research_ro:
                continue
            if 'source_schema="research_ro"' in block:
                continue
            if "source_schema='research_ro'" in block:
                continue
            bad.append((f.name, block))
    assert bad == [], (
        f"Forbidden FK direction (public -> research_ro) found in: {bad}"
    )


def test_research_ro_migration_does_not_add_public_fk_to_research():
    """Specifically scan the research_ro_init migration."""
    p = VERSIONS_DIR / "052_research_ro_init.py"
    if not p.exists():
        return  # phase B file not present in stripped checkouts
    src = p.read_text(encoding="utf-8")
    # The migration must NOT add a FK in public referencing research_ro.
    forbidden_phrases = [
        "ALTER TABLE public",
        "ADD CONSTRAINT",
    ]
    # Cheap scan; allow zero hits even though they could appear in
    # comments — keeps the gate strict.
    bad_present = all(
        phrase in src for phrase in forbidden_phrases
    )
    assert not bad_present, (
        "Phase B migration appears to add a FK on a public table; "
        "FK direction must be research_ro -> public ONLY."
    )
