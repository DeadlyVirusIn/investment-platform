"""Phase 11W (Phase F.1) — static grep guards for premium UX."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_WEB_RESEARCH = Path("apps/web/src/components/research")
_WEB_LIB = Path("apps/web/src/lib/research")


def _read_dir(d: Path, glob: str = "**/*") -> str:
    if not d.exists():
        return ""
    out: list[str] = []
    for p in d.rglob(glob):
        if p.is_file() and p.suffix in (".ts", ".tsx"):
            try:
                out.append(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
    return "\n".join(out)


_FORBIDDEN_VISIBLE_COPY = (
    # Trading-action wording in user-visible copy.
    "Buy ", "Sell ", "Hold ", "Trade now",
    "Best trade", "High conviction", "Target price",
    "Stop loss", "Take profit", "Expected upside",
    "Outperform", "Underperform", "Recommendation",
    "winning signal", "high-conviction picks",
    "what to buy",
)


def test_locked_copy_has_no_signal_language():
    """Inspect tier helper + locked-state component + intelligence
    tab + timeline + pulse + job-health for forbidden visible copy
    in non-comment lines."""
    files = (
        "apps/web/src/lib/research/tier.ts",
        "apps/web/src/components/research/ResearchLockedPreview.tsx",
        "apps/web/src/components/research/ResearchIntelligenceTab.tsx",
        "apps/web/src/components/research/ResearchTimeline.tsx",
        "apps/web/src/components/research/ResearchPulseCard.tsx",
        "apps/web/src/components/research/ResearchJobHealthCard.tsx",
    )
    for rel in files:
        p = Path(rel)
        if not p.exists():
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            stripped = ln.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue
            for bad in _FORBIDDEN_VISIBLE_COPY:
                assert bad.lower() not in stripped.lower(), (
                    f"{rel} non-comment line contains forbidden copy "
                    f"{bad!r}: {stripped[:100]}"
                )


def test_no_post_in_research_components_phase_f1():
    blob = _read_dir(_WEB_RESEARCH) + _read_dir(_WEB_LIB)
    assert "method: 'POST'" not in blob
    assert 'method: "POST"' not in blob
    # tierFetch helper hard-codes GET only.
    tier_src = Path("apps/web/src/lib/research/tier.ts").read_text(encoding="utf-8")
    assert "method: 'GET'" in tier_src or "method: \"GET\"" in tier_src


def test_no_run_button_in_research_components():
    blob = _read_dir(_WEB_RESEARCH)
    # Naive check: no <button> in research components. Action
    # surfaces are forbidden.
    assert "<button" not in blob, (
        "research components contain a <button> element — Phase F.1 "
        "is read-only"
    )


def test_no_trading_imports_phase_f1():
    blob = _read_dir(_WEB_RESEARCH) + _read_dir(_WEB_LIB)
    forbidden = (
        "domain/features",
        "domain/recommendations",
        "domain/stock_engine",
        "domain/execution",
        "options/paper",
        "RecommendationCard",
        "PaperTradeButton",
        "BuyButton", "SellButton", "ActionDialog",
    )
    for tok in forbidden:
        assert tok not in blob, (
            f"research UI tree references trading symbol {tok!r}"
        )


def test_no_scheduler_or_worker_changes_phase_f1():
    worker = Path("apps/worker/src")
    if not worker.exists():
        pytest.skip("worker dir absent")
    blob = ""
    for p in worker.rglob("*.py"):
        blob += p.read_text(encoding="utf-8", errors="ignore")
    for tok in (
        "premium_tier", "ResearchLockedPreview", "ResearchTimeline",
        "tierFetch", "buildSafeMarkdownExport",
    ):
        assert tok not in blob, f"worker references Phase F.1 symbol {tok!r}"


def test_premium_tier_module_has_no_execution_imports():
    src = Path("apps/api/src/research/premium_tier.py").read_text(encoding="utf-8")
    forbidden = (
        "apps.api.src.domain.features.feature_engine",
        "apps.api.src.domain.recommendations.recommendation_engine",
        "apps.api.src.data.evaluation",
        "apps.api.src.domain.stock_engine.decision_engine",
        "apps.api.src.options.paper",
        "apps.api.src.domain.execution",
        "langchain", "langgraph",
    )
    for bad in forbidden:
        assert bad not in src


def test_research_router_still_only_get():
    src = Path("apps/api/src/api/research.py").read_text(encoding="utf-8")
    posts = re.findall(r"@router\.(post|put|patch|delete)\b", src)
    assert posts == [], f"forbidden non-GET routes: {posts}"
