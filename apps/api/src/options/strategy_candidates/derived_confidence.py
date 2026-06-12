"""P0-2A — derived options confidence (v2), SHADOW ONLY.

Deterministic, explainable confidence computed from signals the
candidate already carries. Replaces nothing yet: the per-rule constant
`confidence` stays authoritative; this module's output is written into
`options_strategy_candidate.diagnostics` for distribution comparison
(model tag "v2_shadow").

Locked formula (P0-2 audit):

    confidence_v2 = 0.35 * delta_placement
                  + 0.30 * economics_quality
                  + 0.20 * signal_alignment
                  + 0.15 * freshness_quality

Components (each 0..1, clipped):

  delta_placement   1.0 at |short delta| = 0.30, falling linearly to 0
                    at +/-0.15. Multiple short legs (iron condor) take
                    the MIN of the per-leg scores. No delta available
                    -> 0.40 neutral-low, with reason.

  economics_quality credit-ratio score = clip((credit/width) / 0.33).
                    When POP is supplied: 0.5*credit_ratio +
                    0.5*clip((pop - 0.50) / 0.35). Credit or width
                    unavailable -> 0.40 neutral-low, with reason.

  signal_alignment  0.70 directional bias from the recommendation
                    signal / 0.50 neutral-by-design; +0.10 when a
                    high-importance event sits inside the DTE window
                    (cap 1.0). Fixed values are labeled in reasons —
                    v2.1 replaces 0.70 with the rec's own confidence.

  freshness_quality 1.0 at quote_age <= 60s, linear to 0.0 at 900s.
                    Age unavailable -> 0.50 neutral, with reason.

Pure stdlib — no app imports, no I/O, no clock. Same inputs always
produce the same output (auditable; safe for replay).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Formula weights — locked, keep in lockstep with module docstring.
W_DELTA      = 0.35
W_ECONOMICS  = 0.30
W_ALIGNMENT  = 0.20
W_FRESHNESS  = 0.15

# Component constants.
DELTA_TARGET           = 0.30   # ideal |short delta|
DELTA_HALF_WIDTH       = 0.15   # score reaches 0 at target +/- this
CREDIT_RATIO_FULL      = 0.33   # credit/width at which ratio score = 1.0
POP_FLOOR              = 0.50   # POP at which pop score = 0.0
POP_SPAN               = 0.35   # POP_FLOOR + span -> pop score = 1.0
NEUTRAL_LOW            = 0.40   # missing-input degradation (delta/econ)
FRESH_FULL_AGE_S       = 60.0   # quote age fully fresh up to here
FRESH_ZERO_AGE_S       = 900.0  # quote age at which freshness = 0
ALIGN_DIRECTIONAL      = 0.70   # v2.0 fixed — labeled in reasons
ALIGN_NEUTRAL          = 0.50   # neutral-by-design — labeled in reasons
ALIGN_EVENT_BONUS      = 0.10

MODEL_TAG = "v2_shadow"


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass(frozen=True)
class DerivedConfidence:
    """Result of one confidence_v2 computation."""
    value: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_diagnostics(self) -> dict:
        """Exact shadow payload shape persisted into candidate diagnostics."""
        return {
            "confidence_model": MODEL_TAG,
            "confidence_v2": self.value,
            "confidence_v2_components": dict(self.components),
            "confidence_v2_reasons": list(self.reasons),
        }


def _delta_placement(
    short_abs_deltas: list[float] | None,
) -> tuple[float, str]:
    deltas = [d for d in (short_abs_deltas or []) if d is not None]
    if not deltas:
        return NEUTRAL_LOW, (
            "delta_placement: short-leg delta unavailable -> "
            f"neutral-low {NEUTRAL_LOW:.2f}"
        )
    scores = [
        _clip01(1.0 - abs(d - DELTA_TARGET) / DELTA_HALF_WIDTH)
        for d in deltas
    ]
    score = min(scores)
    legs_txt = ", ".join(f"{d:.2f}" for d in deltas)
    return score, (
        f"delta_placement: |delta| [{legs_txt}] vs target "
        f"{DELTA_TARGET:.2f} -> {score:.2f}"
        + (" (min across short legs)" if len(deltas) > 1 else "")
    )


def _economics_quality(
    credit: float | None, width: float | None, pop: float | None,
) -> tuple[float, str]:
    if credit is None or width is None or width <= 0:
        return NEUTRAL_LOW, (
            "economics_quality: credit/width unavailable -> "
            f"neutral-low {NEUTRAL_LOW:.2f}"
        )
    ratio = credit / width
    cr_score = _clip01(ratio / CREDIT_RATIO_FULL)
    if pop is None:
        return cr_score, (
            f"economics_quality: credit/width {ratio:.2f} -> "
            f"{cr_score:.2f} (POP unavailable; credit-ratio only)"
        )
    pop_score = _clip01((pop - POP_FLOOR) / POP_SPAN)
    score = 0.5 * cr_score + 0.5 * pop_score
    return score, (
        f"economics_quality: credit/width {ratio:.2f} -> {cr_score:.2f}; "
        f"POP {pop:.2f} -> {pop_score:.2f}; blended {score:.2f}"
    )


def _signal_alignment(
    is_directional: bool, high_importance_event: bool,
) -> tuple[float, str]:
    if is_directional:
        base = ALIGN_DIRECTIONAL
        base_txt = (
            f"directional bias from recommendation signal -> "
            f"{ALIGN_DIRECTIONAL:.2f} (v2.0 fixed value)"
        )
    else:
        base = ALIGN_NEUTRAL
        base_txt = (
            f"neutral / no directional signal -> "
            f"{ALIGN_NEUTRAL:.2f} (by design)"
        )
    if high_importance_event:
        score = min(1.0, base + ALIGN_EVENT_BONUS)
        return score, (
            f"signal_alignment: {base_txt}; high-importance event inside "
            f"DTE window +{ALIGN_EVENT_BONUS:.2f} -> {score:.2f}"
        )
    return base, f"signal_alignment: {base_txt}"


def _freshness_quality(
    quote_age_seconds: float | None,
) -> tuple[float, str]:
    if quote_age_seconds is None:
        return 0.50, (
            "freshness_quality: quote age unavailable -> neutral 0.50"
        )
    age = float(quote_age_seconds)
    if age <= FRESH_FULL_AGE_S:
        return 1.0, (
            f"freshness_quality: quote age {age:.0f}s <= "
            f"{FRESH_FULL_AGE_S:.0f}s -> 1.00"
        )
    score = _clip01(
        (FRESH_ZERO_AGE_S - age) / (FRESH_ZERO_AGE_S - FRESH_FULL_AGE_S)
    )
    return score, (
        f"freshness_quality: quote age {age:.0f}s -> {score:.2f} "
        f"(linear decay {FRESH_FULL_AGE_S:.0f}s..{FRESH_ZERO_AGE_S:.0f}s; "
        f"age measured at ingest)"
    )


def compute_confidence_v2(
    *,
    short_abs_deltas: list[float] | None,
    credit: float | None,
    width: float | None,
    pop: float | None,
    is_directional: bool,
    high_importance_event: bool,
    quote_age_seconds: float | None,
) -> DerivedConfidence:
    """Compute shadow confidence_v2. Deterministic; missing inputs degrade
    to labeled neutral values — never fabricated."""
    dp, dp_reason = _delta_placement(short_abs_deltas)
    eq, eq_reason = _economics_quality(credit, width, pop)
    sa, sa_reason = _signal_alignment(is_directional, high_importance_event)
    fq, fq_reason = _freshness_quality(quote_age_seconds)

    value = round(
        W_DELTA * dp
        + W_ECONOMICS * eq
        + W_ALIGNMENT * sa
        + W_FRESHNESS * fq,
        4,
    )
    return DerivedConfidence(
        value=value,
        components={
            "delta_placement": round(dp, 4),
            "economics_quality": round(eq, 4),
            "signal_alignment": round(sa, 4),
            "freshness_quality": round(fq, 4),
        },
        reasons=[dp_reason, eq_reason, sa_reason, fq_reason],
    )
