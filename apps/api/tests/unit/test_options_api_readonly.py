"""Phase 11F unit tests — options read-only API contract.

Two tiers:
  (1) Static source scan — `routes_readonly.py` + `service_readonly.py`
      contain ZERO mutating decorators (POST/PUT/PATCH/DELETE) and
      ZERO mutating SQL or session.add/commit/delete calls.
  (2) Boundary grep — neither file imports any V2 / equity / engine_b /
      shadow_strategy / ML / paper engine internal module.

Runtime API checks live in the integration suite (need DB).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _src_paths() -> list[Path]:
    here = Path(__file__).resolve()
    options_dir = here.parent.parent.parent / "src" / "options"
    return [
        options_dir / "routes_readonly.py",
        options_dir / "service_readonly.py",
    ]


# ---------------------------------------------------------------------------
# Mutation surface — must not exist
# ---------------------------------------------------------------------------

_MUTATING_DECORATORS = (
    r"@router\.post\b",
    r"@router\.put\b",
    r"@router\.patch\b",
    r"@router\.delete\b",
    r"@app\.post\b",  r"@app\.put\b",
    r"@app\.patch\b", r"@app\.delete\b",
)


def test_no_mutation_decorators_in_options_api():
    for p in _src_paths():
        src = p.read_text(encoding="utf-8")
        for pat in _MUTATING_DECORATORS:
            assert not re.search(pat, src), (
                f"forbidden mutating decorator {pat!r} in {p.name}"
            )


_MUTATING_SQL = (
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bDELETE\s+FROM\b",
    r"session\.add\b",
    r"session\.commit\b",
    r"session\.delete\b",
    r"session\.flush\b",
    r"session\.merge\b",
)


def test_no_mutating_sql_in_options_readonly():
    for p in _src_paths():
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            for pat in _MUTATING_SQL:
                assert not re.search(pat, line), (
                    f"forbidden mutating SQL/session call {pat!r} "
                    f"in {p.name}: {line.strip()}"
                )


# ---------------------------------------------------------------------------
# Boundary grep — no V2 / equity / ML / paper engine internals
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORT_PATTERNS = [
    r"\bv2_promotion(?!_snapshot)\b",
    r"\bv2_promotion_snapshot\b",
    r"\bv2_oos_monitoring\b",
    r"\bv2_stat_validation\b",
    r"\bb2_v2_comparison\b",
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bpaper_trade_log\b",
    r"\bdecision_log\b",
    r"\bpaper_shadow_log\b",
    # The read-only API must NOT import the paper engine itself
    # (only the read-only service + flag tokens through `expiration`).
    r"options\.paper\.engine",
    r"options\.paper\.fills",
    r"options\.paper\.pnl",
    r"options\.paper\.strategies",
    # ML signals must not appear
    r"\bml_hybrid\b", r"\bml_advice\b", r"\bml_research\b", r"\bml_replay\b",
]


def test_no_forbidden_imports_in_options_api():
    for p in _src_paths():
        src = p.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        for pat in _FORBIDDEN_IMPORT_PATTERNS:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"forbidden import pattern {pat!r} in {p.name}"
            )


# ---------------------------------------------------------------------------
# Recommendation/execution language scan
# ---------------------------------------------------------------------------

_FORBIDDEN_LANGUAGE = (
    r"\bExecute Trade\b", r"\bPlace Order\b",
    r"\bRecommended Trade\b", r"\bBest Trade\b",
    r"\bML Signal\b", r"\bConfidence Score\b",
    r"\bAuto-?trade\b", r"\bPromotion\b",
    r"\bV2 comparison\b",
)


def test_no_recommendation_or_execution_language_in_api():
    for p in _src_paths():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_LANGUAGE:
            assert not re.search(pat, src, re.IGNORECASE), (
                f"forbidden user-facing wording {pat!r} in {p.name}"
            )


# ---------------------------------------------------------------------------
# Router introspection — every registered route is a GET
# ---------------------------------------------------------------------------

def test_router_introspection_only_get_routes():
    from apps.api.src.options.routes_readonly import router
    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        # Allow HEAD because FastAPI auto-adds it for GET routes
        non_get = methods - {"GET", "HEAD"}
        assert not non_get, (
            f"non-GET method {non_get!r} on route {route.path!r}"
        )


def test_options_module_imports_in_isolation():
    """Importing routes_readonly must NOT pull in V2/equity/ML modules."""
    import importlib
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.routes_readonly")
    importlib.import_module("apps.api.src.options.service_readonly")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
        "ml_hybrid", "ml_advice", "ml_research", "ml_replay",
        "options.paper.engine",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), (
            f"options read-only API indirectly pulled in {f}"
        )
