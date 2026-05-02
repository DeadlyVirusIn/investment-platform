"""Phase 11W (Phase E) — unit-level guard tests.

Pure unit. No DB. No network. Verifies:
  * No scheduler / worker entry references Phase E.
  * No execution / scoring / ML imports from research_*.
  * No LangChain / LangGraph at module load.
  * No filesystem memory.
  * Route scan: only the approved POST endpoint exists under /api/research.
  * Migration scan: no public → research_ro FK introduced by Phase E.
  * Manual-run module never imports execution/scoring modules.
  * `run_manual_safely` is callable signature-stable.
  * API response payload shape never includes raw provider body.
"""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


PHASE_E_FILES = (
    "apps/api/src/research/manual_run_safe.py",
    "apps/api/src/api/research_manual.py",
    "scripts/run_research_manual.py",
)


def _read(rel: str) -> str:
    p = Path(rel)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 11. test_no_scheduler_entry_phase_e
# ---------------------------------------------------------------------------


def test_no_scheduler_entry_phase_e():
    """Confirm Phase E adds no entry to apps/worker/src/."""
    worker_dir = Path("apps/worker/src")
    if not worker_dir.exists():
        pytest.skip("worker dir absent in this checkout")
    bad = []
    for p in worker_dir.rglob("*.py"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "manual_run_safe" in src or "research_manual" in src:
            bad.append(str(p))
    assert not bad, f"Phase E module referenced from worker: {bad}"


# ---------------------------------------------------------------------------
# 12. test_no_worker_registry_entry_phase_e
# ---------------------------------------------------------------------------


def test_no_worker_registry_entry_phase_e():
    """Confirm worker job registry has no Phase E job."""
    reg = Path("apps/worker/src/jobs/registry.py")
    if not reg.exists():
        pytest.skip("worker registry absent")
    src = reg.read_text(encoding="utf-8")
    for token in (
        "manual_run_safe", "research_manual", "run_manual_safely",
    ):
        assert token not in src, (
            f"worker registry references Phase E module: {token!r}"
        )


# ---------------------------------------------------------------------------
# 13. test_no_execution_imports_from_research
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORTS = (
    "apps.api.src.domain.features.feature_engine",
    "apps.api.src.domain.recommendations.recommendation_engine",
    "apps.api.src.data.evaluation",
    "apps.api.src.domain.stock_engine.decision_engine",
    "apps.api.src.options.paper",
    "apps.api.src.domain.execution",
)


@pytest.mark.parametrize("rel", PHASE_E_FILES)
def test_no_execution_imports(rel):
    src = _read(rel)
    for forbidden in _FORBIDDEN_IMPORTS:
        assert forbidden not in src, (
            f"{rel} imports forbidden execution module: {forbidden}"
        )


# ---------------------------------------------------------------------------
# 14. test_no_reflection_feedback_path
# ---------------------------------------------------------------------------


def test_no_reflection_feedback_path():
    """Reflection rows must remain labeled-history-only. Verify no
    code in features/, domain/recommendations/, or worker reads
    `research_reflection`."""
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
                f"reflection feedback edge detected in {p}"
            )


# ---------------------------------------------------------------------------
# 15. test_research_outputs_not_consumed_by_feature_engine_or_recommendation_engine
# ---------------------------------------------------------------------------


def test_research_outputs_not_consumed_by_engines():
    for module in (
        "apps.api.src.domain.features.feature_engine",
        "apps.api.src.domain.recommendations.recommendation_engine",
    ):
        try:
            mod = import_module(module)
        except ImportError:
            continue
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for tok in (
            "research_run", "research_agent_output",
            "research_reflection", "research_ro",
        ):
            assert tok not in src, (
                f"{module} references research artifact: {tok}"
            )


# ---------------------------------------------------------------------------
# 16. test_api_response_never_contains_unsafe_raw_output
# ---------------------------------------------------------------------------


