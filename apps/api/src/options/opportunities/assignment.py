"""Phase F1 — assignment-risk classification (read-side, no new data).

Pure function over the persisted legs. Uses ONLY moneyness (short-leg
|delta|, already persisted) + days-to-expiry. All current engine structures
are DEFINED RISK (the long wing caps loss), so assignment is a pin / early-
exercise nuisance, never an uncapped exposure — callers surface that
reassurance.

NOT assessed (data unavailable): dividend / ex-dividend and earnings driven
early assignment — `corporate_action` is empty and the event calendar is
macro-only. This is stated in the UI caveat; never implied.

No migration, no generator/ranking/threshold change. Returns None when there
is no priced short leg (honest: nothing shown rather than a fabricated level).
"""

from __future__ import annotations


def assess_assignment_risk(legs: list[dict], dte: int | None) -> dict | None:
    """Classify assignment risk from the worst (highest |delta|) short leg.

    Levels:
      high     — short leg ITM (|delta| > 0.50) AND DTE <= 5  (pin / early-
                 exercise zone)
      moderate — short leg near/at the money (|delta| >= 0.30, any DTE), or
                 expiry approaching (DTE <= 7) with the short not deep OTM
      low      — short leg comfortably OTM with time remaining
    """
    shorts = [
        l for l in legs
        if str(l.get("role") or "").startswith("short_")
        and l.get("delta") is not None
    ]
    if not shorts or dte is None:
        return None

    worst = max(shorts, key=lambda l: abs(float(l["delta"])))
    ad = abs(float(worst["delta"]))
    otype = str(worst.get("option_type") or "").lower()
    side_word = "call" if otype == "call" else "put"

    if ad > 0.50 and dte <= 5:
        level = "high"
        reason = (
            f"Short {side_word} is in-the-money (Δ {ad:.2f}) with {dte} DTE "
            f"— early assignment possible near expiry."
        )
    elif ad >= 0.30:
        level = "moderate"
        reason = (
            f"Short {side_word} is near the money (Δ {ad:.2f}), {dte} DTE."
        )
    elif dte <= 7 and ad >= 0.15:
        level = "moderate"
        reason = (
            f"Expiry approaching ({dte} DTE) with the short {side_word} "
            f"not deep out-of-the-money (Δ {ad:.2f})."
        )
    else:
        level = "low"
        reason = (
            f"Short {side_word} comfortably out-of-the-money "
            f"(Δ {ad:.2f}), {dte} DTE."
        )

    return {
        "level": level,                 # low | moderate | high
        "short_delta": round(ad, 2),
        "dte": dte,
        "option_type": otype.upper() if otype else None,
        "reason": reason,
        # All v1 engine structures are defined-risk: the long wing caps loss
        # even if the short leg is assigned.
        "defined_risk": True,
    }
