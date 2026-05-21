"""Phase 2 conditional pipeline CLI.

Gated on E1 VERDICT=PASS (or AMBIGUOUS_* with --force).

Usage::

    python -m scripts.run_phase2_pipeline
    python -m scripts.run_phase2_pipeline --force   # AMBIGUOUS_* too
    python -m scripts.run_phase2_pipeline --e1-result artifacts/e1_ablation_result.json

Writes:
  - artifacts/e2_pipeline_result.json
  - artifacts/e2_pipeline_memo.md

Exit 0 if gate passes and plan_status = PROCEED_TO_WEEK5_SHADOW.
Exit 1 if gate blocks or plan_status = ITERATE_*.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from apps.ml.dataset import load_dataset
from apps.ml.phase2_pipeline import (
    E1_RESULT_PATH,
    Phase2GateBlocked,
    load_e1_result,
    run_phase2_pipeline,
    write_json,
    write_memo,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e1-result", type=Path, default=E1_RESULT_PATH)
    parser.add_argument(
        "--force", action="store_true",
        help="proceed on E1 AMBIGUOUS_* verdicts (not PASS)",
    )
    args = parser.parse_args()

    try:
        e1_result = load_e1_result(args.e1_result)
    except Phase2GateBlocked as e:
        logger.error("[e2.cli] {}", e)
        return 1

    logger.info(
        "[e2.cli] E1 verdict={} — loading dataset…",
        e1_result.get("verdict"),
    )
    bundle = load_dataset()

    try:
        result = run_phase2_pipeline(bundle, e1_result, force=args.force)
    except Phase2GateBlocked as e:
        logger.error("[e2.cli] GATE BLOCKED: {}", e)
        return 1

    json_path = write_json(result)
    memo_path = write_memo(result)

    print()
    print(memo_path.read_text())
    print()
    print(f"[e2] result JSON → {json_path}")
    print(f"[e2] memo       → {memo_path}")

    return 0 if result.weeks_2_4_plan_status == "PROCEED_TO_WEEK5_SHADOW" else 1


if __name__ == "__main__":
    sys.exit(main())
