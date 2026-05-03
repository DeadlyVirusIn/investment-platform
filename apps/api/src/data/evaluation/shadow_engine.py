"""Shadow engine — run candidate/diagnostic overlays in parallel without
touching strategy decisions.

Reads same feature snapshot. Computes what-if outcomes for candidate signals.
Writes results to artifacts/eval/shadow_*.jsonl (never mutates decision_log).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from apps.api.src.data.strategy.selector import SelectorOutput

SHADOW_DIR = Path("artifacts/eval")
SHADOW_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ShadowResult:
    as_of_date: dt.date
    candidate_feature: str
    baseline_engine: str
    candidate_engine: str
    diverged: bool
    baseline_reason: str
    candidate_reason: str
    notes: str


def shadow_evaluate(
    as_of_date: dt.date, baseline: SelectorOutput,
    candidate_result: SelectorOutput, candidate_feature: str,
    notes: str = "",
) -> ShadowResult:
    """Compare baseline production output with candidate-overlay output."""
    return ShadowResult(
        as_of_date=as_of_date,
        candidate_feature=candidate_feature,
        baseline_engine=baseline.engine,
        candidate_engine=candidate_result.engine,
        diverged=(baseline.engine != candidate_result.engine
                  or baseline.fire != candidate_result.fire),
        baseline_reason=baseline.reason,
        candidate_reason=candidate_result.reason,
        notes=notes,
    )


def persist_shadow(result: ShadowResult, candidate_feature: str) -> None:
    """Append to per-feature shadow log."""
    path = SHADOW_DIR / f"shadow_{candidate_feature}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(asdict(result), default=str) + "\n")
