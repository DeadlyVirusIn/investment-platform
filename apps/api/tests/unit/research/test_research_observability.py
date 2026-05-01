"""Phase 11W (Phase D.3) — observability source-level + signature tests.

The DB-touching aggregation paths are covered by
test_research_observability_pg.py. This file enforces source-level
invariants and pure-fn signature guarantees that don't need a DB.
"""

from __future__ import annotations

import datetime as dt
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.api.src.research import observability as obs


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_observability_module_exports_three_functions():
    expected = {
        "get_provider_metrics",
        "get_provider_comparison",
        "get_recent_research_provider_runs",
    }
    actual = {
        name
        for name, member in vars(obs).items()
        if inspect.isfunction(member)
        and member.__module__ == "apps.api.src.research.observability"
    }
    # Each expected function exists; private helpers are allowed.
    assert expected.issubset(actual)


def test_get_provider_metrics_signature():
    sig = inspect.signature(obs.get_provider_metrics)
    params = list(sig.parameters)
    assert params == ["session", "start_date", "end_date"]


def test_get_provider_comparison_signature():
    sig = inspect.signature(obs.get_provider_comparison)
    params = list(sig.parameters)
    assert params == ["session", "symbol", "as_of"]


def test_get_recent_research_provider_runs_signature():
    sig = inspect.signature(obs.get_recent_research_provider_runs)
    params = list(sig.parameters)
    assert params == ["session", "limit"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_get_provider_metrics_rejects_non_date_start():
    with pytest.raises(ValueError):
        obs.get_provider_metrics(
            MagicMock(),
            start_date="2026-04-01",  # type: ignore[arg-type]
            end_date=dt.date(2026, 4, 30),
        )


def test_get_provider_metrics_rejects_non_date_end():
    with pytest.raises(ValueError):
        obs.get_provider_metrics(
            MagicMock(),
            start_date=dt.date(2026, 4, 1),
            end_date="2026-04-30",  # type: ignore[arg-type]
        )


def test_get_provider_metrics_rejects_inverted_range():
    with pytest.raises(ValueError):
        obs.get_provider_metrics(
            MagicMock(),
            start_date=dt.date(2026, 4, 30),
            end_date=dt.date(2026, 4, 1),
        )


def test_get_provider_comparison_rejects_empty_symbol():
    with pytest.raises(ValueError):
        obs.get_provider_comparison(
            MagicMock(),
            symbol="",
            as_of=dt.date(2026, 4, 30),
        )


def test_get_provider_comparison_rejects_non_date_as_of():
    with pytest.raises(ValueError):
        obs.get_provider_comparison(
            MagicMock(),
            symbol="AAPL",
            as_of="2026-04-30",  # type: ignore[arg-type]
        )


def test_get_recent_provider_runs_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        obs.get_recent_research_provider_runs(MagicMock(), limit=0)
    with pytest.raises(ValueError):
        obs.get_recent_research_provider_runs(MagicMock(), limit=-5)


def test_get_recent_provider_runs_rejects_non_int_limit():
    with pytest.raises(ValueError):
        obs.get_recent_research_provider_runs(
            MagicMock(),
            limit="50",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Source-level: read-only + no body text + no public table access
# ---------------------------------------------------------------------------


_SRC_PATH = Path("apps/api/src/research/observability.py")


def test_observability_source_has_no_db_mutation_helpers():
    src = _SRC_PATH.read_text(encoding="utf-8")
    for tok in (
        "session.add(", "session.commit(", "session.flush(",
        "session.delete(", "session.merge(",
        "INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE",
    ):
        assert tok not in src, (
            f"Forbidden DB mutation token {tok!r} in observability.py"
        )


def test_observability_source_does_not_select_public_tables():
    """Allowed sources: research_ro.research_run +
    research_ro.research_agent_output. Anything else is rejected."""
    src = _SRC_PATH.read_text(encoding="utf-8")
    # FROM/JOIN must always reference research_ro.*
    forbidden_table_refs = (
        "FROM public.", "JOIN public.",
        "FROM candidate_idea", "FROM paper_run_log",
        "FROM paper_decision_log", "FROM alpha_rule_snapshot",
        "FROM context_daily", "FROM paper_position",
        "FROM paper_trade",
    )
    for tok in forbidden_table_refs:
        assert tok not in src, (
            f"Forbidden public-table reference {tok!r} in observability.py"
        )


def test_observability_does_not_return_body_text():
    """The SELECT lists must NOT include ANY column literally named
    `body` (which holds raw artifact text). `body_hash` is fine
    (it's metadata, not content)."""
    src = _SRC_PATH.read_text(encoding="utf-8")
    # Find every SQL fragment between text(""" and """) and assert
    # body is never in the SELECT projection.
    import re
    sql_blocks = re.findall(r'text\(\s*"""([\s\S]*?)"""\s*[,)]', src)
    assert sql_blocks, "no SQL blocks parsed from observability.py"
    for block in sql_blocks:
        # body must not appear except as part of body_hash.
        # Strip "body_hash" then assert body absent.
        scrubbed = block.replace("body_hash", "")
        # Allow "body_hash" tokens; reject bare "body" identifier.
        assert re.search(r"\bbody\b", scrubbed) is None, (
            f"observability returns body text in SQL block: {block!r}"
        )


def test_observability_no_recommendation_tokens():
    src = _SRC_PATH.read_text(encoding="utf-8")
    import re
    forbidden = re.compile(
        r"\b(buy|sell|hold|recommend|signal|allocate|"
        r"position|leverage)\b",
        re.IGNORECASE,
    )
    # Strip docstrings.
    no_doc = re.sub(r'"""[\s\S]*?"""', "", src)
    m = forbidden.search(no_doc)
    assert m is None, (
        f"Forbidden recommendation token in observability.py: {m.group(0)!r}"
    )


def test_observability_no_execution_or_ml_imports():
    src = _SRC_PATH.read_text(encoding="utf-8")
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
            f"Forbidden import {tok!r} in observability.py"
        )


def test_observability_no_llm_sdk_imports():
    src = _SRC_PATH.read_text(encoding="utf-8")
    for tok in (
        "import anthropic", "from anthropic",
        "import openai", "from openai",
        "from google.generativeai", "import google.generativeai",
        "import langchain", "from langchain",
        "import langgraph", "from langgraph",
    ):
        assert tok not in src, f"Forbidden import {tok!r} in observability.py"
