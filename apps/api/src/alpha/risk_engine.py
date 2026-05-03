"""Portfolio-level risk score. Recommendation-only by default."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class RiskScore:
    portfolio_risk_score: float
    concentration_score:  float
    correlation_score:    float
    drawdown_score:       float
    event_risk_score:     float
    regime_risk_score:    float
    drawdown_recommendation: str
    regime_scaling_recommendation: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_risk_score": round(self.portfolio_risk_score, 4),
            "concentration_score":  round(self.concentration_score, 4),
            "correlation_score":    round(self.correlation_score, 4),
            "drawdown_score":       round(self.drawdown_score, 4),
            "event_risk_score":     round(self.event_risk_score, 4),
            "regime_risk_score":    round(self.regime_risk_score, 4),
            "drawdown_recommendation": self.drawdown_recommendation,
            "regime_scaling_recommendation": self.regime_scaling_recommendation,
            "warnings": list(self.warnings),
        }


def compute_portfolio_risk(
    *,
    positions: list[dict[str, Any]],
    current_drawdown_pct: float,
    regime: str,
    volatility_state: str = "normal",
    events_soon: int = 0,
    sector_lookup: dict[str, str] | None = None,
) -> RiskScore:
    """`positions` = [{symbol, weight_pct, has_earnings_soon}, …].

    weight_pct is position size as % of portfolio NAV (0..100).
    """
    warnings: list[str] = []
    if not positions:
        return RiskScore(
            portfolio_risk_score=0.0,
            concentration_score=0.0,
            correlation_score=0.0,
            drawdown_score=_dd_score(current_drawdown_pct),
            event_risk_score=0.0,
            regime_risk_score=_regime_score(regime, volatility_state),
            drawdown_recommendation=_dd_recommendation(current_drawdown_pct),
            regime_scaling_recommendation=_regime_recommendation(
                regime, volatility_state,
            ),
            warnings=warnings,
        )

    # --- Concentration: Herfindahl-like ---
    weights = np.array([p.get("weight_pct", 0.0) for p in positions],
                        dtype=float) / 100.0
    hhi = float(np.sum(weights ** 2))
    # hhi=1 → single position, hhi=1/n → fully diversified
    concentration = min(1.0, hhi)

    # --- Correlation proxy: sector concentration ---
    if sector_lookup is not None:
        sector_w: dict[str, float] = {}
        for p, w in zip(positions, weights):
            sec = sector_lookup.get(p["symbol"].upper(), "UNKNOWN")
            sector_w[sec] = sector_w.get(sec, 0.0) + float(w)
        correlation = float(max(sector_w.values())) if sector_w else 0.0
    else:
        correlation = concentration  # fallback

    # --- Event risk: fraction of weight in near-earnings positions ---
    event_risk = float(sum(
        w for p, w in zip(positions, weights)
        if p.get("has_earnings_soon")
    ))

    regime_risk = _regime_score(regime, volatility_state)
    dd_score = _dd_score(current_drawdown_pct)
    overall = float(np.mean([
        concentration, correlation, dd_score, event_risk, regime_risk,
    ]))

    if concentration > 0.4:
        warnings.append(
            f"concentration HHI {concentration:.2f} > 0.4"
        )
    if event_risk > 0.3:
        warnings.append(
            f"{event_risk:.0%} of book in near-earnings names"
        )

    return RiskScore(
        portfolio_risk_score=overall,
        concentration_score=concentration,
        correlation_score=correlation,
        drawdown_score=dd_score,
        event_risk_score=event_risk,
        regime_risk_score=regime_risk,
        drawdown_recommendation=_dd_recommendation(current_drawdown_pct),
        regime_scaling_recommendation=_regime_recommendation(
            regime, volatility_state,
        ),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
def _dd_score(dd_pct: float) -> float:
    dd = abs(dd_pct or 0.0)
    return max(0.0, min(1.0, dd / 10.0))


def _dd_recommendation(dd_pct: float) -> str:
    dd = abs(dd_pct or 0.0)
    if dd >= 10: return "paper_only_safe_mode"
    if dd >= 7:  return "pause_weak_signals"
    if dd >= 5:  return "tighten_filters"
    if dd >= 3:  return "reduce_size"
    return "normal"


def _regime_score(regime: str, vol_state: str) -> float:
    if regime == "stress":       return 0.85
    if vol_state == "high":      return 0.7
    if regime == "directional":  return 0.3
    return 0.4


def _regime_recommendation(regime: str, vol_state: str) -> str:
    if regime == "stress":       return "defensive"
    if vol_state == "high":      return "reduce"
    if regime == "directional":  return "normal"
    return "require_confirmation"
