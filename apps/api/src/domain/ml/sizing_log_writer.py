"""Persist daily sizing decisions (production + parallel shadow) to JSONL.

Call `persist_sizing_decisions(result, as_of)` after every size_positions()
invocation in live runs. Writes to artifacts/ml_sizing/<as_of>.jsonl so
records are append-only and timestamped.

Contains BOTH production and parallel-shadow weights per the feature-flag
contract in portfolio_sizer — whichever path is live, the other is
preserved for monitoring / A-B comparison.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from loguru import logger

from apps.api.src.domain.stock_engine.portfolio.portfolio_sizer import (
    SizingResult,
)

ART_DIR = Path("artifacts/ml_sizing")


def _dec_str(v: Decimal | str | None) -> str | None:
    if v is None:
        return None
    return str(v)


def persist_sizing_decisions(
    result: SizingResult, as_of: dt.date,
) -> Path:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    path = ART_DIR / f"{as_of.isoformat()}.jsonl"

    production_sum = sum(result.target_weights.values(), Decimal("0"))
    shadow_sum = sum(result.shadow_weights.values(), Decimal("0"))

    header = {
        "kind": "daily_header",
        "as_of_date": as_of.isoformat(),
        "sizing_mode": result.sizing_mode,
        "production_positions": len(result.target_weights),
        "production_sum_weights": str(production_sum),
        "shadow_positions": len(result.shadow_weights),
        "shadow_sum_weights": str(shadow_sum),
        "shadow_sum_pre_norm": str(result.shadow_sum_pre_norm),
        "shadow_sum_post_norm": str(result.shadow_sum_post_norm),
        "scale_factor": str(result.shadow_scale_factor),
        "production_sector_totals": {k: str(v) for k, v in result.sector_totals.items()},
        "shadow_sector_totals": {k: str(v) for k, v in result.shadow_sector_totals.items()},
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for row in result.shadow_log:
            rec = {
                "kind": "trade",
                "as_of_date": row.as_of_date or as_of.isoformat(),
                "symbol": row.symbol,
                "asset_id": row.asset_id,
                "base_weight": row.base_weight,
                "ml_proba": row.ml_proba,
                "multiplier": row.multiplier,
                "adjusted_weight": row.adjusted_weight,
                "final_weight_pre_norm": row.final_weight,
                "normalized_weight": row.normalized_weight,
                "was_clipped": row.was_clipped,
                "cap_reason": row.cap_reason,
                "production_weight": str(
                    result.target_weights.get(row.asset_id, Decimal("0"))
                ),
            }
            f.write(json.dumps(rec) + "\n")

    logger.info("[ml.sizing_log] persisted {} trades + header → {}",
                len(result.shadow_log), path)
    return path
