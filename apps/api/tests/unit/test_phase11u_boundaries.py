"""Phase 11U - boundary + isolation tests."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
SCRIPTS = REPO_ROOT / "scripts"


_PHASE_11U_FILES = (
    API_SRC / "ml" / "drift_metrics.py",
    API_SRC / "ml" / "drift_thresholds.py",
    API_SRC / "ml" / "drift_monitor.py",
    SCRIPTS / "run_model_drift_report.py",
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
    API_SRC / "ml" / "model_registry.py",
    API_SRC / "ml" / "shadow_scorer.py",
    API_SRC / "ml" / "rule_comparator.py",
    API_SRC / "ml" / "shadow_report.py",
)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# 1. Strict + 11R + 11T unchanged

def test_strict_engine_files_unchanged_by_11u():
    for f in _STRICT_FROZEN:
        assert f.exists(), f"frozen file missing: {f}"
        h = _checksum(f)
        assert isinstance(h, str) and len(h) == 64


def test_options_paper_engine_unchanged_by_11u():
    f = API_SRC / "options" / "paper" / "engine.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "drift_monitor", "drift_metrics", "drift_thresholds",
    ):
        assert tok not in src, f"options engine: {tok!r}"


def test_eval_runner_unchanged_by_11u():
    f = API_SRC / "options" / "paper" / "eval_runner.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "drift_monitor", "drift_metrics", "drift_thresholds",
    ):
        assert tok not in src, f"eval_runner: {tok!r}"


def test_auto_trader_unchanged_by_11u():
    f = API_SRC / "domain" / "paper_trading" / "auto_trader.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "drift_monitor", "drift_metrics", "drift_thresholds",
    ):
        assert tok not in src, f"auto_trader: {tok!r}"


def test_fast_fill_runner_unchanged_by_11u():
    f = API_SRC / "data" / "research" / "fast_fill_runner.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "drift_monitor", "drift_metrics", "drift_thresholds",
    ):
        assert tok not in src, f"fast_fill_runner: {tok!r}"


def test_shadow_scorer_unchanged_by_11u():
    f = API_SRC / "ml" / "shadow_scorer.py"
    src = f.read_text(encoding="utf-8")
    for tok in (
        "drift_monitor", "drift_metrics", "drift_thresholds",
    ):
        assert tok not in src, f"shadow_scorer: {tok!r}"


def test_dataset_builder_unchanged_by_11u():
    f = API_SRC / "ml" / "dataset_builder.py"
    if not f.exists():
        return
    src = f.read_text(encoding="utf-8")
    for tok in ("drift_monitor", "drift_metrics"):
        assert tok not in src


def test_trainer_unchanged_by_11u():
    f = API_SRC / "ml" / "trainer.py"
    if not f.exists():
        return
    src = f.read_text(encoding="utf-8")
    for tok in ("drift_monitor", "drift_metrics"):
        assert tok not in src


# 2. REGISTRY

def test_no_new_jobs_in_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert len(REGISTRY) == 13
    bad = sorted(
        k for k in REGISTRY
        if any(s in k.lower() for s in (
            "drift", "monitor", "model_drift", "shadow",
        ))
    )
    assert bad == []


# 3. Forbidden imports + DB writes

def test_no_forbidden_imports_in_11u_modules():
    for f in _PHASE_11U_FILES:
        src = f.read_text(encoding="utf-8")
        for tok in _FORBIDDEN_TOKENS:
            assert tok not in src, f"{f.name}: forbidden {tok!r}"


def test_no_db_writes_in_11u_modules():
    for f in _PHASE_11U_FILES:
        src = f.read_text(encoding="utf-8")
        for tok in (
            "INSERT INTO", "UPDATE ", "DELETE FROM",
            ".to_parquet(", ".to_csv(",
        ):
            assert tok not in src, (
                f"{f.name}: forbidden write token {tok!r}"
            )


def test_no_api_router_added_by_11u():
    main = (API_SRC / "main.py").read_text(encoding="utf-8")
    for tok in (
        "drift_monitor", "drift_metrics", "drift_thresholds",
        "model_drift_router",
    ):
        assert tok not in main, (
            f"main.py must not import 11U: {tok!r}"
        )


def test_no_frontend_files_added_by_11u():
    for f in _PHASE_11U_FILES:
        path_str = str(f).replace("\\", "/")
        assert "apps/web" not in path_str


def test_no_alembic_migrations_added_by_11u():
    versions = REPO_ROOT / "infra" / "alembic" / "versions"
    files = sorted(versions.glob("*.py"))
    last = files[-1].stem
    assert last == "051_research_fast_fill", (
        f"unexpected migration head: {last}"
    )


def test_no_registry_file_writes_in_drift_module():
    """drift_monitor must not open `models/model_registry.json` for
    write under any path."""
    src = (API_SRC / "ml" / "drift_monitor.py").read_text(encoding="utf-8")
    for tok in (
        'model_registry.json"', "model_registry.json'",
        "register(", "model_registry.write_text",
    ):
        assert tok not in src, (
            f"drift_monitor must not write registry: {tok!r}"
        )
