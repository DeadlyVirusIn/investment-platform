"""Phase 11W (Phase B) — confirms no worker registry entry, no
scheduler entry, and no LLM client wiring exists for the research
layer in Phase B."""

from __future__ import annotations

from pathlib import Path


def test_no_research_worker_registry_entry():
    """Worker registry must not reference the research namespace."""
    src = Path(
        "apps/worker/src/jobs/registry.py"
    ).read_text(encoding="utf-8")
    # Allow the literal word "research" in comments only if it's not a
    # registry-key string. Easier check: no quoted "research_*" key.
    forbidden_patterns = (
        '"research_run',
        "'research_run",
        '"research_intelligence',
        "'research_intelligence",
        '"research_ro',
        "'research_ro",
    )
    for pat in forbidden_patterns:
        assert pat not in src, (
            f"Forbidden research worker key {pat!r} in registry.py"
        )


def test_no_research_scheduler_tick_entry():
    """Scheduler tick loop must not reference the research namespace."""
    src = Path(
        "apps/worker/src/scheduler/tick_loop.py"
    ).read_text(encoding="utf-8")
    forbidden_patterns = (
        '"research_run',
        "'research_run",
        "research_intelligence",
        "research_orchestrator",
    )
    for pat in forbidden_patterns:
        assert pat not in src, (
            f"Forbidden research scheduler ref {pat!r} in tick_loop.py"
        )


def test_no_research_worker_module_exists_in_phase_b():
    """Phase B forbids any apps/worker/src/jobs/research_*.py file."""
    jobs_dir = Path("apps/worker/src/jobs")
    if not jobs_dir.is_dir():
        return
    research_files = sorted(p.name for p in jobs_dir.glob("research_*.py"))
    assert research_files == [], (
        f"Phase B forbids research worker files; found: {research_files}"
    )


def test_no_llm_client_wiring_in_research_module():
    """The research API stub must not import an LLM client SDK."""
    src = Path(
        "apps/api/src/api/research.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "from anthropic", "import anthropic",
        "from openai", "import openai",
        "from google.generativeai",
        "langgraph", "langchain",
        "OpenAI(", "Anthropic(",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"Forbidden LLM client wiring {tok!r} in research.py"
        )
