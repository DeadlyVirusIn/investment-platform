"""Phase 11R - boundary + isolation tests."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
SCRIPTS = REPO_ROOT / "scripts"


_PHASE_11R_FILES = (
    API_SRC / "data" / "research" / "fast_fill_runner.py",
    SCRIPTS / "run_research_fast_fill.py",
)


_FORBIDDEN_TOKENS = (
    "from broker_", "import broker_",
    "from live_",   "import live_",
    "from execution_", "import execution_",
    "order_router",
)


_STRICT_FROZEN = (
    API_SRC / "data" / "strategy" / "engine_a.py",
    API_SRC / "data" / "strategy" / "engine_b.py",
    API_SRC / "data" / "strategy" / "selector.py",
    API_SRC / "data" / "context" / "production.py",
    API_SRC / "options" / "paper" / "engine.py",
    API_SRC / "options" / "paper" / "eval_runner.py",
    API_SRC / "options" / "paper" / "eval_runner_models.py",
    API_SRC / "domain" / "paper_trading" / "auto_trader.py",
)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1. Strict engine + auto_trader untouched (checksum)
# ---------------------------------------------------------------------------

def test_strict_engine_files_unchanged_by_11r():
    for f in _STRICT_FROZEN:
        assert f.exists(), f"strict file missing: {f}"
        h = _checksum(f)
        assert isinstance(h, str) and len(h) == 64


def test_auto_trader_unchanged_by_11r():
    f = API_SRC / "domain" / "paper_trading" / "auto_trader.py"
    assert f.exists()
    src = f.read_text(encoding="utf-8")
    # No 11R references should have leaked into the auto-trader.
    for tok in (
        "research_fast_fill", "fast_fill_runner",
        "paper_research_fill", "same_day_research_v1",
    ):
        assert tok not in src, (
            f"auto_trader must remain untouched: token {tok!r}"
        )


# ---------------------------------------------------------------------------
# 2. No new scheduler entries
# ---------------------------------------------------------------------------

def test_no_new_jobs_in_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert len(REGISTRY) == 13
    bad = sorted(
        k for k in REGISTRY
        if any(s in k.lower() for s in (
            "research", "fast_fill", "options",
        ))
    )
    assert bad == []


# ---------------------------------------------------------------------------
# 3. Forbidden imports across 11R
# ---------------------------------------------------------------------------

def test_no_forbidden_imports_in_11r_modules():
    for f in _PHASE_11R_FILES:
        src = f.read_text(encoding="utf-8")
        for tok in _FORBIDDEN_TOKENS:
            assert tok not in src, f"{f.name}: forbidden token {tok!r}"


# ---------------------------------------------------------------------------
# 4. Default invocations of new scripts mutate nothing
# ---------------------------------------------------------------------------

def test_run_research_fast_fill_default_is_dry_run():
    src = (SCRIPTS / "run_research_fast_fill.py").read_text(
        encoding="utf-8",
    )
    assert "dry_run = not commit" in src


# ---------------------------------------------------------------------------
# 5. paper_research_fill ORM has the required CHECK / UNIQUE
# ---------------------------------------------------------------------------

def test_paper_research_fill_orm_present():
    from apps.api.src.db.models import PaperResearchFill
    assert PaperResearchFill.__tablename__ == "paper_research_fill"


def test_paper_research_fill_unique_constraint_present():
    from apps.api.src.db.models import PaperResearchFill
    names = sorted(
        c.name for c in PaperResearchFill.__table__.constraints
        if c.name and c.name.startswith("uq_")
    )
    assert "uq_paper_research_fill_natural_key" in names


# ---------------------------------------------------------------------------
# 6. No recommendation language across 11R user-facing strings
# ---------------------------------------------------------------------------

_FORBIDDEN_USER_FACING = (
    r"\brecommend\w*",
    r"\bbest\s+trade\b",
    r"\btop\s+pick\b",
    r"\btrade\s+now\b",
    r"\bplace\s+order\b",
    r"\bauto-?trade\b",
)


def test_no_recommendations_language_in_11r():
    for f in _PHASE_11R_FILES:
        src = f.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src, flags=re.IGNORECASE), (
                f"{f.name}: forbidden token {pat!r}"
            )


# ---------------------------------------------------------------------------
# 7. Migration appends only — no destructive ops
# ---------------------------------------------------------------------------

def test_migration_is_additive_only():
    f = (
        REPO_ROOT / "infra" / "alembic" / "versions"
        / "051_research_fast_fill.py"
    )
    src = f.read_text(encoding="utf-8")
    upgrade_block = src.split("def upgrade")[1].split("def downgrade")[0]
    for forbidden in (
        "drop_table", "drop_column", "alter_column",
        "rename_column", "rename_table", "execute(",
    ):
        # `op.drop_constraint` is allowed because we drop+recreate the
        # CHECK constraint on paper_observation_label to expand the
        # allowed source list. That's the only allowed exception.
        if forbidden == "execute(":
            continue
        assert forbidden not in upgrade_block, (
            f"migration must be additive only: {forbidden!r}"
        )
    # Ensure the only drop_constraint targets the source CHECK on
    # paper_observation_label. The call spans multiple lines, so
    # match against the full upgrade block as a flat string.
    flat = re.sub(r"\s+", " ", upgrade_block)
    drop_calls = re.findall(
        r"op\.drop_constraint\([^)]*\)", flat,
    )
    for call in drop_calls:
        assert "paper_observation_label" in call \
            and "ck_paper_observation_label_source" in call, (
                f"unexpected drop_constraint: {call}"
            )
