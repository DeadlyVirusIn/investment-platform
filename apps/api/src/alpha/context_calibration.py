"""SYSTEM-ALPHA-7 — context-aware calibration.

Groups closed paper trades into (engine × regime × mode) buckets, measures
performance per bucket, emits context-specific multipliers. Runtime picks
matching bucket for each decision.

Never increases size. Minimum multiplier floor = 0.2.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


# --- Safety ---
MIN_MULTIPLIER = 0.2
MIN_SAMPLE = 20
AUTO_MIN_CONFIDENCE = 0.70


@dataclass(frozen=True)
class ContextKey:
    engine: str               # A | B | none
    regime: str               # stress | directional | neutral
    mode: str                 # strict | exploratory

    def to_dict(self) -> dict[str, Any]:
        return {"engine": self.engine, "regime": self.regime,
                "mode": self.mode}

    def to_key(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True)
        # Short stable hash-prefixed key for the table
        h = hashlib.sha1(
            raw.encode("utf-8"), usedforsecurity=False,
        ).hexdigest()[:10]
        return f"{self.engine}|{self.regime}|{self.mode}|{h}"


@dataclass
class ContextStats:
    context: ContextKey
    sample_size: int
    win_rate: float
    avg_return: float
    median_return: float
    sharpe: float
    total_return: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "sample_size": self.sample_size,
            "win_rate": round(self.win_rate, 4),
            "avg_return": round(self.avg_return, 4),
            "median_return": round(self.median_return, 4),
            "sharpe": round(self.sharpe, 4),
            "total_return": round(self.total_return, 4),
        }


@dataclass
class ContextRec:
    context: ContextKey
    current_multiplier: float
    proposed_multiplier: float
    stats: ContextStats
    reason: str
    confidence: float
    risk_reducing: bool = True

    @property
    def auto_applicable(self) -> bool:
        return (
            self.risk_reducing
            and self.proposed_multiplier <= self.current_multiplier
            and self.confidence >= AUTO_MIN_CONFIDENCE
            and self.stats.sample_size >= MIN_SAMPLE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "context_key": self.context.to_key(),
            "current_multiplier": round(self.current_multiplier, 4),
            "proposed_multiplier": round(self.proposed_multiplier, 4),
            "stats": self.stats.to_dict(),
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
            "risk_reducing": self.risk_reducing,
            "auto_applicable": self.auto_applicable,
        }


# ---------------------------------------------------------------------------
# Build context map + recommendations
# ---------------------------------------------------------------------------

def build_context_performance(
    session: Session, *, lookback_days: int = 60,
) -> list[ContextStats]:
    rows = _load_closed(session, lookback_days)
    buckets: dict[tuple[str, str, str], list[float]] = {}
    for r in rows:
        eng = (r.get("engine") or "none").upper()
        regime = _regime_for(r)
        mode = "exploratory" if r.get("exploratory_paper") else "strict"
        k = (eng, regime, mode)
        ret = r.get("net_ret_pct")
        if ret is None:
            continue
        buckets.setdefault(k, []).append(float(ret))

    out: list[ContextStats] = []
    for (eng, regime, mode), rets in buckets.items():
        n = len(rets)
        wins = sum(1 for x in rets if x > 0)
        mean = sum(rets) / n
        median = sorted(rets)[n // 2]
        sd = _std(rets)
        sharpe = (mean / sd) if sd > 1e-9 else 0.0
        out.append(ContextStats(
            context=ContextKey(engine=eng, regime=regime, mode=mode),
            sample_size=n,
            win_rate=wins / n,
            avg_return=mean,
            median_return=median,
            sharpe=sharpe,
            total_return=sum(rets),
        ))
    out.sort(key=lambda s: -s.sample_size)
    return out


def evaluate_context_calibration(
    session: Session, *, lookback_days: int = 60,
) -> list[ContextRec]:
    stats = build_context_performance(
        session, lookback_days=lookback_days,
    )
    active = load_active_context_multipliers(session)
    recs: list[ContextRec] = []
    for s in stats:
        if s.sample_size < MIN_SAMPLE:
            continue
        key = s.context.to_key()
        current = active.get(key, 1.0)
        proposed = _propose_multiplier(s, current)
        if proposed is None:
            continue
        if proposed >= current:
            continue   # never increase
        confidence = _confidence_from_stats(s)
        reason = _reason_from_stats(s)
        recs.append(ContextRec(
            context=s.context,
            current_multiplier=current,
            proposed_multiplier=max(MIN_MULTIPLIER, proposed),
            stats=s,
            reason=reason,
            confidence=confidence,
        ))
    return recs


def _propose_multiplier(
    s: ContextStats, current: float,
) -> float | None:
    # Rule 1: avg_return < 0 AND sharpe < 0 → aggressive reduce
    if s.avg_return < 0 and s.sharpe < 0:
        if s.sample_size >= 40:
            return max(MIN_MULTIPLIER, 0.3)
        return max(MIN_MULTIPLIER, 0.5)
    # Rule 2: avg_return < 0 only → moderate reduce
    if s.avg_return < 0:
        return max(MIN_MULTIPLIER, min(current, 0.7))
    # Rule 3: win_rate < 0.42 → reduce
    if s.win_rate < 0.42:
        return max(MIN_MULTIPLIER, min(current, 0.6))
    return None


def _confidence_from_stats(s: ContextStats) -> float:
    # Confidence scales with sample + effect size
    sample_factor = min(1.0, s.sample_size / 100.0)
    effect = min(1.0, abs(s.avg_return) * 0.4)
    sharpe_factor = min(1.0, abs(s.sharpe) * 0.3)
    return round(min(1.0, 0.5 + sample_factor * 0.3
                     + effect * 0.1 + sharpe_factor * 0.1), 4)


def _reason_from_stats(s: ContextStats) -> str:
    c = s.context
    bits = [
        f"Engine {c.engine}",
        f"in {c.regime} regime",
        f"({c.mode})",
        f"avg_return {s.avg_return:.2f}%",
        f"win {s.win_rate:.0%}",
        f"sharpe {s.sharpe:.2f}",
        f"n={s.sample_size}",
    ]
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_recommendations(
    session: Session, recs: list[ContextRec],
    *, auto_apply: bool = False,
) -> dict[str, Any]:
    applied = 0
    for r in recs:
        session.execute(text("""
            INSERT INTO alpha_context_log
              (context_key, action, old_multiplier, new_multiplier,
               reason, confidence, sample_size, applied_by, context)
            VALUES
              (:k, 'recommend', :om, :nm, :rea, :c, :n,
               'system', CAST(:ctx AS jsonb))
        """), {
            "k": r.context.to_key(),
            "om": r.current_multiplier,
            "nm": r.proposed_multiplier,
            "rea": r.reason,
            "c": r.confidence,
            "n": r.stats.sample_size,
            "ctx": json.dumps(r.context.to_dict()),
        })
        if auto_apply and r.auto_applicable:
            apply_context_rec(session, r, applied_by="system")
            applied += 1
    session.commit()
    return {"recommended": len(recs), "auto_applied": applied}


def apply_context_rec(
    session: Session, r: ContextRec,
    *, applied_by: str = "operator",
) -> None:
    session.execute(text("""
        INSERT INTO alpha_context_multiplier
          (context_key, context, multiplier, reason, confidence,
           sample_size, applied_by, previous_multiplier, status)
        VALUES
          (:k, CAST(:ctx AS jsonb), :nm, :rea, :c, :n,
           :ab, :om, 'active')
        ON CONFLICT (context_key) DO UPDATE SET
          previous_multiplier = alpha_context_multiplier.multiplier,
          multiplier = EXCLUDED.multiplier,
          reason = EXCLUDED.reason,
          confidence = EXCLUDED.confidence,
          sample_size = EXCLUDED.sample_size,
          applied_by = EXCLUDED.applied_by,
          applied_at = NOW(),
          status = 'active'
    """), {
        "k": r.context.to_key(),
        "ctx": json.dumps(r.context.to_dict()),
        "nm": r.proposed_multiplier,
        "rea": r.reason,
        "c": r.confidence,
        "n": r.stats.sample_size,
        "ab": applied_by,
        "om": r.current_multiplier,
    })
    session.execute(text("""
        INSERT INTO alpha_context_log
          (context_key, action, old_multiplier, new_multiplier,
           reason, confidence, sample_size, applied_by, context)
        VALUES
          (:k, 'apply', :om, :nm, :rea, :c, :n, :ab,
           CAST(:ctx AS jsonb))
    """), {
        "k": r.context.to_key(),
        "om": r.current_multiplier,
        "nm": r.proposed_multiplier,
        "rea": r.reason,
        "c": r.confidence,
        "n": r.stats.sample_size,
        "ab": applied_by,
        "ctx": json.dumps(r.context.to_dict()),
    })


def revert_context(
    session: Session, context_key: str,
    *, applied_by: str = "operator", reason: str = "",
) -> bool:
    row = session.execute(text("""
        SELECT multiplier, previous_multiplier, context
        FROM alpha_context_multiplier
        WHERE context_key = :k AND status = 'active'
    """), {"k": context_key}).mappings().first()
    if row is None:
        return False
    prev = row.get("previous_multiplier")
    target = float(prev) if prev is not None else 1.0
    session.execute(text("""
        UPDATE alpha_context_multiplier
           SET previous_multiplier = multiplier,
               multiplier = :m,
               reason = :r,
               applied_by = :ab,
               applied_at = NOW()
         WHERE context_key = :k
    """), {"m": target, "r": reason or "manual revert",
            "ab": applied_by, "k": context_key})
    session.execute(text("""
        INSERT INTO alpha_context_log
          (context_key, action, old_multiplier, new_multiplier,
           reason, confidence, sample_size, applied_by, context)
        VALUES
          (:k, 'revert', :om, :nm, :r, 0, 0, :ab, CAST(:ctx AS jsonb))
    """), {
        "k": context_key, "om": float(row["multiplier"]),
        "nm": target, "r": reason or "manual revert",
        "ab": applied_by,
        "ctx": json.dumps(row.get("context") or {}),
    })
    session.commit()
    return True


# ---------------------------------------------------------------------------
# Runtime lookup
# ---------------------------------------------------------------------------

def load_active_context_multipliers(session: Session) -> dict[str, float]:
    try:
        rows = session.execute(text("""
            SELECT context_key, multiplier
            FROM alpha_context_multiplier
            WHERE status = 'active' AND multiplier < 1.0
        """)).mappings().all()
    except Exception as e:
        logger.warning(
            "context_calibration: active read failed: {}", e,
        )
        return {}
    return {r["context_key"]: float(r["multiplier"]) for r in rows}


def match_context_multiplier(
    session: Session,
    *,
    engine: str, regime: str, mode: str,
) -> tuple[float, str | None]:
    """Return (multiplier, matched_context_key_or_None). 1.0 when no match."""
    key = ContextKey(
        engine=(engine or "none").upper(),
        regime=(regime or "neutral"),
        mode=(mode or "strict"),
    ).to_key()
    try:
        row = session.execute(text("""
            SELECT multiplier FROM alpha_context_multiplier
            WHERE context_key = :k AND status = 'active'
        """), {"k": key}).mappings().first()
    except Exception as e:
        logger.warning(
            "context_calibration: match read failed: {}", e,
        )
        return 1.0, None
    if row is None:
        return 1.0, None
    try:
        m = float(row["multiplier"])
    except (TypeError, ValueError):
        return 1.0, None
    # Defensive clamp — never allow above 1.0 even if DB corrupted
    return max(MIN_MULTIPLIER, min(1.0, m)), key


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _regime_for(row: dict[str, Any]) -> str:
    r = (row.get("regime_at_entry") or "").lower()
    if r in {"stress", "directional", "neutral", "exploratory"}:
        return "directional" if r == "exploratory" else r
    return "neutral"


def _load_closed(
    session: Session, lookback_days: int,
) -> list[dict[str, Any]]:
    try:
        rows = session.execute(text("""
            SELECT engine, regime_at_entry, exploratory_paper,
                   net_ret_pct, entry_date
            FROM paper_trade_log
            WHERE status = 'closed'
              AND net_ret_pct IS NOT NULL
              AND entry_date >= CURRENT_DATE - :lb
        """), {"lb": int(lookback_days)}).mappings().all()
    except Exception as e:
        logger.warning(
            "context_calibration: trade read failed: {}", e,
        )
        return []
    return [dict(r) for r in rows]


def _std(xs: list[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
