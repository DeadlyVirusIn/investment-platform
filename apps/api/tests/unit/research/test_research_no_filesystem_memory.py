"""Phase 11W (Phase B) — filesystem-egress lint.

The research layer must persist exclusively to Postgres `research_ro`.
No `~/.tradingagents/`, `~/.vibe-trading/`, `~/.openalice/`, or any
other home-relative path may be referenced in research code.
`os.path.expanduser` is also forbidden — its only use case here would
be to resolve a home-relative path."""

from __future__ import annotations

from pathlib import Path

# Files under explicit research-namespace control. If new files are
# added, this list MUST be updated to keep coverage honest.
RESEARCH_FILES = [
    "apps/api/src/api/research.py",
    "apps/web/src/lib/research/forbiddenTokens.ts",
    "apps/web/src/components/research/ResearchBanner.tsx",
    "apps/web/src/components/research/ResearchSafetyFailure.tsx",
    "apps/web/src/components/research/ResearchIntelligenceTab.tsx",
    "apps/web/src/components/research/ResearchPulseCard.tsx",
    "apps/web/src/components/research/ResearchJobHealthCard.tsx",
]


def test_no_home_relative_paths_in_research_code():
    for rel in RESEARCH_FILES:
        path = Path(rel)
        if not path.exists():
            # Phase B may not yet have all client files in test env
            continue
        src = path.read_text(encoding="utf-8")
        # Forbid `~/.foo` literal references and `os.path.expanduser(`
        # AND `Path.home(` and `process.env.HOME` style.
        for tok in (
            "~/.",
            "os.path.expanduser",
            "Path.home(",
            "process.env.HOME",
        ):
            assert tok not in src, (
                f"Forbidden home-relative path token {tok!r} in {rel}"
            )


def test_no_filesystem_memory_paths_referenced():
    """Reject any reference to known external filesystem-memory dirs."""
    for rel in RESEARCH_FILES:
        path = Path(rel)
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        for tok in (
            ".tradingagents",
            ".vibe-trading",
            ".openalice",
            ".ai-trader",
        ):
            assert tok not in src, (
                f"Forbidden filesystem-memory ref {tok!r} in {rel}"
            )
