"""Phase 11W (Phase E) — manual research run CLI (operator-only).

Single-shot runner. Reads inputs from CLI args, applies every
Phase E gate via `manual_run_safe.run_manual_safely`, prints
sanitized JSON metadata. Never prints the raw provider body.

Default behavior:
  * Refuses to run unless BOTH `RESEARCH_RO_ENABLED=true` AND
    `RESEARCH_MANUAL_RUN_ENABLED=true` are set in the process
    environment.
  * Refuses any provider not in `RESEARCH_ALLOWED_PROVIDERS`.
  * Refuses any symbol not in `RESEARCH_ALLOWED_SYMBOLS` when that
    allowlist is non-empty.

Exit codes:
  0   run completed (status may be 'succeeded' or 'token_violation'
      etc.; check the printed status field)
  2   precondition failure (flags off, validation, args)
  3   not allowed (provider / symbol / cost)
  4   quota exceeded (per-ticker daily cap)
  5   cost cap exceeded (per-day or per-run)
  9   unexpected error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Sequence

from loguru import logger

from apps.api.src.db import SessionLocal
from apps.api.src.research.manual_run_safe import (
    PhaseECostExceededError,
    PhaseEDisabledError,
    PhaseENotAllowedError,
    PhaseEQuotaExceededError,
    PhaseEValidationError,
    PhaseEError,
    run_manual_safely,
)


def _parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_research_manual",
        description=(
            "Manual research run (operator-only). Refuses to run "
            "unless RESEARCH_RO_ENABLED and RESEARCH_MANUAL_RUN_ENABLED "
            "are both true."
        ),
    )
    p.add_argument("--symbol", required=True)
    p.add_argument(
        "--as-of", required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument("--provider", default="mock")
    p.add_argument("--operator-id", required=True)
    p.add_argument("--candidate-idea-id", default=None)
    p.add_argument("--idempotency-key", default=None)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    try:
        with SessionLocal() as session:
            payload = run_manual_safely(
                session,
                symbol=args.symbol,
                as_of=args.as_of,
                provider_name=args.provider,
                operator_id=args.operator_id,
                candidate_idea_id=args.candidate_idea_id,
                idempotency_key=args.idempotency_key,
                triggered_by="manual",
                request_source="cli",
            )
    except PhaseEDisabledError as exc:
        sys.stderr.write(f"[disabled] {exc}\n")
        return 2
    except PhaseEValidationError as exc:
        sys.stderr.write(f"[validation] {exc}\n")
        return 2
    except PhaseENotAllowedError as exc:
        sys.stderr.write(f"[not_allowed] {exc}\n")
        return 3
    except PhaseEQuotaExceededError as exc:
        sys.stderr.write(f"[quota_exceeded] {exc}\n")
        return 4
    except PhaseECostExceededError as exc:
        sys.stderr.write(f"[cost_exceeded] {exc}\n")
        return 5
    except PhaseEError as exc:
        sys.stderr.write(f"[error] {exc.code}: {exc}\n")
        return 9
    except Exception as exc:  # noqa: BLE001
        logger.exception("unexpected: {}", exc)
        return 9

    sys.stdout.write(json.dumps(payload.as_dict(), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
