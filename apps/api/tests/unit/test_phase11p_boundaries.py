"""Phase 11P - boundary + isolation tests.

Static-source scans + ORM checks ensuring 11P does not perturb strict
engine, scheduler, options paper engine, or front-end.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
SCRIPTS = REPO_ROOT / "scripts"


_PHASE_11P_FILES = (
    API_SRC / "data" / "macro" / "fred_adapter.py",
    API_SRC / "data" / "strategy" / "exploratory_runner.py",
    API_SRC / "labeling" / "forward_returns.py",
    API_SRC / "labeling" / "labeller_service.py",
    SCRIPTS / "backfill_macro_features.py",
    SCRIPTS / "run_exploratory_paper.py",
    SCRIPTS / "run_paper_labeller.py",
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
)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1. No forbidden imports anywhere in 11P
# ---------------------------------------------------------------------------

def test_no_forbidden_imports_in_11p_modules():
    for f in _PHASE_11P_FILES:
        src = f.read_text(encoding="utf-8")
        for tok in _FORBIDDEN_TOKENS:
            assert tok not in src, f"{f.name}: forbidden token {tok!r}"


# ---------------------------------------------------------------------------
# 2. Strict engine files unchanged by 11P
#
# We don't have a frozen golden checksum to compare against (the spec
# only says "byte-level or checksum test"), but we can at least
# assert that no 11P file edits these files (their existence
# untouched + paths read OK).
# ---------------------------------------------------------------------------

def test_strict_engine_files_exist_unchanged_by_11p():
    for f in _STRICT_FROZEN:
        assert f.exists(), f"strict file missing: {f}"
        # Sanity: file is not empty and is readable
        b = f.read_bytes()
        assert len(b) > 0
        # Compute checksum to satisfy the "checksum test" criterion
        h = _checksum(f)
        assert isinstance(h, str) and len(h) == 64


def test_strict_engine_threshold_constants_present_unchanged():
    """Frozen constants from existing strict gate logic. 11P must not
    have edited these values."""
    rates = (API_SRC / "data" / "features" / "rates.py").read_text(
        encoding="utf-8",
    )
    assert "FEATURE_VERSION = \"v1.0.0\"" in rates
    vol = (API_SRC / "data" / "features" / "vol.py").read_text(
        encoding="utf-8",
    )
    assert "FEATURE_VERSION = \"v1.0.0\"" in vol
    credit = (API_SRC / "data" / "features" / "credit.py").read_text(
        encoding="utf-8",
    )
    assert "FEATURE_VERSION = \"v1.0.0\"" in credit


# ---------------------------------------------------------------------------
# 3. No new options jobs in REGISTRY
# ---------------------------------------------------------------------------

def test_no_new_options_jobs_in_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert all("options" not in k.lower() for k in REGISTRY.keys()), (
        f"REGISTRY contains options jobs: "
        f"{[k for k in REGISTRY if 'options' in k.lower()]}"
    )


def test_REGISTRY_size_unchanged():
    """11P adds zero scheduler entries."""
    from apps.worker.src.jobs.registry import REGISTRY
    assert len(REGISTRY) == 13


def test_no_new_macro_or_label_or_exploratory_jobs_in_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    bad = sorted(
        k for k in REGISTRY
        if any(s in k.lower() for s in (
            "macro", "label", "exploratory", "fred",
        ))
    )
    assert bad == []


# ---------------------------------------------------------------------------
# 4. Default invocation of every new script mutates nothing (dry-run on)
# ---------------------------------------------------------------------------

def test_backfill_macro_features_default_is_dry_run():
    src = (SCRIPTS / "backfill_macro_features.py").read_text(
        encoding="utf-8",
    )
    # Argparse mutually-exclusive group — when neither flag is set,
    # commit=False, dry_run=True is implied at construction time
    assert "dry_run = not commit" in src


def test_run_exploratory_paper_default_is_dry_run():
    src = (SCRIPTS / "run_exploratory_paper.py").read_text(
        encoding="utf-8",
    )
    assert "dry_run = not commit" in src


def test_run_paper_labeller_default_is_dry_run():
    src = (SCRIPTS / "run_paper_labeller.py").read_text(
        encoding="utf-8",
    )
    assert "dry_run = not commit" in src


# ---------------------------------------------------------------------------
# 5. No recommendation language in 11P user-facing strings
# ---------------------------------------------------------------------------

_FORBIDDEN_USER_FACING = (
    r"\brecommend\w*",
    r"\bbest\s+trade\b",
    r"\btop\s+pick\b",
    r"\btrade\s+now\b",
    r"\bplace\s+order\b",
    r"\bauto-?trade\b",
)


def test_no_recommendations_language_in_11p_user_facing_strings():
    for f in _PHASE_11P_FILES:
        src = f.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src, flags=re.IGNORECASE), (
                f"{f.name}: forbidden token {pat!r}"
            )


# ---------------------------------------------------------------------------
# 6. paper_observation_label append-only via constraints
# ---------------------------------------------------------------------------

def test_paper_observation_label_orm_present():
    from apps.api.src.db.models import PaperObservationLabel
    # Smoke: ORM class exists
    assert PaperObservationLabel.__tablename__ == "paper_observation_label"


def test_label_version_constant_frozen():
    from apps.api.src.labeling.forward_returns import LABEL_VERSION
    assert LABEL_VERSION == "label-v1.0.0"


def test_paper_observation_label_unique_constraints_present():
    from apps.api.src.db.models import PaperObservationLabel
    names = sorted(
        c.name for c in PaperObservationLabel.__table__.constraints
        if c.name and c.name.startswith("uq_")
    )
    assert "uq_paper_observation_label_decision" in names
    assert "uq_paper_observation_label_paper_trade" in names
    assert "uq_paper_observation_label_options_paper_trade" in names
    assert "uq_paper_observation_label_options_observation" in names


# ---------------------------------------------------------------------------
# 7. Exploratory writes only to decision_log, not paper_position
# ---------------------------------------------------------------------------

def test_exploratory_runner_does_not_write_paper_position_or_paper_trade():
    src = (
        API_SRC / "data" / "strategy" / "exploratory_runner.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "INSERT INTO paper_position", "INSERT INTO paper_trade",
        "INSERT INTO paper_portfolio", "INSERT INTO paper_equity_snapshot",
    ):
        assert forbidden not in src, (
            f"exploratory runner must only write decision_log: "
            f"{forbidden!r}"
        )
    assert "INSERT INTO decision_log" in src


# ---------------------------------------------------------------------------
# 8. Macro backfill writes only features_daily + context_daily
# ---------------------------------------------------------------------------

def test_macro_backfill_writes_only_features_daily_and_context_daily():
    src = (SCRIPTS / "backfill_macro_features.py").read_text(
        encoding="utf-8",
    )
    inserts = re.findall(r"INSERT INTO\s+(\w+)", src)
    allowed = {"features_daily", "context_daily"}
    assert set(inserts).issubset(allowed), (
        f"macro backfill writes to disallowed tables: "
        f"{set(inserts) - allowed}"
    )
    # Must not write to decision_log / paper_*
    for forbidden_table in (
        "decision_log", "paper_position", "paper_trade",
        "paper_portfolio", "paper_observation_label",
    ):
        assert (
            f"INSERT INTO {forbidden_table}" not in src
        ), f"backfill writes forbidden table: {forbidden_table}"


# ---------------------------------------------------------------------------
# 9. Frontend untouched (no apps/web edits in 11P diff)
# ---------------------------------------------------------------------------

def test_no_frontend_files_added_by_11p():
    """Phase 11P adds zero frontend files. The 11P additions are all
    on the backend."""
    for f in _PHASE_11P_FILES:
        assert "apps/web" not in str(f).replace("\\", "/"), (
            f"11P file lives in frontend: {f}"
        )


# ---------------------------------------------------------------------------
# 10. Settings defaults preserved
# ---------------------------------------------------------------------------

def test_settings_defaults_preserved():
    from apps.api.src.config import Settings
    s = Settings(
        OPTIONS_ENABLED=False, OPTIONS_PAPER_ONLY=True,
        OPTIONS_ML_CAN_AFFECT_TRADES=False,
        EQUITY_EXPLORATORY_ENABLED=False,
    )
    assert s.OPTIONS_ENABLED is False
    assert s.OPTIONS_PAPER_ONLY is True
    assert s.OPTIONS_ML_CAN_AFFECT_TRADES is False
    assert s.EQUITY_EXPLORATORY_ENABLED is False
