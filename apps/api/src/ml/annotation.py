"""Advisory annotation builder — attaches ML/baseline/pattern metadata to
a live decision WITHOUT affecting execution.

Called by the daily paper pipeline after the selector fires but before the
decision is persisted. Pure read-only: never raises, returns neutral dicts
on failure so the pipeline can't be broken by a missing snapshot.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.ml.snapshots import latest_snapshot


def build_decision_annotation(
    session: Session | None,
    *,
    symbol: str,
    engine: str,
    data_quality: dict[str, Any] | None,
    catalyst: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return {ml_advisory, baseline_advisory, pattern_flags} for a decision.

    All three keys are always present (possibly empty) so the decision
    writer can pass them through uniformly.
    """
    ml_advisory: dict[str, Any] = {}
    baseline_advisory: dict[str, Any] = {}
    pattern_flags: dict[str, Any] = {}

    # Dataset tier + Engine C status from latest persisted snapshot
    tier = "unknown"
    dataset_rows = 0
    labeled_rows = 0
    engine_c = "ADVISORY_READY"
    baseline_best = None
    patterns: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        if session is not None:
            snap = latest_snapshot(session)
        else:
            snap = None
        if snap:
            tier = str(snap.get("tier") or "unknown")
            dataset_rows = int(snap.get("row_count") or 0)
            labeled_rows = int(snap.get("labeled_row_count") or 0)
            ec = snap.get("engine_c_status") or {}
            if isinstance(ec, dict):
                engine_c = str(ec.get("engine_c_ml_status") or engine_c)
            br = snap.get("baseline_results") or {}
            if isinstance(br, dict):
                baseline_best = _best_baseline(br)
            patterns = snap.get("patterns") or {}
            if isinstance(patterns, dict):
                patterns_pos = patterns.get("positive_patterns") or []
                patterns_neg = patterns.get("negative_patterns") or []
            else:
                patterns_pos, patterns_neg = [], []
            warnings = snap.get("warnings") or []
    except Exception as e:
        # Never break the pipeline because snapshot had a hiccup
        warnings = [f"annotation: latest_snapshot failed ({type(e).__name__})"]
        patterns_pos, patterns_neg = [], []

    # Advisory gate — mirrors advisory.build_advisory but no model call yet
    data_conf = _safe_float((data_quality or {}).get("confidence"), default=0.0)
    catalyst_policy = _safe_str((catalyst or {}).get("trade_policy"), "neutral")
    ml_advisory = {
        "ml_status": engine_c,
        "suggested_action": _advisory_action(
            data_conf=data_conf,
            catalyst_policy=catalyst_policy,
            dataset_rows=dataset_rows,
        ),
        "reason": _advisory_reason(
            engine_c=engine_c,
            data_conf=data_conf,
            catalyst_policy=catalyst_policy,
        ),
        "engine_c_status": engine_c,
        "dataset_tier": tier,
        "dataset_rows": dataset_rows,
        "labeled_rows": labeled_rows,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    baseline_advisory = {
        "best_baseline": (baseline_best or {}).get("name") if baseline_best
                         else None,
        "best_baseline_sharpe": (baseline_best or {}).get("sharpe_proxy")
                                 if baseline_best else None,
        "best_baseline_hit_rate": (baseline_best or {}).get("hit_rate")
                                   if baseline_best else None,
    }
    pattern_flags = _pattern_flags_for_symbol(
        symbol=symbol, engine=engine,
        positive=patterns_pos, negative=patterns_neg,
    )
    if warnings:
        pattern_flags["warnings"] = warnings[:5]
    return {
        "ml_advisory": ml_advisory,
        "baseline_advisory": baseline_advisory,
        "pattern_flags": pattern_flags,
    }


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _advisory_action(
    *, data_conf: float, catalyst_policy: str, dataset_rows: int,
) -> str:
    if dataset_rows < 200:
        return "needs_more_data"
    if data_conf < 0.3:
        return "avoid"
    if catalyst_policy == "block_new_entry":
        return "avoid"
    if catalyst_policy == "watch_only":
        return "avoid"
    if catalyst_policy in {"reduce_size", "require_confirmation"}:
        return "reduce"
    return "accept"


def _advisory_reason(
    *, engine_c: str, data_conf: float, catalyst_policy: str,
) -> str:
    parts = [f"engine_c={engine_c}"]
    parts.append(f"data_conf={data_conf:.2f}")
    parts.append(f"catalyst_policy={catalyst_policy}")
    return "; ".join(parts)


def _best_baseline(br: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the baseline with the highest finite sharpe_proxy."""
    rows: list[dict[str, Any]] = []
    for key in ("v1", "v2"):
        r = br.get(key)
        if isinstance(r, list):
            rows.extend(r)
    if not rows:
        return None
    def score(r: dict[str, Any]) -> float:
        s = r.get("sharpe_proxy")
        try:
            v = float(s)
        except (TypeError, ValueError):
            return float("-inf")
        if v != v or v in (float("inf"), float("-inf")):
            return float("-inf")
        return v
    rows.sort(key=score, reverse=True)
    return rows[0]


def _pattern_flags_for_symbol(
    *, symbol: str, engine: str,
    positive: list[dict[str, Any]],
    negative: list[dict[str, Any]],
) -> dict[str, Any]:
    """Tag decision with nearby positive / negative pattern buckets.

    Only attaches top-3 from each side so the decision_log blob stays small.
    """
    def _pick(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in cands[:3]:
            if not isinstance(c, dict):
                continue
            # Prefer axes that plausibly match this decision
            out.append({
                "axis":    c.get("axis"),
                "bucket":  c.get("bucket"),
                "lift":    c.get("lift_vs_control"),
                "n":       c.get("n"),
                "low_confidence": c.get("low_confidence"),
            })
        return out
    return {
        "symbol": symbol,
        "engine": engine,
        "positive": _pick(positive),
        "negative": _pick(negative),
    }


def _safe_float(v: Any, *, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v: Any, default: str) -> str:
    if v is None:
        return default
    return str(v)
