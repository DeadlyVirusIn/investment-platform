"""Operator script — evaluate options strategy auto-promotion.

Read-only by default (`--dry-run`). Apply mode is gated behind the
`OPTIONS_STRATEGY_PROMOTION_ENABLED=true` env flag. Even in apply
mode this script writes nothing today — it only emits a structured
artifact. The paper-exec runner is responsible for *consuming* the
artifact, and only when both env flags are set.

Hard guards:
  * Default off — env flag must be `true` for `--apply`.
  * `OPTIONS_DYNAMIC_SIZING_ENABLED=true` is required for sizing
    artifacts to be marked `enforced=True`. Otherwise sizing is
    advisory only.
  * Per-strategy size hard cap (2%) baked into the promotion module.
  * Per-underlying / total / daily caps echoed in the artifact for
    the runner to enforce.

Usage:
  python -m scripts.run_options_promotion_eval --dry-run
  python -m scripts.run_options_promotion_eval --dry-run --unit underlying_strategy
  python -m scripts.run_options_promotion_eval --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger


PROMOTION_ENV = "OPTIONS_STRATEGY_PROMOTION_ENABLED"
SIZING_ENV = "OPTIONS_DYNAMIC_SIZING_ENABLED"
ARTIFACT_DIR = Path("artifacts/options_promotion")
ARTIFACT_NAME_TEMPLATE = "promotion_eval_{horizon}_{unit}.json"


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_options_promotion_eval",
        description=(
            "Evaluate options strategy auto-promotion. Default dry-run."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true", default=True,
        help="No-op default. Print plan, write artifact under "
             "artifacts/options_promotion/.",
    )
    p.add_argument(
        "--apply", action="store_true",
        help=f"Write artifact + mark as enforceable. Requires "
             f"{PROMOTION_ENV}=true.",
    )
    p.add_argument("--horizon", default="5D")
    p.add_argument("--unit", default="strategy_name")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)

    promotion_enabled = (
        os.environ.get(PROMOTION_ENV, "").strip().lower() == "true"
    )
    sizing_enabled = (
        os.environ.get(SIZING_ENV, "").strip().lower() == "true"
    )

    if args.apply and not promotion_enabled:
        sys.stderr.write(
            f"REFUSED: --apply requires {PROMOTION_ENV}=true. "
            f"Default is OFF; set explicitly to enforce.\n"
        )
        return 2

    from apps.api.src.db import SessionLocal
    from apps.api.src.domain.options_quality.promotion import (
        VALID_HORIZONS, VALID_UNITS,
        PromotionThresholds, SizingConfig,
        evaluate_promotions, candidate_to_dict,
    )

    if args.horizon not in VALID_HORIZONS:
        sys.stderr.write(
            f"REFUSED: --horizon must be one of {VALID_HORIZONS}\n"
        )
        return 2
    if args.unit not in VALID_UNITS:
        sys.stderr.write(
            f"REFUSED: --unit must be one of {VALID_UNITS}\n"
        )
        return 2

    logger.info(
        "[promotion-eval] horizon={} unit={} mode={} "
        "{}={} {}={}",
        args.horizon, args.unit,
        "apply" if args.apply else "dry-run",
        PROMOTION_ENV, promotion_enabled,
        SIZING_ENV, sizing_enabled,
    )

    with SessionLocal() as session:
        cands = evaluate_promotions(
            session, horizon=args.horizon, unit=args.unit,
            thresholds=PromotionThresholds(), sizing=SizingConfig(),
        )
    items = [candidate_to_dict(c) for c in cands]

    eligible = [c for c in items if c["eligible"]]
    blocked = [c for c in items if not c["eligible"]]

    logger.info(
        "[promotion-eval] candidates={} eligible={} blocked={}",
        len(items), len(eligible), len(blocked),
    )
    for c in eligible:
        logger.info(
            "[promotion-eval.eligible] tier={} key={} "
            "hit_rate={:.3f} avg_fr={:.4f} samples={} "
            "proposed_size_pct={:.4f}",
            c["tier"], c["promotion_key"], c["hit_rate"],
            c["avg_forward_return_pct"], c["sample_count"],
            c["proposed_size_pct"],
        )
    for c in blocked[:25]:
        logger.info(
            "[promotion-eval.blocked] key={} reasons={}",
            c["promotion_key"], c["blocking_reasons"],
        )

    artifact = {
        "schema_version": 1,
        "horizon": args.horizon,
        "unit": args.unit,
        "promotion_enabled": promotion_enabled,
        "sizing_enabled": sizing_enabled,
        "enforced": bool(args.apply and promotion_enabled),
        "size_enforceable": bool(
            args.apply and promotion_enabled and sizing_enabled
        ),
        "candidates": items,
        "execution_caps": {
            "hard_max_per_strategy_pct": 0.02,
            "hard_max_per_underlying_pct": 0.02,
            "hard_max_total_options_exposure_pct": 0.05,
            "hard_max_daily_new_pct": 0.03,
        },
        "notice": (
            "Promotion artifact. Hard execution gates (liquidity, "
            "next-bar, quote freshness, paper-only, no live exec) "
            "are enforced by the runner regardless of this artifact."
        ),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / ARTIFACT_NAME_TEMPLATE.format(
        horizon=args.horizon, unit=args.unit,
    )
    out_path.write_text(json.dumps(artifact, indent=2, default=str))
    logger.info("[promotion-eval] wrote artifact: {}", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
