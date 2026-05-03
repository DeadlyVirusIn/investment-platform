"""ML CLI entrypoint.

Usage::

    python -m apps.ml.cli train
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from apps.ml.training import EdgeGateBlocked, train_and_evaluate


def _cmd_train(_args: argparse.Namespace) -> int:
    try:
        result = train_and_evaluate()
    except EdgeGateBlocked as e:
        logger.error("[ml.cli] {}", e)
        return 2
    if not result.shadow_ready:
        logger.error(
            "[ml.cli] NOT shadow-ready: {}", result.shadow_ready_reason,
        )
        return 1
    logger.info("[ml.cli] shadow-ready ✓")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="apps.ml.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("train", help="Train LightGBM meta-labeler and evaluate.")
    args = parser.parse_args()

    if args.cmd == "train":
        sys.exit(_cmd_train(args))
    parser.error(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
