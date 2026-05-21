"""Phase L invariant check — state-label resolver anchor.

The state-label resolver (apps/api/src/system_state/resolver.py) MUST
anchor on `paper_trade.fill_ts` (engine decisions), not on
`paper_equity_snapshot.recorded_at` (which writes nightly even on
quiet days and would mask LIVE_DORMANT / OBSERVING substates).

This was locked at D2.5. This script enforces the invariant in CI.

Exit codes:
  0 — anchor is paper_trade.fill_ts (correct).
  1 — anchor drifted or _latest_live_decision missing.

Usage:
  python infra/ci/constitutional_checklist/resolver_anchor_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RESOLVER = REPO_ROOT / "apps" / "api" / "src" / "system_state" / "resolver.py"

# The canonical SELECT we expect inside _latest_live_decision.
REQUIRED_PATTERN = re.compile(
    r"_latest_live_decision[\s\S]{0,400}?SELECT\s+MAX\s*\(\s*fill_ts\s*\)\s+FROM\s+paper_trade",
    re.IGNORECASE,
)

# Forbidden anchor inside the same function.
FORBIDDEN_PATTERN = re.compile(
    r"_latest_live_decision[\s\S]{0,400}?paper_equity_snapshot",
    re.IGNORECASE,
)


def main() -> int:
    if not RESOLVER.exists():
        print(f"FAIL: resolver missing at {RESOLVER}", file=sys.stderr)
        return 1
    src = RESOLVER.read_text(encoding="utf-8")
    if not REQUIRED_PATTERN.search(src):
        print(
            "FAIL: resolver._latest_live_decision must anchor on "
            "`SELECT MAX(fill_ts) FROM paper_trade`. Anchor drifted "
            "or function missing.",
            file=sys.stderr,
        )
        return 1
    if FORBIDDEN_PATTERN.search(src):
        print(
            "FAIL: resolver._latest_live_decision references "
            "paper_equity_snapshot. Forbidden — snapshots write "
            "nightly even on quiet days and would mask substates.",
            file=sys.stderr,
        )
        return 1
    print("resolver_anchor_lint: OK (paper_trade.fill_ts anchor preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
