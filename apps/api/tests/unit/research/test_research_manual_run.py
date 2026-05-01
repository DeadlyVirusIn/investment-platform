"""Phase 11W (Phase D.1) — manual run + prompt + boundary tests.

The DB-touching insertion paths are exercised by the integration
test in test_research_manual_insert_pg.py. This file covers the
pure-fn, prompt, source-level, and boundary properties.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from apps.api.src.research.prompts import (
    PROMPT_TEMPLATE_ID,
    PROMPT_TEMPLATE_VERSION,
    SINGLE_ASSET_CONTEXT_NOTE_V1,
    render_single_asset_context_note,
)
from apps.api.src.research.provenance import compute_prompt_hash
from apps.api.src.research.safety import validate_research_text


# ---------------------------------------------------------------------------
# Prompt determinism + hash stability
# ---------------------------------------------------------------------------


def test_prompt_template_id_and_version_frozen():
    assert PROMPT_TEMPLATE_ID == "single_asset_context_note_v1"
    assert PROMPT_TEMPLATE_VERSION == 1


def test_prompt_renders_deterministically():
    a = render_single_asset_context_note(
        symbol="AAPL", as_of=dt.date(2026, 4, 30),
        asset_meta={"name": "Apple Inc"},
        context_gates={"rates_calm": False},
        candidate=None,
    )
    b = render_single_asset_context_note(
        symbol="AAPL", as_of=dt.date(2026, 4, 30),
        asset_meta={"name": "Apple Inc"},
        context_gates={"rates_calm": False},
        candidate=None,
    )
    assert a == b


def test_prompt_hash_is_stable_across_calls():
    rendered = render_single_asset_context_note(
        symbol="MSFT", as_of=dt.date(2026, 4, 30),
        asset_meta=None, context_gates=None, candidate=None,
    )
    h1 = compute_prompt_hash(rendered)
    h2 = compute_prompt_hash(rendered)
    assert h1 == h2
    assert len(h1) == 64


def test_prompt_renderer_invariant_to_dict_key_order():
    a = render_single_asset_context_note(
        symbol="AAPL", as_of=dt.date(2026, 4, 30),
        asset_meta={"a": 1, "b": 2, "c": 3},
        context_gates=None, candidate=None,
    )
    b = render_single_asset_context_note(
        symbol="AAPL", as_of=dt.date(2026, 4, 30),
        asset_meta={"c": 3, "b": 2, "a": 1},
        context_gates=None, candidate=None,
    )
    assert a == b


def test_prompt_renderer_rejects_empty_symbol():
    with pytest.raises(ValueError):
        render_single_asset_context_note(
            symbol="", as_of=dt.date(2026, 4, 30),
            asset_meta=None, context_gates=None, candidate=None,
        )


def test_prompt_renderer_rejects_non_date_as_of():
    with pytest.raises(ValueError):
        render_single_asset_context_note(
            symbol="AAPL",
            as_of="2026-04-30",  # type: ignore[arg-type]
            asset_meta=None, context_gates=None, candidate=None,
        )


# ---------------------------------------------------------------------------
# Prompt source does not contain forbidden tokens
# ---------------------------------------------------------------------------


def test_prompt_template_source_passes_safety_validator():
    """Sanity check: the template body itself must NOT match any
    forbidden-token regex. If the prompt itself were unsafe, models
    would copy the bad pattern back."""
    ok, matched = validate_research_text(SINGLE_ASSET_CONTEXT_NOTE_V1)
    assert ok is True, (
        f"Prompt template contains forbidden token {matched!r}"
    )


def test_prompts_module_source_has_no_action_tokens_outside_format_braces():
    """Stronger source-grep: scan the prompts.py file directly for
    bare forbidden-token literals. Allows the literal strings inside
    test/example positions only when they appear inside `{}` format
    placeholders (none should)."""
    src = Path(
        "apps/api/src/research/prompts.py"
    ).read_text(encoding="utf-8")
    # Action verbs we MUST NOT see outside docstrings/comments.
    forbidden_re = re.compile(
        r"\b(buy|sell|hold|long|short|recommend|signal|allocate|"
        r"execute|position|entry|exit|leverage)\b",
        re.IGNORECASE,
    )
    # Strip docstrings (heuristic: triple-quoted blocks).
    no_docstrings = re.sub(
        r'"""[\s\S]*?"""',
        "",
        src,
    )
    # Allow occurrences inside the template body — find those by
    # locating the template constant value and then EXCLUDING it.
    # Simpler: assert no forbidden token outside docstrings.
    assert forbidden_re.search(no_docstrings) is None, (
        f"Forbidden token in prompts.py source: "
        f"{forbidden_re.search(no_docstrings).group(0)!r}"  # type: ignore[union-attr]
    )


# ---------------------------------------------------------------------------
# Manual run — provider resolution + ValueError on unknown provider
# ---------------------------------------------------------------------------


def test_manual_run_rejects_unknown_provider_name():
    from apps.api.src.research.manual_run import _resolve_provider

    with pytest.raises(ValueError) as excinfo:
        _resolve_provider("openai")
    assert "Phase D.1" in str(excinfo.value) or "mock" in str(excinfo.value)


def test_manual_run_resolves_mock_provider_by_name():
    from apps.api.src.research.manual_run import _resolve_provider
    from apps.api.src.research.providers.mock_provider import (
        MockResearchProvider,
    )

    p = _resolve_provider("mock")
    assert isinstance(p, MockResearchProvider)


def test_manual_run_phase_d1_constants_frozen():
    from apps.api.src.research.manual_run import (
        PHASE_D1_AGENT_ROLE,
        PHASE_D1_PROMPT_BUNDLE_VERSION,
        PHASE_D1_SCHEMA_VERSION,
    )

    assert PHASE_D1_AGENT_ROLE == "fundamentals"
    assert PHASE_D1_SCHEMA_VERSION == "research-run-v1.0.0"
    assert PHASE_D1_PROMPT_BUNDLE_VERSION == "single-asset-v1.0.0"


# ---------------------------------------------------------------------------
# Boundary — no API routes changed (Phase B + C invariants intact)
# ---------------------------------------------------------------------------


def test_research_router_still_get_only_after_phase_d1():
    from apps.api.src.api.research import router as research_router

    forbidden = {"POST", "PUT", "PATCH", "DELETE"}
    routes = list(research_router.routes)
    assert len(routes) == 4, (
        f"Phase D.1 must not add API routes; got {len(routes)}"
    )
    for r in routes:
        methods = getattr(r, "methods", set())
        assert forbidden.isdisjoint(methods), (
            f"Forbidden non-GET method on {r.path}: {methods}"
        )


def test_no_manual_endpoint_registered_after_phase_d1():
    from apps.api.src.api.research import router as research_router

    for r in research_router.routes:
        path = getattr(r, "path", "")
        assert "manual" not in path
        assert "trigger" not in path


# ---------------------------------------------------------------------------
# Boundary — no worker / scheduler additions
# ---------------------------------------------------------------------------


def test_no_research_worker_module_in_phase_d1():
    jobs_dir = Path("apps/worker/src/jobs")
    if not jobs_dir.is_dir():
        return
    research_files = sorted(p.name for p in jobs_dir.glob("research_*.py"))
    assert research_files == [], (
        f"Phase D.1 forbids research worker files; found: {research_files}"
    )


def test_no_research_scheduler_entry_in_phase_d1():
    p = Path("apps/worker/src/scheduler/tick_loop.py")
    if not p.exists():
        return
    src = p.read_text(encoding="utf-8")
    for tok in ('"research_run', "'research_run",
                "research_orchestrator", "research_intelligence"):
        assert tok not in src, f"Forbidden scheduler reference {tok!r}"


def test_no_research_registry_entry_in_phase_d1():
    p = Path("apps/worker/src/jobs/registry.py")
    if not p.exists():
        return
    src = p.read_text(encoding="utf-8")
    for tok in ('"research_run', "'research_run"):
        assert tok not in src, f"Forbidden registry key {tok!r}"


# ---------------------------------------------------------------------------
# Boundary — no LLM SDK / LangGraph / LangChain imports anywhere new
# ---------------------------------------------------------------------------


PHASE_D1_SOURCE_FILES = (
    "apps/api/src/research/provider_base.py",
    "apps/api/src/research/providers/__init__.py",
    "apps/api/src/research/providers/mock_provider.py",
    "apps/api/src/research/prompts.py",
    "apps/api/src/research/manual_run.py",
)


@pytest.mark.parametrize("rel", PHASE_D1_SOURCE_FILES)
def test_phase_d1_source_no_llm_sdk_imports(rel):
    src = Path(rel).read_text(encoding="utf-8")
    forbidden = (
        "import anthropic", "from anthropic",
        "import openai", "from openai",
        "from google.generativeai",
        "import langchain", "from langchain",
        "import langgraph", "from langgraph",
        "import vercel_ai", "from vercel_ai",
        "import llama_index", "from llama_index",
    )
    for tok in forbidden:
        assert tok not in src, f"Forbidden import {tok!r} in {rel}"


@pytest.mark.parametrize("rel", PHASE_D1_SOURCE_FILES)
def test_phase_d1_source_no_execution_or_ml_imports(rel):
    src = Path(rel).read_text(encoding="utf-8")
    import_lines = [
        line for line in src.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    forbidden = (
        "feature_engine", "recommendation_engine",
        "shadow_scorer", "drift_monitor",
        "auto_trader", "paper_execution",
        "submit_trade", "auto_trade_portfolio",
    )
    for tok in forbidden:
        assert tok not in joined, (
            f"Forbidden import {tok!r} in {rel} import lines: {joined!r}"
        )


@pytest.mark.parametrize("rel", PHASE_D1_SOURCE_FILES)
def test_phase_d1_source_no_filesystem_egress(rel):
    src = Path(rel).read_text(encoding="utf-8")
    for tok in (
        "~/.", "os.path.expanduser", "Path.home(",
        ".tradingagents", ".vibe-trading", ".openalice",
    ):
        assert tok not in src, (
            f"Forbidden filesystem token {tok!r} in {rel}"
        )


# ---------------------------------------------------------------------------
# Boundary — feature flags still default OFF
# ---------------------------------------------------------------------------


def test_research_ro_enabled_still_default_false():
    import os

    saved = os.environ.pop("RESEARCH_RO_ENABLED", None)
    try:
        from apps.api.src.config import Settings
        s = Settings()
        assert s.RESEARCH_RO_ENABLED is False
    finally:
        if saved is not None:
            os.environ["RESEARCH_RO_ENABLED"] = saved


# ---------------------------------------------------------------------------
# Boundary — langgraph / langchain still banned in pyproject
# ---------------------------------------------------------------------------


def test_langgraph_still_banned_after_phase_d1():
    src = Path("pyproject.toml").read_text(encoding="utf-8")
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


def test_langchain_still_banned_after_phase_d1():
    src = Path("pyproject.toml").read_text(encoding="utf-8")
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
