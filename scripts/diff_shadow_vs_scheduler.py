"""Phase 1.5 shadow vs scheduler diff — structured JSON output.

Rules (unchanged from Phase 1):
  1. Asset set EXACTLY matches.
  2. Top-N overlap = 100%.
  3. Ordering tolerance: reorder allowed only if Prefect score delta
     between the two symbols involved is ≤ SCORE_EPSILON.

JSON output always printed to stdout, regardless of pass/fail, to support
downstream machine readers + shadow_run_log writes.

Usage::

    python -m scripts.diff_shadow_vs_scheduler --as-of 2026-04-17
    python -m scripts.diff_shadow_vs_scheduler --as-of 2026-04-17 --top-n 10
    python -m scripts.diff_shadow_vs_scheduler --as-of 2026-04-17 --json-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select, text

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset, CandidateIdea
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

SCORE_EPSILON = 1e-4
DEFAULT_TOP_N = 10


@dataclass
class RankedRow:
    symbol: str
    rank_position: int
    score: float


@dataclass
class DiffResult:
    ok: bool
    as_of: str
    top_n: int
    asset_set_match: bool = False
    topn_match: bool = False
    reorder_count: int = 0
    max_score_delta: float = 0.0
    reason: str | None = None
    failing_symbols: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "ok": self.ok,
            "as_of": self.as_of,
            "top_n": self.top_n,
            "asset_set_match": self.asset_set_match,
            "topn_match": self.topn_match,
            "reorder_count": self.reorder_count,
            "max_score_delta": self.max_score_delta,
            "reason": self.reason,
            "failing_symbols": self.failing_symbols,
            "details": self.details,
        }


def _load_prefect_ranked(session, as_of: dt.date) -> list[RankedRow]:
    sql = text(
        "SELECT symbol, rank_position, score FROM ranked_signal "
        "WHERE as_of_date = :d ORDER BY rank_position ASC"
    )
    rows = session.execute(sql, {"d": as_of}).all()
    return [RankedRow(symbol=r[0], rank_position=r[1], score=float(r[2])) for r in rows]


def _load_scheduler_buys(session, as_of: dt.date) -> list[str]:
    stmt = (
        select(Asset.symbol)
        .join(CandidateIdea, CandidateIdea.asset_id == Asset.id)
        .where(
            CandidateIdea.as_of_date == as_of,
            CandidateIdea.status == "accepted",
            CandidateIdea.action == "Buy",
            CandidateIdea.model_version == MODEL_VERSION,
        )
        .order_by(
            CandidateIdea.composite_score.desc().nullslast(),
            Asset.symbol.asc(),
        )
    )
    return [row[0] for row in session.execute(stmt).all()]


def diff_day(as_of: dt.date, top_n: int = DEFAULT_TOP_N) -> DiffResult:
    with SessionLocal() as session:
        prefect = _load_prefect_ranked(session, as_of)
        scheduler = _load_scheduler_buys(session, as_of)

    result = DiffResult(ok=False, as_of=as_of.isoformat(), top_n=top_n)

    if not prefect and not scheduler:
        result.ok = True
        result.asset_set_match = True
        result.topn_match = True
        result.details["note"] = "both_empty"
        return result

    p_syms = [r.symbol for r in prefect]
    s_syms = scheduler
    p_set, s_set = set(p_syms), set(s_syms)

    # --- 1. Asset set ---
    result.asset_set_match = p_set == s_set
    if not result.asset_set_match:
        extra = sorted(p_set - s_set)
        missing = sorted(s_set - p_set)
        result.reason = "asset_set_mismatch"
        result.failing_symbols = sorted(set(extra) | set(missing))
        result.details = {
            "extra_prefect": extra, "missing_prefect": missing,
            "prefect_count": len(p_set), "scheduler_count": len(s_set),
        }
        return result

    # --- 2. Top-N overlap ---
    topN_p = p_syms[:top_n]
    topN_s = s_syms[:top_n]
    result.topn_match = set(topN_p) == set(topN_s)
    if not result.topn_match:
        only_p = sorted(set(topN_p) - set(topN_s))
        only_s = sorted(set(topN_s) - set(topN_p))
        result.reason = "topn_overlap_incomplete"
        result.failing_symbols = sorted(set(only_p) | set(only_s))
        result.details = {
            "only_in_prefect_topN": only_p,
            "only_in_scheduler_topN": only_s,
        }
        return result

    # --- 3. Ordering tolerance ---
    score_by = {r.symbol: r.score for r in prefect}
    reorders = []
    max_delta = 0.0
    for i in range(len(topN_p)):
        if topN_p[i] == topN_s[i]:
            continue
        p_score = score_by.get(topN_p[i], 0.0)
        s_score = score_by.get(topN_s[i], 0.0)
        delta = abs(p_score - s_score)
        max_delta = max(max_delta, delta)
        if delta > SCORE_EPSILON:
            result.reason = f"material_reorder_at_position_{i}"
            result.failing_symbols = [topN_p[i], topN_s[i]]
            result.details = {
                "position": i,
                "prefect_symbol": topN_p[i],
                "scheduler_symbol": topN_s[i],
                "prefect_score_p": p_score,
                "prefect_score_s": s_score,
                "delta": delta,
                "epsilon": SCORE_EPSILON,
            }
            result.reorder_count = len(reorders) + 1
            result.max_score_delta = max_delta
            return result
        reorders.append({
            "position": i, "prefect": topN_p[i], "scheduler": topN_s[i],
            "delta": delta,
        })

    result.reorder_count = len(reorders)
    result.max_score_delta = max_delta
    result.ok = True
    result.details = {"tolerated_reorders": reorders}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True, type=lambda s: dt.date.fromisoformat(s))
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--json-only", action="store_true",
                        help="Print JSON to stdout only (for pipes).")
    args = parser.parse_args()

    result = diff_day(args.as_of, top_n=args.top_n)
    payload = result.to_json()

    # Machine-readable output ALWAYS on stdout.
    print(json.dumps(payload))

    if not args.json_only:
        if result.ok:
            logger.info(
                "[diff] as_of={} OK reorders={} max_delta={:.6g}",
                result.as_of, result.reorder_count, result.max_score_delta,
            )
        else:
            logger.error(
                "[diff] as_of={} FAIL reason={} failing={}",
                result.as_of, result.reason, result.failing_symbols,
            )

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
