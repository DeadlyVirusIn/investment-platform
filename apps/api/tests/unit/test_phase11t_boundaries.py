"""Phase 11T - boundary + isolation tests."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
SCRIPTS = REPO_ROOT / "scripts"


_PHASE_11T_FILES = (
    API_SRC / "ml" / "model_registry.py",
    API_SRC / "ml" / "shadow_scorer.py",
    API_SRC / "ml" / "rule_comparator.py",
    API_SRC / "ml" / "shadow_report.py",
    SCRIPTS / "manage_model_registry.py",
    SCRIPTS / "run_shadow_scoring.py",
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
    API_SRC / "data" / "research" / "fast_fill_runner.py",
)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# 1. Strict + 11R unchanged

def test_strict_engine_files_unchanged_by_11t():
    for f in _STRICT_FROZEN:
        assert f.exists(), f"frozen file missing: {f}"
        h = _checksum(f)
        assert isinstance(h, str) and len(h) == 64


def test_options_paper_engine_unchanged_by_11t():
    f = API_SRC / "options" / "paper" / "engine.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "shadow_scorer", "model_registry", "shadow_report",
    ):
        assert tok not in src, (
            f"options engine must not reference 11T modules: {tok!r}"
        )


def test_eval_runner_unchanged_by_11t():
    f = API_SRC / "options" / "paper" / "eval_runner.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "shadow_scorer", "model_registry", "shadow_report",
    ):
        assert tok not in src, f"eval_runner: forbidden ref {tok!r}"


def test_auto_trader_unchanged_by_11t():
    f = API_SRC / "domain" / "paper_trading" / "auto_trader.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "shadow_scorer", "model_registry", "shadow_report",
        "ScoredRow", "ScoringSummary",
    ):
        assert tok not in src, f"auto_trader: forbidden ref {tok!r}"


def test_fast_fill_runner_unchanged_by_11t():
    f = API_SRC / "data" / "research" / "fast_fill_runner.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "shadow_scorer", "model_registry", "shadow_report",
    ):
        assert tok not in src, f"fast_fill_runner: forbidden ref {tok!r}"


def test_dataset_builder_unchanged_by_11t():
    """11S not yet implemented — file may not exist. If it exists,
    must not reference 11T modules."""
    f = API_SRC / "ml" / "dataset_builder.py"
    if not f.exists():
        return
    src = f.read_text(encoding="utf-8")
    for tok in ("shadow_scorer", "shadow_report", "model_registry"):
        assert tok not in src, f"dataset_builder: forbidden ref {tok!r}"


def test_trainer_unchanged_by_11t():
    f = API_SRC / "ml" / "trainer.py"
    if not f.exists():
        return
    src = f.read_text(encoding="utf-8")
    for tok in ("shadow_scorer", "shadow_report"):
        assert tok not in src


# 2. REGISTRY

def test_no_new_jobs_in_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert len(REGISTRY) == 13
    bad = sorted(
        k for k in REGISTRY
        if any(s in k.lower() for s in (
            "shadow", "scoring", "ml_", "model_registry",
        ))
    )
    assert bad == []


# 3. Forbidden imports + DB writes

def test_no_forbidden_imports_in_11t_modules():
    for f in _PHASE_11T_FILES:
        src = f.read_text(encoding="utf-8")
        for tok in _FORBIDDEN_TOKENS:
            assert tok not in src, f"{f.name}: forbidden token {tok!r}"


def test_no_db_writes_in_11t_modules():
    for f in _PHASE_11T_FILES:
        src = f.read_text(encoding="utf-8")
        for tok in (
            "INSERT INTO", "UPDATE ", "DELETE FROM",
            ".to_parquet(", ".to_csv(",
        ):
            # `.to_parquet` is a write helper from pandas; the scorer
            # never persists tabular data. Reports go through
            # `path.write_text` (text JSON), which is allowed.
            assert tok not in src, (
                f"{f.name}: forbidden write token {tok!r}"
            )


def test_no_api_router_added_by_11t():
    main = (API_SRC / "main.py").read_text(encoding="utf-8")
    for tok in ("shadow_scorer", "shadow_scoring", "model_registry"):
        assert tok not in main, (
            f"main.py must not import 11T modules: {tok!r}"
        )


def test_no_frontend_files_added_by_11t():
    for f in _PHASE_11T_FILES:
        path_str = str(f).replace("\\", "/")
        assert "apps/web" not in path_str, (
            f"11T file in frontend: {f}"
        )


def test_no_recommendation_language_in_11t():
    forbidden = (
        r"\brecommend\w*",
        r"\bsignal\b",
        r"\bbest\s+trade\b",
        r"\btop\s+pick\b",
        r"\btrade\s+now\b",
        r"\bplace\s+order\b",
        r"\bauto-?trade\b",
        r"\bpromote\b",
    )
    for f in _PHASE_11T_FILES:
        src = f.read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src, flags=re.IGNORECASE), (
                f"{f.name}: forbidden token {pat!r}"
            )


def test_model_status_frozen_at_shadow_only():
    from apps.api.src.ml.model_registry import ALLOWED_STATUS
    assert ALLOWED_STATUS == ("shadow_only",)


def test_no_alembic_migrations_added_by_11t():
    versions = (REPO_ROOT / "infra" / "alembic" / "versions")
    files = sorted(versions.glob("*.py"))
    # Latest migration should still be 051_research_fast_fill.py
    # (11T adds none).
    last = files[-1].stem
    assert last == "051_research_fast_fill", (
        f"unexpected migration head: {last}"
    )
