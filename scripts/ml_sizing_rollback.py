"""Rollback helper — disable ML sizing instantly.

Writes ENABLE_ML_SIZING=0 to .env (or appends if absent), then prints the
container restart command. Operators can also toggle at OS level:

    export ENABLE_ML_SIZING=0     # unix
    setx  ENABLE_ML_SIZING 0      # windows (persistent)

And restart worker + api.

Usage::

    python -m scripts.ml_sizing_rollback --off
    python -m scripts.ml_sizing_rollback --on
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

ENV_FILE = Path(".env")
KEY = "ENABLE_ML_SIZING"


def _set_env_var(value: str) -> None:
    lines: list[str] = []
    replaced = False
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if raw.strip().startswith(f"{KEY}="):
                lines.append(f"{KEY}={value}")
                replaced = True
            else:
                lines.append(raw)
    if not replaced:
        lines.append(f"{KEY}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("[rollback] {}={} written to {}", KEY, value, ENV_FILE)


def main() -> None:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--on", action="store_true", help="Enable ML sizing (live).")
    grp.add_argument("--off", action="store_true", help="Disable ML sizing (rollback).")
    args = parser.parse_args()

    if args.on:
        _set_env_var("1")
        logger.warning(
            "ML sizing ENABLED. Restart api + worker. "
            "Verify with: grep ENABLE_ML_SIZING .env"
        )
    else:
        _set_env_var("0")
        logger.warning(
            "ML sizing DISABLED. Production reverted to deterministic path. "
            "Restart api + worker to apply."
        )


if __name__ == "__main__":
    main()
