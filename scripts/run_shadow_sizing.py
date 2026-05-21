"""End-to-end shadow sizing demo for a single as_of date.

Pipeline (SHADOW ONLY — no writes to live tables):
  1. Resolve candidates via production decision_engine.generate_candidates
  2. Load factor snapshots for accepted Buys on as_of
  3. Score each candidate via ShadowScorer (LightGBM cached model)
  4. Run portfolio_sizer with ml_proba populated; receive BOTH production
     weights (unchanged) AND shadow_weights (ML-sized)
  5. Emit per-trade + per-day JSON log to artifacts/shadow_sizing/<as_of>.json

Usage::

    python -m scripts.run_shadow_sizing --as-of 2026-04-17
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    Asset,
    FactorSnapshot,
    RegimeSnapshot,
)
from apps.api.src.domain.ml.shadow_scorer import predict_proba_for_candidates
from apps.api.src.domain.ml.sizing_log_writer import persist_sizing_decisions
from apps.api.src.domain.stock_engine.decision_engine import (
    DEFAULT_UNIVERSE,
    generate_candidates,
)
from apps.api.src.domain.stock_engine.portfolio.portfolio_sizer import (
    SizingInput,
    size_positions,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

ART_DIR = Path("artifacts/shadow_sizing")


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _atr_median(rows: list[FactorSnapshot]) -> Decimal | None:
    vals = [r.atr_percent_14 for r in rows if r.atr_percent_14 is not None]
    if not vals:
        return None
    vals = sorted(vals)
    n = len(vals)
    mid = n // 2
    if n % 2 == 0:
        return (Decimal(vals[mid - 1]) + Decimal(vals[mid])) / Decimal("2")
    return Decimal(vals[mid])


def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow sizing demo for one day.")
    parser.add_argument("--as-of", required=True, type=_parse_date)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    args = parser.parse_args()
    as_of = args.as_of

    ART_DIR.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        regime = session.get(RegimeSnapshot, as_of)
        if regime is None:
            raise SystemExit(f"no regime_snapshot for {as_of}")

        # 1. Production decision engine (unchanged)
        candidates = generate_candidates(session, as_of, universe_name=args.universe)
        accepted_buys = [
            c for c in candidates
            if c.status == "accepted" and c.action == "Buy"
        ]
        logger.info(
            "[shadow] as_of={} total_candidates={} accepted_buys={}",
            as_of, len(candidates), len(accepted_buys),
        )
        if not accepted_buys:
            raise SystemExit("no accepted Buys on as_of")

        # 2. Asset + factor lookup for the accepted set
        asset_map = {
            a.id: a for a in session.execute(
                select(Asset).where(Asset.id.in_([c.asset_id for c in accepted_buys]))
            ).scalars().all()
        }
        factor_rows = list(session.execute(
            select(FactorSnapshot).where(
                FactorSnapshot.as_of_date == as_of,
                FactorSnapshot.asset_id.in_([c.asset_id for c in accepted_buys]),
            )
        ).scalars().all())
        f_by_id = {f.asset_id: f for f in factor_rows}

        # 3. ML scoring
        atr_med = _atr_median(factor_rows)
        proba_map = predict_proba_for_candidates(factor_rows, regime, atr_med)
        logger.info(
            "[shadow] scored {} candidates proba_range=[{:.3f}..{:.3f}]",
            len(proba_map), min(proba_map.values()), max(proba_map.values()),
        )

        # 4. Build SizingInput rows
        sizing_inputs = []
        for c in accepted_buys:
            asset = asset_map.get(c.asset_id)
            if asset is None:
                continue
            proba = proba_map.get(c.asset_id)
            sizing_inputs.append(SizingInput(
                asset_id=c.asset_id,
                composite_score=c.composite_score,
                confidence=c.confidence,
                sector=asset.sector or "unknown",
                ml_proba=Decimal(str(proba)) if proba is not None else None,
                symbol=asset.symbol,
            ))

        result = size_positions(sizing_inputs)

        # 5. Per-day aggregates
        prod_sum    = sum(result.target_weights.values(), Decimal("0"))
        shadow_sum  = sum(result.shadow_weights.values(), Decimal("0"))
        avg_mult = (
            sum(Decimal(r.multiplier) for r in result.shadow_log)
            / Decimal(len(result.shadow_log))
            if result.shadow_log else Decimal("0")
        )
        avg_norm = (
            sum(Decimal(r.normalized_weight or "0") for r in result.shadow_log)
            / Decimal(len(result.shadow_log))
            if result.shadow_log else Decimal("0")
        )

        top5_shadow = sorted(
            result.shadow_log,
            key=lambda r: Decimal(r.normalized_weight or r.final_weight),
            reverse=True,
        )[:5]

        # Prepare log rows with as_of_date backfilled
        for row in result.shadow_log:
            row.as_of_date = str(as_of)

        output = {
            "as_of_date": str(as_of),
            "engine_version": MODEL_VERSION,
            "mode": "SHADOW",
            "production": {
                "target_weights_count": len(result.target_weights),
                "sum_weights": str(prod_sum),
                "sector_totals": {k: str(v) for k, v in result.sector_totals.items()},
                "dropped": [{"asset_id": a, "reason": r} for a, r in result.dropped],
            },
            "shadow": {
                "weights_count": len(result.shadow_weights),
                "baseline_sum_weights": str(prod_sum),
                "shadow_sum_pre_norm": str(result.shadow_sum_pre_norm),
                "shadow_sum_post_norm": str(result.shadow_sum_post_norm),
                "scale_factor_applied": str(result.shadow_scale_factor),
                "sector_totals": {k: str(v) for k, v in result.shadow_sector_totals.items()},
                "avg_multiplier": str(avg_mult),
                "avg_normalized_weight": str(avg_norm),
                "top5_by_normalized_weight": [
                    {
                        "symbol": r.symbol,
                        "ml_proba": r.ml_proba,
                        "multiplier": r.multiplier,
                        "final_weight_pre_norm": r.final_weight,
                        "normalized_weight": r.normalized_weight,
                    }
                    for r in top5_shadow
                ],
            },
            "per_trade_log": [row.__dict__ for row in result.shadow_log],
        }

        out_path = ART_DIR / f"{as_of.isoformat()}.json"
        out_path.write_text(json.dumps(output, indent=2))
        logger.info("[shadow] wrote log → {}", out_path)

        # Persistent JSONL (production path — append-only)
        persist_sizing_decisions(result, as_of)

        # Stdout summary
        logger.info("=" * 84)
        logger.info("SHADOW SIZING REPORT as_of={}", as_of)
        logger.info("=" * 84)
        logger.info(
            "production: positions={} sum_weights={}",
            len(result.target_weights), prod_sum,
        )
        logger.info(
            "shadow:     positions={} pre_norm={} post_norm={} scale={} avg_mult={}",
            len(result.shadow_weights),
            result.shadow_sum_pre_norm,
            result.shadow_sum_post_norm,
            result.shadow_scale_factor,
            avg_mult,
        )
        logger.info("top 5 shadow-weighted (normalized):")
        for r in top5_shadow:
            logger.info(
                "  {:<6s}  proba={}  mult={}  pre_norm={}  norm={}",
                r.symbol or "?",
                (r.ml_proba or "—")[:6],
                r.multiplier[:5],
                r.final_weight[:8],
                (r.normalized_weight or "—")[:10],
            )
        logger.info("per-trade log rows: {}", len(result.shadow_log))


if __name__ == "__main__":
    main()
