"""Phase 11W (Phase F) — static guards for the UI integration.

Pure-unit grep tests. No DB. No browser. Verifies:
  * No research UI component imports trading / scoring / paper / ML
    / options modules.
  * No scheduler / worker registry changes added by Phase F.
  * `apps/api/src/api/research.py` declares zero
    POST/PUT/PATCH/DELETE handlers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


WEB_RESEARCH_DIR = Path("apps/web/src/components/research")
WEB_LIB_RESEARCH = Path("apps/web/src/lib/research")


_FORBIDDEN_FRONTEND_IMPORTS = (
    # Trading / scoring / candidate / paper paths.
    "domain/features",
    "domain/recommendations",
    "domain/stock_engine",
    "domain/execution",
    "options/paper",
    "lib/trading",
    # Action surfaces.
    "RecommendationCard",
    "PaperTradeButton",
    "BuyButton",
    "SellButton",
    "ActionDialog",
)


def _read_all(d: Path, glob: str = "**/*.ts*") -> str:
    if not d.exists():
        return ""
    out: list[str] = []
    for p in d.rglob(glob):
        if p.is_file():
            try:
                out.append(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
    return "\n".join(out)


def test_no_research_ui_imports_trading_modules():
    src = _read_all(WEB_RESEARCH_DIR) + _read_all(WEB_LIB_RESEARCH)
    for bad in _FORBIDDEN_FRONTEND_IMPORTS:
        assert bad not in src, (
            f"research UI tree references {bad!r}: expected zero hits"
        )


def test_no_scheduler_or_worker_changes_phase_f():
    """Phase F is a UI-and-read-only-API phase. Worker dir must not
    reference any Phase F module."""
    worker = Path("apps/worker/src")
    if not worker.exists():
        pytest.skip("worker dir absent")
    blob = ""
    for p in worker.rglob("*.py"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    for bad in (
        "research.py",
        "ResearchByline",
        "ResearchPulseCard",
        "FreshnessBadge",
        "research/runs",
        "research_manual_run_audit",
    ):
        assert bad not in blob, (
            f"worker dir references Phase F symbol {bad!r}"
        )


def test_research_router_exposes_only_get_handlers():
    src = Path("apps/api/src/api/research.py").read_text(encoding="utf-8")
    posts = re.findall(r"@router\.(post|put|patch|delete)\b", src)
    assert posts == [], f"forbidden non-GET handlers: {posts}"


def test_phase_f_api_response_payloads_have_no_raw_body_field_for_runs():
    """Inspect `_row_to_run_payload`: must not include any body field
    at the run level. Bodies live only in agent_output payloads, and
    there they're filtered through `_safe_body_or_blank`."""
    src = Path("apps/api/src/api/research.py").read_text(encoding="utf-8")
    # Locate the run-payload mapper.
    m = re.search(
        r"def _row_to_run_payload\(.*?\)\s*->.*?\{(.+?)\}\s*$",
        src, flags=re.DOTALL | re.MULTILINE,
    )
    assert m is not None, "_row_to_run_payload not found"
    body = m.group(1)
    for forbidden in (
        '"body"', '"raw_body"', '"raw_response"',
        '"structured_output"', '"prompt"',
    ):
        assert forbidden not in body, (
            f"_row_to_run_payload exposes {forbidden}"
        )


def test_research_byline_component_has_no_body_field():
    """ResearchByline renders provenance only. Verify by source
    inspection — no body / raw_body interpolation."""
    p = Path("apps/web/src/components/research/ResearchByline.tsx")
    src = p.read_text(encoding="utf-8")
    for tok in ("body", "raw_body", "raw_response", "buy", "sell", "recommend"):
        # Allow comments mentioning these tokens (e.g., "NEVER renders the
        # artifact body."), but not actual code interpolation.
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            assert tok not in stripped.lower(), (
                f"ResearchByline contains {tok!r} in non-comment line: "
                f"{stripped!r}"
            )
