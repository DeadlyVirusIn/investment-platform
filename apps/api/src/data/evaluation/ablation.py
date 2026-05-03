"""Feature ablation — standardized evaluation result schema.

Each candidate/diagnostic feature test produces an AblationResult row.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

RESULTS_DIR = Path("artifacts/eval")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AblationResult:
    feature_name: str
    test_type: str             # "overlay_skip" | "overlay_size" | "additional_gate"
    test_date: dt.date
    baseline_oos_n: int
    candidate_oos_n: int
    baseline_oos_mean_pct: float
    candidate_oos_mean_pct: float
    oos_mean_delta_pct: float
    baseline_oos_t: float
    candidate_oos_t: float
    oos_t_delta: float
    baseline_oos_dd_pct: float
    candidate_oos_dd_pct: float
    dd_delta_pp: float
    trades_removed: int
    trades_removed_mean_pct: float
    verdict: str               # PASS | WEAK | FAIL
    notes: str = ""
    extras: dict = field(default_factory=dict)


def persist_ablation(r: AblationResult) -> None:
    out = RESULTS_DIR / "ablation_results.jsonl"
    with out.open("a") as f:
        f.write(json.dumps(asdict(r), default=str) + "\n")
