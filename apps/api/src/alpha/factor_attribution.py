"""Deterministic factor attribution per decision.

7-factor breakdown attached to every decision_log row. Scores in [-1, +1].
Positive = helped trade. Negative = hurt trade. Zero = neutral/unavailable.

No future-outcome access. All inputs known at decision_ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FactorAttribution:
    momentum:     float = 0.0
    volatility:   float = 0.0
    regime:       float = 0.0
    catalyst:     float = 0.0
    data_quality: float = 0.0
    risk:         float = 0.0
    execution:    float = 0.0
    version:      str = ""
    raw_inputs:   dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "momentum":     _r(self.momentum),
            "volatility":   _r(self.volatility),
            "regime":       _r(self.regime),
            "catalyst":     _r(self.catalyst),
            "data_quality": _r(self.data_quality),
            "risk":         _r(self.risk),
            "execution":    _r(self.execution),
            "version":      self.version,
            "raw_inputs":   dict(self.raw_inputs),
        }


def compute_factor_attribution(
    *,
    inputs_used: dict[str, Any] | None = None,
    context_values: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
    risk_context: dict[str, Any] | None = None,
    version: str = "factor-v1.0.0",
) -> FactorAttribution:
    """Return FactorAttribution. All args optional — missing → factor=0."""
    inp = inputs_used or {}
    ctx = context_values or {}
    cat = catalyst or {}
    dq  = data_quality or {}
    rk  = risk_context or {}

    # --- Momentum: 20d return scaled ---
    mean_ret = _num(inp.get("mean_20d_ret"), default=0.0)
    # Clamp to [-2%, +2%] per day → [-1, +1]
    momentum = _clip(mean_ret * 50.0)

    # --- Volatility: favors 'controlled' vol; penalises extremes ---
    vol_elev = bool(inp.get("vol_elevated"))
    vol_exp  = bool(inp.get("vol_expanding"))
    atr_ratio = _num(inp.get("atr_ratio"), default=1.0)
    # sweet spot 0.9..1.3 → positive; above 1.5 → negative
    vol_score = 0.0
    if 0.9 <= atr_ratio <= 1.3: vol_score += 0.4
    if atr_ratio > 1.5:         vol_score -= 0.6
    if atr_ratio < 0.7:         vol_score -= 0.3
    if vol_elev and vol_exp:    vol_score -= 0.3
    volatility = _clip(vol_score)

    # --- Regime: directional=+ / stress=- / neutral=0 ---
    if bool(ctx.get("stress_regime")):
        regime = -0.6
    elif bool(ctx.get("directional_regime")):
        regime = 0.6
    else:
        regime = 0.0
    gates = int(_num(ctx.get("gates_favorable"), default=0))
    regime = _clip(regime + (gates - 2) * 0.1)

    # --- Catalyst: event_risk hurts, high catalyst_score w/o risk helps ---
    evt_risk = _num(cat.get("event_risk_score"), default=0.0)
    cat_score = _num(cat.get("catalyst_score"), default=0.0)
    catalyst_f = _clip(cat_score * 0.5 - evt_risk * 0.8)
    # Hard blocks dominate
    if str(cat.get("trade_policy")) == "block_new_entry":
        catalyst_f = -1.0
    elif str(cat.get("trade_policy")) == "watch_only":
        catalyst_f = -0.8

    # --- Data quality ---
    conf = _num(dq.get("confidence"), default=1.0)
    missing = len(dq.get("missing_fields") or [])
    stale = len(dq.get("stale_fields") or [])
    dq_f = _clip(conf - 1.0 - missing * 0.15 - stale * 0.1)
    # Re-shift: conf=1,no missing,no stale → 0; lower conf → negative
    # Above only produces <=0 so boost positive when conf=1 AND no issues
    if conf >= 0.95 and missing == 0 and stale == 0:
        dq_f = 0.3

    # --- Risk: concentration + drawdown state ---
    dd_pct = _num(rk.get("current_drawdown_pct"), default=0.0)
    conc = _num(rk.get("concentration_score"), default=0.0)  # 0..1
    risk_f = _clip(-conc * 0.6 + (dd_pct / 100.0) * 5.0)
    # dd_pct is negative typically; deeper drawdown → more negative

    # --- Execution: proxy from engine confidence + gates ---
    eng_conf = _num(dq.get("engine_confidence"), default=0.5)
    exec_f = _clip((eng_conf - 0.5) * 1.5)

    raw = {
        "mean_20d_ret":     mean_ret,
        "atr_ratio":        atr_ratio,
        "vol_elevated":     vol_elev,
        "vol_expanding":    vol_exp,
        "stress_regime":    bool(ctx.get("stress_regime")),
        "directional":      bool(ctx.get("directional_regime")),
        "gates_favorable":  gates,
        "event_risk":       evt_risk,
        "catalyst_score":   cat_score,
        "trade_policy":     cat.get("trade_policy"),
        "data_confidence":  conf,
        "missing_count":    missing,
        "stale_count":      stale,
        "drawdown_pct":     dd_pct,
        "concentration":    conc,
        "engine_confidence": eng_conf,
    }

    return FactorAttribution(
        momentum=momentum, volatility=volatility, regime=regime,
        catalyst=catalyst_f, data_quality=dq_f, risk=risk_f,
        execution=exec_f, version=version, raw_inputs=raw,
    )


# ---------------------------------------------------------------------------

def _num(v: Any, *, default: float = 0.0) -> float:
    try:
        x = float(v)
        if x != x:   # NaN check without importing math
            return default
        return x
    except (TypeError, ValueError):
        return default


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x < lo: return lo
    if x > hi: return hi
    return x


def _r(x: float) -> float:
    return round(float(x), 4)
