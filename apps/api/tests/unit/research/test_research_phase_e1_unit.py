"""Phase 11W (Phase E.1) — pure-unit guards.

No DB. No network. Verifies the structural invariants:
  * No scheduler / worker / execution imports.
  * No reflection feedback path.
  * Operator allowlist parsing is deterministic.
  * Anomaly detection module declares no execution / ML / LLM
    imports.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


PHASE_E1_FILES = (
    "apps/api/src/research/manual_run_controls.py",
    "apps/api/src/research/manual_run_safe.py",
    "apps/api/src/api/research_manual.py",
    "scripts/run_research_manual.py",
)


def _read(rel: str) -> str:
    p = Path(rel)
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ---------------------------------------------------------------------------
# 12. test_no_scheduler_entry_phase_e1
# ---------------------------------------------------------------------------


def test_no_scheduler_entry_phase_e1():
    worker_dir = Path("apps/worker/src")
    if not worker_dir.exists():
        pytest.skip("worker dir absent")
    bad: list[str] = []
    for p in worker_dir.rglob("*.py"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if (
            "manual_run_controls" in src
            or "manual_run_safe" in src
            or "research_manual_run_audit" in src
        ):
            bad.append(str(p))
    assert not bad, f"scheduler references Phase E.1 module: {bad}"


# ---------------------------------------------------------------------------
# 13. test_no_worker_registry_entry_phase_e1
# ---------------------------------------------------------------------------


def test_no_worker_registry_entry_phase_e1():
    reg = Path("apps/worker/src/jobs/registry.py")
    if not reg.exists():
        pytest.skip("registry absent")
    src = reg.read_text(encoding="utf-8")
    for token in (
        "manual_run_controls", "manual_run_safe",
        "research_manual_run_audit", "research_manual",
    ):
        assert token not in src, f"registry has {token!r}"


# ---------------------------------------------------------------------------
# 14. test_no_execution_imports_phase_e1
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORTS = (
    "apps.api.src.domain.features.feature_engine",
    "apps.api.src.domain.recommendations.recommendation_engine",
    "apps.api.src.data.evaluation",
    "apps.api.src.domain.stock_engine.decision_engine",
    "apps.api.src.options.paper",
    "apps.api.src.domain.execution",
    "langchain", "langgraph",
)


@pytest.mark.parametrize("rel", PHASE_E1_FILES)
def test_no_execution_imports_phase_e1(rel):
    src = _read(rel)
    for bad in _FORBIDDEN_IMPORTS:
        assert bad not in src, f"{rel} references {bad!r}"


# ---------------------------------------------------------------------------
# 15. test_no_reflection_feedback_phase_e1
# ---------------------------------------------------------------------------


def test_no_reflection_feedback_phase_e1():
    """Phase E.1 must not introduce a code path that lets reflection
    rows feed back into trading or scoring."""
    for d in (
        "apps/api/src/domain/features",
        "apps/api/src/domain/recommendations",
        "apps/api/src/data/evaluation",
        "apps/worker/src",
    ):
        path = Path(d)
        if not path.exists():
            continue
        for p in path.rglob("*.py"):
            src = p.read_text(encoding="utf-8", errors="ignore")
            assert "research_reflection" not in src, (
                f"reflection feedback in {p}"
            )
            assert "research_manual_run_audit" not in src, (
                f"audit log read by execution path in {p}"
            )


# ---------------------------------------------------------------------------
# Allowlist + anomaly module load-time invariants
# ---------------------------------------------------------------------------


def test_csv_set_helper():
    from apps.api.src.research.manual_run_controls import _csv_set
    assert _csv_set("") == frozenset()
    assert _csv_set(None) == frozenset()
    assert _csv_set("op-a, op-b ,op-c") == frozenset(
        {"op-a", "op-b", "op-c"}
    )


def test_anomaly_module_lazy_imports_only():
    """`manual_run_controls` must not import any provider SDK or
    execution module at load time."""
    src = _read("apps/api/src/research/manual_run_controls.py")
    for bad in ("anthropic", "google.generativeai"):
        # Allowed only inside function bodies (lazy). Top-level
        # `import` lines must not reference these.
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert bad not in stripped, (
                    f"top-level import references {bad!r}: {stripped}"
                )


# ---------------------------------------------------------------------------
# Allowlist semantics
# ---------------------------------------------------------------------------


def test_operator_allowlist_empty_in_production_rejects(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_ALLOWED_OPERATORS", "")
    monkeypatch.setattr(settings, "RESEARCH_LOCAL_TEST_MODE", False)
    from apps.api.src.research.manual_run_controls import is_operator_allowed
    assert is_operator_allowed("anyone") is False
    assert is_operator_allowed("") is False


def test_operator_allowlist_local_test_mode_allows_anyone(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "RESEARCH_ALLOWED_OPERATORS", "")
    monkeypatch.setattr(settings, "RESEARCH_LOCAL_TEST_MODE", True)
    from apps.api.src.research.manual_run_controls import is_operator_allowed
    assert is_operator_allowed("anyone") is True
    # But empty string still rejected.
    assert is_operator_allowed("") is False


def test_operator_allowlist_explicit_list(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(
        settings, "RESEARCH_ALLOWED_OPERATORS", "alice, bob",
    )
    monkeypatch.setattr(settings, "RESEARCH_LOCAL_TEST_MODE", False)
    from apps.api.src.research.manual_run_controls import is_operator_allowed
    assert is_operator_allowed("alice") is True
    assert is_operator_allowed("bob") is True
    assert is_operator_allowed("eve") is False
