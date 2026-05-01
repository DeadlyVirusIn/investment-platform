"""Phase 11W (Phase C) — boundary tests.

These are CI gates that fail the build if any Phase C module
violates the strict scope:
  * No execution / scoring / ML imports.
  * No POST routes added.
  * No worker file or scheduler entry referencing research.
  * No LLM client SDK import.
  * No new dependencies (langgraph / langchain still banned).
  * Phase B API behavior unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHASE_C_FILES = (
    "apps/api/src/research/__init__.py",
    "apps/api/src/research/schemas.py",
    "apps/api/src/research/safety.py",
    "apps/api/src/research/provenance.py",
    "apps/api/src/research/input_snapshot.py",
)


def _read(rel: str) -> str:
    p = Path(rel)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# All four Phase C source files exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", PHASE_C_FILES)
def test_phase_c_file_exists(rel):
    assert Path(rel).exists(), f"Missing Phase C file: {rel}"


# ---------------------------------------------------------------------------
# No execution / scoring / ML imports
# ---------------------------------------------------------------------------


FORBIDDEN_IMPORT_TARGETS = (
    "feature_engine",
    "recommendation_engine",
    "shadow_scorer",
    "drift_monitor",
    "auto_trader",
    "paper_execution",
    "submit_trade",
    "auto_trade_portfolio",
)


@pytest.mark.parametrize("rel", PHASE_C_FILES)
def test_phase_c_module_does_not_import_execution_or_ml(rel):
    src = _read(rel)
    if not src:
        pytest.skip(f"{rel} not present")
    import_lines = [
        line for line in src.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    for tok in FORBIDDEN_IMPORT_TARGETS:
        assert tok not in joined, (
            f"Forbidden import {tok!r} in {rel}: {joined!r}"
        )


# ---------------------------------------------------------------------------
# No LLM client SDK imports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", PHASE_C_FILES)
def test_phase_c_module_does_not_import_llm_client(rel):
    src = _read(rel)
    if not src:
        pytest.skip(f"{rel} not present")
    forbidden = (
        "from anthropic", "import anthropic",
        "from openai", "import openai",
        "from google.generativeai", "from langchain", "import langchain",
        "from langgraph", "import langgraph",
        "from vercel_ai", "from llama_index",
    )
    for tok in forbidden:
        assert tok not in src, f"Forbidden LLM client import {tok!r} in {rel}"


# ---------------------------------------------------------------------------
# Phase B API surface unchanged: research.py still has 4 GET routes
# only, no POST.
# ---------------------------------------------------------------------------


def test_phase_b_research_router_unchanged_to_get_only():
    from apps.api.src.api.research import router as research_router

    forbidden = {"POST", "PUT", "PATCH", "DELETE"}
    paths = []
    for route in research_router.routes:
        methods = getattr(route, "methods", set())
        path = getattr(route, "path", "?")
        paths.append(path)
        assert forbidden.isdisjoint(methods), (
            f"Phase C added a non-GET method on {path}: {methods}"
        )
    # Phase B route count was 4. Phase C must NOT add any.
    assert len(paths) == 4, (
        f"Phase C must not add API routes. Found {len(paths)}: {paths}"
    )


def test_phase_b_research_router_no_manual_endpoint():
    from apps.api.src.api.research import router as research_router

    for route in research_router.routes:
        path = getattr(route, "path", "")
        assert "manual" not in path, (
            f"Forbidden /manual endpoint registered at {path!r}"
        )


# ---------------------------------------------------------------------------
# No worker / scheduler entry references research
# ---------------------------------------------------------------------------


def test_no_research_worker_module_in_phase_c():
    jobs_dir = Path("apps/worker/src/jobs")
    if not jobs_dir.is_dir():
        return
    research_files = sorted(p.name for p in jobs_dir.glob("research_*.py"))
    assert research_files == [], (
        f"Phase C forbids research worker files; found: {research_files}"
    )


def test_no_research_scheduler_entry_in_phase_c():
    src = _read("apps/worker/src/scheduler/tick_loop.py")
    if not src:
        return
    forbidden_patterns = (
        '"research_run', "'research_run",
        "research_orchestrator", "research_intelligence",
    )
    for pat in forbidden_patterns:
        assert pat not in src, (
            f"Forbidden research scheduler reference {pat!r}"
        )


def test_no_research_registry_entry_in_phase_c():
    src = _read("apps/worker/src/jobs/registry.py")
    if not src:
        return
    forbidden_patterns = (
        '"research_run', "'research_run",
        '"research_intelligence', "'research_intelligence",
    )
    for pat in forbidden_patterns:
        assert pat not in src, (
            f"Forbidden research registry key {pat!r}"
        )


# ---------------------------------------------------------------------------
# Dependency lint — langgraph / langchain still banned
# ---------------------------------------------------------------------------


def test_langgraph_still_banned_in_pyproject():
    src = _read("pyproject.toml")
    in_optional = False
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("[project.optional-dependencies"):
            in_optional = True
            continue
        if s.startswith("[tool.") or s.startswith("[build"):
            in_optional = False
            continue
        if in_optional:
            continue
        if re.match(r"^\s*['\"]?langgraph['\"]?[\s>=<,]", line):
            raise AssertionError(
                f"langgraph reintroduced as runtime dep: {line!r}"
            )


def test_langchain_still_banned_in_pyproject():
    src = _read("pyproject.toml")
    in_optional = False
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("[project.optional-dependencies"):
            in_optional = True
            continue
        if s.startswith("[tool.") or s.startswith("[build"):
            in_optional = False
            continue
        if in_optional:
            continue
        if re.match(r"^\s*['\"]?langchain[a-z\-]*['\"]?[\s>=<,]", line):
            raise AssertionError(
                f"langchain reintroduced as runtime dep: {line!r}"
            )


# ---------------------------------------------------------------------------
# No filesystem-egress in Phase C modules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", PHASE_C_FILES)
def test_phase_c_no_home_relative_paths(rel):
    src = _read(rel)
    if not src:
        pytest.skip(f"{rel} not present")
    for tok in (
        "~/.", "os.path.expanduser", "Path.home(",
        ".tradingagents", ".vibe-trading", ".openalice",
    ):
        assert tok not in src, (
            f"Forbidden filesystem reference {tok!r} in {rel}"
        )


# ---------------------------------------------------------------------------
# No DB-mutation patterns in Phase C source modules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", [
    "apps/api/src/research/safety.py",
    "apps/api/src/research/provenance.py",
    "apps/api/src/research/input_snapshot.py",
    "apps/api/src/research/schemas.py",
])
def test_phase_c_modules_have_no_db_mutation_helpers(rel):
    src = _read(rel)
    if not src:
        pytest.skip(f"{rel} not present")
    for tok in (
        "session.add(", "session.commit(", "session.flush(",
        "session.delete(", "session.merge(",
        "INSERT INTO", "UPDATE ", "DELETE FROM",
    ):
        assert tok not in src, f"Forbidden DB mutation token {tok!r} in {rel}"
