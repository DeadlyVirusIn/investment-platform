"""SYSTEM-ALPHA-8 — deterministic context-similarity engine.

Reads labeled paper_trade_log + decision_log context, builds normalized
vectors, finds K nearest past decisions for a new candidate, computes
weighted avg_return. If historical peers lost money → additional size
reduction.

Never ML. No training. Pure L2 distance on normalized features.
Never increases size. Floor = 0.5 (less aggressive than context buckets).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


# --- safety + thresholds ---
MIN_MULTIPLIER = 0.5          # never cut by more than half via similarity
MIN_NEIGHBORS = 20
TOP_K = 20
LOOKBACK_DAYS = 180
MAX_DISTANCE = 1.5            # drop neighbors beyond this normalized dist
CACHE_TTL_SECS = 60 * 10      # 10 min rebuild cadence


# Feature names + hard normalization bounds so distances stay comparable.
# Boolean → 0/1; numeric → min/max clamp + scale to [0,1].
FEATURE_BOUNDS: dict[str, dict[str, float]] = {
    "regime_stress":        {"min": 0.0, "max": 1.0},
    "regime_directional":   {"min": 0.0, "max": 1.0},
    "regime_neutral":       {"min": 0.0, "max": 1.0},
    "engine_a":             {"min": 0.0, "max": 1.0},
    "engine_b":             {"min": 0.0, "max": 1.0},
    "exploratory":          {"min": 0.0, "max": 1.0},
    "gates_passed":         {"min": 0.0, "max": 4.0},
    "credit_stable":        {"min": 0.0, "max": 1.0},
    "liquidity_expanding":  {"min": 0.0, "max": 1.0},
    "vol_elevated":         {"min": 0.0, "max": 1.0},
    "data_confidence":      {"min": 0.0, "max": 1.0},
    "event_risk":           {"min": 0.0, "max": 1.0},
}

FEATURE_KEYS = tuple(FEATURE_BOUNDS.keys())


# ---------------------------------------------------------------------------
# Vector building
# ---------------------------------------------------------------------------

def _vec_from_parts(
    *,
    regime: str, engine: str, exploratory: bool,
    gates_passed: int | None, context: dict[str, Any] | None,
    data_confidence: float | None, event_risk: float | None,
) -> list[float]:
    ctx = context or {}
    feats = {
        "regime_stress":       1.0 if regime == "stress"       else 0.0,
        "regime_directional":  1.0 if regime == "directional"  else 0.0,
        "regime_neutral":      1.0 if regime == "neutral"      else 0.0,
        "engine_a":            1.0 if (engine or "").upper() == "A" else 0.0,
        "engine_b":            1.0 if (engine or "").upper() == "B" else 0.0,
        "exploratory":         1.0 if exploratory else 0.0,
        "gates_passed":        float(gates_passed or 0),
        "credit_stable":       1.0 if ctx.get("credit_stable") else 0.0,
        "liquidity_expanding": 1.0 if ctx.get("liquidity_expanding") else 0.0,
        "vol_elevated":        1.0 if ctx.get("vol_elevated") else 0.0,
        "data_confidence":     float(data_confidence or 0.0),
        "event_risk":          float(event_risk or 0.0),
    }
    # Normalize into [0, 1] per FEATURE_BOUNDS
    out: list[float] = []
    for k in FEATURE_KEYS:
        b = FEATURE_BOUNDS[k]
        lo, hi = b["min"], b["max"]
        rng = hi - lo if hi > lo else 1.0
        v = feats.get(k, 0.0)
        v = max(lo, min(hi, v))
        out.append((v - lo) / rng)
    return out


def build_current_vector(
    *,
    regime: str, engine: str, exploratory: bool,
    gates_passed: int | None,
    context_values: dict[str, Any] | None,
    catalyst: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
) -> list[float]:
    dc = (data_quality or {}).get("confidence")
    er = (catalyst or {}).get("event_risk_score")
    return _vec_from_parts(
        regime=regime, engine=engine, exploratory=exploratory,
        gates_passed=gates_passed, context=context_values,
        data_confidence=(
            float(dc) if isinstance(dc, (int, float)) else None
        ),
        event_risk=(
            float(er) if isinstance(er, (int, float)) else None
        ),
    )


# ---------------------------------------------------------------------------
# Historical store (DB + in-process cache)
# ---------------------------------------------------------------------------

@dataclass
class HistoricalPoint:
    vector: list[float]
    outcome_pct: float            # net_ret_pct
    engine: str
    exploratory: bool


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, list[HistoricalPoint]]] = {}


def _now_secs() -> float:
    import time
    return time.time()


def load_historical(
    session: Session, *, lookback_days: int = LOOKBACK_DAYS,
    force: bool = False,
) -> list[HistoricalPoint]:
    key = f"lb:{lookback_days}"
    if not force:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and (_now_secs() - hit[0]) < CACHE_TTL_SECS:
                return list(hit[1])
    try:
        rows = session.execute(text("""
            SELECT t.engine, t.regime_at_entry, t.exploratory_paper,
                   t.net_ret_pct,
                   d.context_values, d.feature_confidence,
                   d.gates_passed, d.catalyst
            FROM paper_trade_log t
            JOIN decision_log d
              ON d.instrument = t.instrument
             AND d.as_of_date = t.entry_date
            WHERE t.status = 'closed'
              AND t.net_ret_pct IS NOT NULL
              AND t.entry_date >= CURRENT_DATE - :lb
        """), {"lb": int(lookback_days)}).mappings().all()
    except Exception as e:
        logger.warning("similarity: historical read failed: {}", e)
        return []

    points: list[HistoricalPoint] = []
    for r in rows:
        reg = (r.get("regime_at_entry") or "").lower()
        if reg not in {"stress", "directional", "neutral"}:
            reg = "directional" if reg == "exploratory" else "neutral"
        catalyst = r.get("catalyst") or {}
        data_q = r.get("feature_confidence")
        dc = float(data_q) if data_q is not None else None
        er = None
        if isinstance(catalyst, dict):
            er_raw = catalyst.get("event_risk_score")
            if isinstance(er_raw, (int, float)):
                er = float(er_raw)
        v = _vec_from_parts(
            regime=reg,
            engine=(r.get("engine") or "NONE").upper(),
            exploratory=bool(r.get("exploratory_paper")),
            gates_passed=r.get("gates_passed"),
            context=r.get("context_values"),
            data_confidence=dc,
            event_risk=er,
        )
        try:
            ret = float(r["net_ret_pct"])
        except (TypeError, ValueError):
            continue
        points.append(HistoricalPoint(
            vector=v, outcome_pct=ret,
            engine=(r.get("engine") or "NONE").upper(),
            exploratory=bool(r.get("exploratory_paper")),
        ))

    with _CACHE_LOCK:
        _CACHE[key] = (_now_secs(), list(points))
    return points


def invalidate_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Similarity lookup
# ---------------------------------------------------------------------------

@dataclass
class SimilarityResult:
    matched: bool
    n_neighbors: int
    avg_return_pct: float
    win_rate: float
    multiplier: float
    avg_distance: float
    top_similarity: float         # 1 / (1 + min_distance); ≤ 1.0
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "n_neighbors": self.n_neighbors,
            "avg_return_pct": round(self.avg_return_pct, 4),
            "win_rate": round(self.win_rate, 4),
            "multiplier": round(self.multiplier, 4),
            "avg_distance": round(self.avg_distance, 4),
            "similarity_score": round(self.top_similarity, 4),
            "reason": self.reason,
            "details": dict(self.details),
        }


def _l2(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def evaluate_similarity(
    current_vector: list[float],
    historical: list[HistoricalPoint],
    *,
    top_k: int = TOP_K,
    min_neighbors: int = MIN_NEIGHBORS,
    max_distance: float = MAX_DISTANCE,
) -> SimilarityResult:
    if not historical or len(historical) < min_neighbors:
        return SimilarityResult(
            matched=False, n_neighbors=0, avg_return_pct=0.0,
            win_rate=0.0, multiplier=1.0, avg_distance=0.0,
            top_similarity=0.0,
            reason=(f"only {len(historical)} labeled rows — need "
                    f"{min_neighbors}"),
        )
    # Compute distances
    scored: list[tuple[float, HistoricalPoint]] = []
    for p in historical:
        d = _l2(current_vector, p.vector)
        if math.isfinite(d) and d <= max_distance:
            scored.append((d, p))
    scored.sort(key=lambda t: t[0])
    neighbors = scored[:top_k]
    if len(neighbors) < min_neighbors:
        return SimilarityResult(
            matched=False,
            n_neighbors=len(neighbors),
            avg_return_pct=0.0, win_rate=0.0,
            multiplier=1.0, avg_distance=0.0,
            top_similarity=(
                1.0 / (1.0 + neighbors[0][0]) if neighbors else 0.0
            ),
            reason=(f"only {len(neighbors)} close matches — need "
                    f"{min_neighbors}"),
        )
    # Weighted mean — weight = 1/(1+distance)
    weights = [1.0 / (1.0 + d) for d, _ in neighbors]
    returns = [p.outcome_pct for _, p in neighbors]
    wsum = sum(weights) or 1.0
    wavg = sum(w * r for w, r in zip(weights, returns)) / wsum
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / len(returns)
    avg_d = sum(d for d, _ in neighbors) / len(neighbors)
    top_sim = 1.0 / (1.0 + neighbors[0][0])

    multiplier = _multiplier_from(wavg, win_rate)
    reason = _reason_from(wavg, win_rate, len(neighbors))
    return SimilarityResult(
        matched=(multiplier < 1.0),
        n_neighbors=len(neighbors),
        avg_return_pct=wavg,
        win_rate=win_rate,
        multiplier=multiplier,
        avg_distance=avg_d,
        top_similarity=top_sim,
        reason=reason,
        details={
            "neighbor_distances": [round(d, 4) for d, _ in neighbors[:5]],
            "top_k": top_k,
        },
    )


def _multiplier_from(wavg: float, win_rate: float) -> float:
    """Risk-reducing only. Floor = 0.5."""
    # Strongly negative peers → 0.5
    if wavg < -0.5 or win_rate < 0.35:
        return MIN_MULTIPLIER
    # Moderately negative peers → 0.7
    if wavg < 0 and win_rate < 0.45:
        return 0.7
    # Mildly negative peers → 0.85
    if wavg < 0:
        return 0.85
    # Otherwise no reduction
    return 1.0


def _reason_from(wavg: float, win_rate: float, n: int) -> str:
    if wavg >= 0:
        return (f"Similar past contexts OK (avg {wavg:+.2f}%, "
                f"win {win_rate:.0%}, n={n}) — no reduction")
    return (f"Similar past trades underperformed "
            f"(avg {wavg:+.2f}%, win {win_rate:.0%}, n={n}) — size reduced")


# ---------------------------------------------------------------------------
# Convenience — runtime entry point
# ---------------------------------------------------------------------------

def compute_similarity_multiplier(
    session: Session, *,
    regime: str, engine: str, exploratory: bool,
    gates_passed: int | None,
    context_values: dict[str, Any] | None,
    catalyst: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
) -> SimilarityResult:
    vec = build_current_vector(
        regime=regime, engine=engine, exploratory=exploratory,
        gates_passed=gates_passed, context_values=context_values,
        catalyst=catalyst, data_quality=data_quality,
    )
    hist = load_historical(session)
    return evaluate_similarity(vec, hist)