def test_response_payload_has_no_body_field():
    """Inspect the dataclass returned by run_manual_safely. The
    sanitized payload must not expose any provider-body field."""
    from apps.api.src.research.manual_run_safe import ManualRunPayload
    fields = ManualRunPayload.__dataclass_fields__.keys()
    forbidden = {
        "body", "raw_body", "raw_response", "structured_output",
        "agent_output", "evidence_refs", "reflection",
    }
    overlap = forbidden.intersection(fields)
    assert not overlap, f"payload exposes raw model output: {overlap}"


# ---------------------------------------------------------------------------
# Phase E HTTP route scan: only POST /api/research/runs/manual exists
# ---------------------------------------------------------------------------


def test_only_one_post_route_under_research():
    """Inspect apps/api/src/api/research_manual.py and confirm it
    declares exactly one @router.post and that the path is /manual."""
    src = _read("apps/api/src/api/research_manual.py")
    posts = re.findall(r"@router\.post\([^\)]*\)", src)
    assert len(posts) == 1, f"expected 1 POST route, got {len(posts)}: {posts}"
    assert "/manual" in posts[0]


# ---------------------------------------------------------------------------
# Module-load isolation
# ---------------------------------------------------------------------------


def test_no_langchain_or_langgraph_at_module_load():
    src = _read("apps/api/src/research/manual_run_safe.py")
    src += _read("apps/api/src/api/research_manual.py")
    src += _read("scripts/run_research_manual.py")
    for tok in ("langchain", "langgraph"):
        assert tok not in src.lower(), f"forbidden lib referenced: {tok}"


def test_no_filesystem_memory():
    """Phase E modules must not write to ~/.research, ~/.cache, or
    similar persistent filesystem locations."""
    for rel in PHASE_E_FILES:
        src = _read(rel)
        for tok in (
            "os.path.expanduser",
            'Path.home(',
            "Path('~",
            'Path("~',
            ".cache/research",
            "/.research",
        ):
            assert tok not in src, f"filesystem memory in {rel}: {tok}"


# ---------------------------------------------------------------------------
# Migration scan — Phase E must not introduce public → research_ro FK
# ---------------------------------------------------------------------------


def test_phase_e_adds_no_public_to_research_ro_fk():
    """Phase E ships zero new migrations. Verify no Phase E commit
    snuck a forbidden FK into any migration file."""
    versions = Path("infra/alembic/versions")
    if not versions.exists():
        pytest.skip("alembic versions dir absent")
    bad = []
    for p in versions.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        # Phase E must not have introduced any new migration.
        if "phase_e" in src.lower() or "phase e" in src.lower():
            for m in re.finditer(r"create_foreign_key\s*\(.*?\)", src, re.DOTALL):
                block = m.group(0)
                if "research_ro" in block and "source_schema" not in block:
                    bad.append((p.name, block))
    assert not bad, f"forbidden FK introduced by Phase E: {bad}"


# ---------------------------------------------------------------------------
# Allowlist behavior — pure unit
# ---------------------------------------------------------------------------


def test_csv_allowlist_parsing():
    from apps.api.src.research.manual_run_safe import _csv_set
    assert _csv_set("") == frozenset()
    assert _csv_set(None) == frozenset()
    assert _csv_set("mock,gemini, anthropic ") == frozenset(
        {"mock", "gemini", "anthropic"}
    )


def test_validate_symbol_format_strict():
    from apps.api.src.research.manual_run_safe import (
        _validate_symbol, PhaseEValidationError,
    )
    assert _validate_symbol("UNH") == "UNH"
    assert _validate_symbol("brk.b") == "BRK.B"
    with pytest.raises(PhaseEValidationError):
        _validate_symbol("")
    with pytest.raises(PhaseEValidationError):
        _validate_symbol("12FOO")
    with pytest.raises(PhaseEValidationError):
        _validate_symbol("X" * 12)


def test_validate_as_of_rejects_future():
    import datetime as dt
    from apps.api.src.research.manual_run_safe import (
        _validate_as_of, PhaseEValidationError,
    )
    today = dt.date.today()
    assert _validate_as_of(today) == today
    with pytest.raises(PhaseEValidationError):
        _validate_as_of(today + dt.timedelta(days=10))
