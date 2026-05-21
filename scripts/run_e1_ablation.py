"""E1 — Week-1 risk-feature ablation CLI.

Usage::

    python -m scripts.run_e1_ablation

Loads HistoricalLabel rows via apps.ml.dataset, runs E1, writes:
  - artifacts/e1_ablation_result.json
  - artifacts/e1_ablation_memo.md

Prints memo to stdout, exits 0 if VERDICT=PASS, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION
from apps.ml.dataset import load_dataset
from apps.ml.e1_ablation import (
    memo_path as memo_path_fn,
    result_path as result_path_fn,
    run_e1_ablation,
    write_json,
    write_memo,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine-version", type=str, default=MODEL_VERSION,
        help="engine_version filter for HistoricalLabel (default: current)",
    )
    parser.add_argument(
        "--suffix", type=str, default="",
        help="artifact path suffix (e.g. '_asym'); preserves multiple runs",
    )
    args = parser.parse_args()

    logger.info(
        "[e1.cli] loading dataset engine_version={} …", args.engine_version,
    )
    bundle = load_dataset(engine_version=args.engine_version)
    logger.info("[e1.cli] running E1 ablation…")
    result = run_e1_ablation(bundle)
    json_path = write_json(result, result_path_fn(args.suffix))
    memo_path = write_memo(result, memo_path_fn(args.suffix))

    # Print memo
    print()
    print(memo_path.read_text())
    print()
    print(f"[e1] result JSON → {json_path}")
    print(f"[e1] memo       → {memo_path}")
    return 0 if result.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
