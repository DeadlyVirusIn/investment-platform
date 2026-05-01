"""Phase 11W (Phase B) — runtime dependency lint.

LangGraph and LangChain are FORBIDDEN as runtime dependencies of this
project. Conceptual DAG patterns may be re-implemented from scratch.
This test fails the build if either package appears as a non-dev
dependency in pyproject.toml.
"""

from __future__ import annotations

import re
from pathlib import Path


def _read_pyproject() -> str:
    return Path("pyproject.toml").read_text(encoding="utf-8")


def test_langgraph_not_in_runtime_dependencies():
    src = _read_pyproject()
    # Match `langgraph` only at line start in dependency lists,
    # ignoring comments and dev sections.
    in_optional = False
    in_dev = False
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("[project.optional-dependencies"):
            in_optional = True
            continue
        if stripped.startswith("[tool.") or stripped.startswith("[build"):
            in_optional = False
            in_dev = "dev" in stripped.lower()
            continue
        if in_optional or in_dev:
            continue
        if re.match(r"^\s*['\"]?langgraph['\"]?[\s>=<,]", line):
            raise AssertionError(
                f"Forbidden runtime dep `langgraph` in pyproject: {line!r}"
            )


def test_langchain_not_in_runtime_dependencies():
    src = _read_pyproject()
    in_optional = False
    in_dev = False
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("[project.optional-dependencies"):
            in_optional = True
            continue
        if stripped.startswith("[tool.") or stripped.startswith("[build"):
            in_optional = False
            in_dev = "dev" in stripped.lower()
            continue
        if in_optional or in_dev:
            continue
        if re.match(r"^\s*['\"]?langchain[a-z\-]*['\"]?[\s>=<,]", line):
            raise AssertionError(
                f"Forbidden runtime dep langchain* in pyproject: {line!r}"
            )


def test_research_module_does_not_import_langgraph_or_langchain():
    """Direct AST-level check on the research API source."""
    src = Path("apps/api/src/api/research.py").read_text(encoding="utf-8")
    for tok in ("langgraph", "langchain", "from anthropic", "from openai"):
        assert tok not in src, (
            f"Forbidden import {tok!r} in apps/api/src/api/research.py"
        )
