"""Phase B6.2 + B7.4 — deterministic strategy candidate generator.

Input: one accepted contract observation (row from
`options_shadow_decision_log`) joined with its chain quote, the
underlying's feature_daily snapshot, and the earliest macro catalyst
event inside the DTE window (or None when no event applies).

Output: 1-3 `StrategyCandidate` dataclasses with full explainability
metadata. Generation rules are table-driven so review/audit is a
single-file read.

Locked composite-score formula (interpretation-only):

    composite = 0.40 * confidence
              + 0.20 * iv_suitability
              + 0.20 * expiry_suitability
              + 0.20 * liquidity_suitability

(Different from the Opportunities ranking formula — that one mixes
in freshness + event boost. Here we score the strategy-fit only;
the endpoint adds run-time signals on top.)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from apps.api.src.options.strategy_candidates.event_proximity import (
    CatalystEvent,
)


# Composite weights — locked. Keep in lockstep with docstring.
W_CONF      = 0.40
W_IV_FIT    = 0.20
W_EXPIRY    = 0.20
W_LIQUIDITY = 0.20


@dataclass
class ShadowObservation:
    """Subset of options_shadow_decision_log used by the generator."""
    observation_id: int
    run_date: dt.date
    underlying: str
    option_symbol: str
    expiration: dt.date
    strike: float
    option_type: str          # 'call' | 'put'
    side: str
    would_trade: bool
    liquidity_pass: bool
    spread_pass: bool
    open_interest_pass: bool
    volume_pass: bool
    greeks_pass: bool
    iv_rank_pass: bool
    risk_pass: bool
    score: float | None
    diagnostics: dict[str, Any]


@dataclass
class ChainQuote:
    """Latest chain snapshot for the option_symbol."""
    bid: float | None
    ask: float | None
    mid: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    iv: float | None
    open_interest: int | None
    volume: int | None


@dataclass
class UnderlyingFeature:
    """Subset of options_feature_daily."""
    iv_rank_252d: float | None
    atm_iv: float | None
    realized_vol_30d: float | None


@dataclass
class StrategyCandidate:
    """One emitted strategy candidate ready for persistence."""
    rule_id: str
    bias: str
    directional_view: str
    risk_profile: str
    confidence: float
    iv_suitability: float
    expiry_suitability: float
    liquidity_suitability: float
    composite_score: float
    why_emitted: str
    triggering_rule: str
    rejected_alternatives: list[dict[str, str]] = field(default_factory=list)
    strategy_fit_reason: str | None = None
    iv_fit_reason: str | None = None
    dte_fit_reason: str | None = None
    liquidity_fit_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    # Phase B7 — catalyst metadata. NULL when no event inside DTE
    # window for this underlying.
    earliest_event_date: dt.date | None = None
    earliest_event_type: str | None = None
    earliest_event_importance: str | None = None
    event_days_away: int | None = None


# ---------------------------------------------------------------------------
# Suitability scorers — pure functions, deterministic
# ---------------------------------------------------------------------------


def _iv_suitability(
    iv_rank: float | None, preference: str,
) -> tuple[float, str]:
    """Return (score 0..1, reason text)."""
    if iv_rank is None:
        return 0.5, (
            "IV-rank history building — IV suitability unconfirmed "
            "(neutral default)."
        )
    if preference == "iv_low":
        # Strategy favors low IV. Score inverts iv_rank.
        score = max(0.0, min(1.0, (50 - iv_rank) / 50)) if iv_rank < 50 else 0.0
        reason = (
            f"strategy favors low IV; iv_rank={iv_rank:.0f} "
            f"→ suitability {score:.2f}"
        )
        return score, reason
    if preference == "iv_high":
        # Strategy favors high IV. Score climbs with iv_rank.
        score = max(0.0, min(1.0, (iv_rank - 50) / 50)) if iv_rank > 50 else 0.0
        reason = (
            f"strategy favors high IV; iv_rank={iv_rank:.0f} "
            f"→ suitability {score:.2f}"
        )
        return score, reason
    # iv_neutral
    return 0.6, f"strategy is IV-neutral; iv_rank={iv_rank:.0f}"


def _expiry_suitability(
    dte: int, low: int, high: int,
) -> tuple[float, str]:
    """Triangular preference function: full score inside (low, high),
    falls linearly to 0 over a 7-day buffer either side."""
    if low <= dte <= high:
        return 1.0, (
            f"DTE {dte}d is inside the preferred window "
            f"[{low}-{high}d]"
        )
    if dte < low:
        gap = low - dte
        score = max(0.0, 1.0 - gap / 7.0)
        return score, (
            f"DTE {dte}d is {gap}d short of preferred window "
            f"[{low}-{high}d] → suitability {score:.2f}"
        )
    gap = dte - high
    score = max(0.0, 1.0 - gap / 14.0)
    return score, (
        f"DTE {dte}d is {gap}d long of preferred window "
        f"[{low}-{high}d] → suitability {score:.2f}"
    )


def _liquidity_suitability(
    obs: ShadowObservation, quote: ChainQuote,
) -> tuple[float, str]:
    """Combine gate passes + quote presence into 0..1."""
    passes = (
        (1.0 if obs.liquidity_pass else 0.0)
        + (1.0 if obs.spread_pass else 0.0)
        + (1.0 if obs.open_interest_pass else 0.0)
        + (1.0 if obs.volume_pass else 0.0)
    ) / 4.0
    reason_parts = []
    if quote.bid is not None and quote.ask is not None:
        spread = float(quote.ask) - float(quote.bid)
        reason_parts.append(f"spread ${spread:.2f}")
    if quote.open_interest is not None:
        reason_parts.append(f"OI {quote.open_interest:,}")
    if quote.volume is not None:
        reason_parts.append(f"vol {quote.volume:,}")
    return passes, (
        f"{int(passes * 4)}/4 liquidity gates pass"
        + (f" ({' · '.join(reason_parts)})" if reason_parts else "")
    )


def _composite(
    confidence: float, iv_fit: float,
    expiry_fit: float, liquidity_fit: float,
) -> float:
    return (
        W_CONF      * confidence
        + W_IV_FIT    * iv_fit
        + W_EXPIRY    * expiry_fit
        + W_LIQUIDITY * liquidity_fit
    )


# ---------------------------------------------------------------------------
# Generation rules — table-driven, deterministic
# ---------------------------------------------------------------------------


def _abs_delta(quote: ChainQuote) -> float | None:
    if quote.delta is None: return None
    try:
        return abs(float(quote.delta))
    except (TypeError, ValueError):
        return None


def _build_candidate(
    *,
    rule_id: str, bias: str, directional_view: str,
    risk_profile: str,
    base_confidence: float,
    delta_match_bonus: float,
    iv_pref: str,
    dte_window: tuple[int, int],
    why_emitted: str,
    triggering_rule: str,
    strategy_fit_reason: str,
    obs: ShadowObservation,
    quote: ChainQuote,
    feat: UnderlyingFeature,
    catalyst: CatalystEvent | None,
    extra_diagnostics: dict[str, Any] | None = None,
) -> StrategyCandidate:
    """Compose one StrategyCandidate from the standard score pipeline."""
    dte = (obs.expiration - obs.run_date).days
    iv_fit, iv_reason = _iv_suitability(feat.iv_rank_252d, iv_pref)
    expiry_fit, dte_reason = _expiry_suitability(dte, *dte_window)
    liq_fit, liq_reason = _liquidity_suitability(obs, quote)
    confidence = min(1.0, base_confidence + delta_match_bonus)
    composite = _composite(confidence, iv_fit, expiry_fit, liq_fit)

    # Append catalyst context to the IV-fit reason when a high-impact
    # event sits inside the DTE window. Operator instantly sees both
    # the IV-rank read AND the catalyst causing the premium env.
    if catalyst is not None and catalyst.importance == "high":
        iv_reason = (
            f"{iv_reason} · "
            f"{catalyst.event_type} on {catalyst.event_date.isoformat()} "
            f"(+{catalyst.days_away}d) likely elevates IV into the event."
        )

    return StrategyCandidate(
        rule_id=rule_id,
        bias=bias,
        directional_view=directional_view,
        risk_profile=risk_profile,
        confidence=confidence,
        iv_suitability=iv_fit,
        expiry_suitability=expiry_fit,
        liquidity_suitability=liq_fit,
        composite_score=composite,
        why_emitted=why_emitted,
        triggering_rule=triggering_rule,
        strategy_fit_reason=strategy_fit_reason,
        iv_fit_reason=iv_reason,
        dte_fit_reason=dte_reason,
        liquidity_fit_reason=liq_reason,
        diagnostics={
            "iv_rank_252d": feat.iv_rank_252d,
            "atm_iv": feat.atm_iv,
            "delta": quote.delta,
            "dte": dte,
            "catalyst_title":
                catalyst.title if catalyst else None,
            "catalyst_explanation":
                catalyst.explanation if catalyst else None,
            **(extra_diagnostics or {}),
        },
        earliest_event_date=catalyst.event_date if catalyst else None,
        earliest_event_type=catalyst.event_type if catalyst else None,
        earliest_event_importance=catalyst.importance if catalyst else None,
        event_days_away=catalyst.days_away if catalyst else None,
    )


# ---------------------------------------------------------------------------
# Credit / Iron-Condor mode (Opt-B) — engine-aligned structures
#
# Emits ONLY the three paper-engine-supported defined-risk structures:
#   SHORT_PUT_CREDIT_SPREAD  (bullish)  — sell OTM put spread, 1-strike wide
#   SHORT_CALL_CREDIT_SPREAD (bearish)  — sell OTM call spread, 1-strike wide
#   IRON_CONDOR              (neutral)  — both wings, underlying-level pass
#
# Directional bias is PASSED IN from the underlying's recommendation/signal
# (per approved decision 3) — never inferred from contract type. Width is
# fixed at the next listed strike (1-strike-wide, decision 1) and recorded
# in diagnostics. IV preference is iv_high; when iv_rank is NULL the shared
# _iv_suitability returns a neutral 0.5 with explicit "IV-rank history
# building" copy (decision 4) — no fabricated IV edge.
# ---------------------------------------------------------------------------

# Short-leg delta band for a credit spread's sold strike (~0.30 target).
CREDIT_SHORT_DELTA_LO = 0.20
CREDIT_SHORT_DELTA_HI = 0.35

# v1 width: next listed strike → 1-strike-wide defined-risk spread.
CREDIT_WIDTH_STRIKES = 1


def _iv_building_note(feat: UnderlyingFeature) -> str:
    if feat.iv_rank_252d is None:
        return (" IV-rank history building — IV suitability unconfirmed; "
                "no IV edge assumed.")
    return ""


def _generate_credit(
    *,
    obs: ShadowObservation,
    quote: ChainQuote,
    feat: UnderlyingFeature,
    catalyst: CatalystEvent | None,
    bias: str,
) -> list[StrategyCandidate]:
    """Per-contract credit-spread emission, engine-aligned.

    bullish bias + OTM put short-leg  → SHORT_PUT_CREDIT_SPREAD
    bearish bias + OTM call short-leg → SHORT_CALL_CREDIT_SPREAD
    Anything else → [] (IRON_CONDOR is composed at the underlying level
    in the service layer — see build_iron_condor).
    """
    abs_delta = _abs_delta(quote)
    option_type = obs.option_type.lower()
    in_short_zone = (
        abs_delta is not None
        and CREDIT_SHORT_DELTA_LO <= abs_delta <= CREDIT_SHORT_DELTA_HI
    )
    note = _iv_building_note(feat)
    extra = {
        "width_strikes": CREDIT_WIDTH_STRIKES,
        "short_leg_delta": quote.delta,
        "bias_source": "recommendation_signal",
    }

    if bias == "bullish" and option_type == "put" and in_short_zone:
        return [_build_candidate(
            rule_id="SHORT_PUT_CREDIT_SPREAD",
            bias="bullish",
            directional_view=(
                "Profits if the underlying holds above the short put; "
                "defined risk via the 1-strike-wide long put."
            ),
            risk_profile="defined",
            base_confidence=0.60, delta_match_bonus=0.10,
            iv_pref="iv_high",
            dte_window=(30, 45),
            why_emitted=(
                "Bullish recommendation bias → sell an OTM put credit "
                "spread (1-strike wide)." + note
            ),
            triggering_rule="rec_bullish__short_put_credit_spread",
            strategy_fit_reason=(
                "Bullish bias expressed as defined-risk premium "
                "collection; max loss = width − net credit." + note
            ),
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            extra_diagnostics=extra,
        )]

    if bias == "bearish" and option_type == "call" and in_short_zone:
        return [_build_candidate(
            rule_id="SHORT_CALL_CREDIT_SPREAD",
            bias="bearish",
            directional_view=(
                "Profits if the underlying stays below the short call; "
                "defined risk via the 1-strike-wide long call."
            ),
            risk_profile="defined",
            base_confidence=0.60, delta_match_bonus=0.10,
            iv_pref="iv_high",
            dte_window=(30, 45),
            why_emitted=(
                "Bearish recommendation bias → sell an OTM call credit "
                "spread (1-strike wide)." + note
            ),
            triggering_rule="rec_bearish__short_call_credit_spread",
            strategy_fit_reason=(
                "Bearish bias expressed as defined-risk premium "
                "collection; max loss = width − net credit." + note
            ),
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            extra_diagnostics=extra,
        )]

    return []


def build_iron_condor(
    *,
    obs: ShadowObservation,
    quote: ChainQuote,
    feat: UnderlyingFeature,
    catalyst: CatalystEvent | None,
    has_directional_signal: bool,
) -> StrategyCandidate:
    """Underlying-level IRON_CONDOR composition (decision 2).

    Emitted once per neutral / no-signal underlying, anchored on a
    representative would-trade observation. Direction-agnostic two-sided
    credit; 1-strike-wide wings. `has_directional_signal=False` means the
    underlying has no recommendation bias (e.g. GLD/TLT) — messaging is
    explicit about that (decision: IC-only for no-bias underlyings).
    """
    note = _iv_building_note(feat)
    if has_directional_signal:
        reason = "Neutral/hold recommendation — range-bound Iron Condor."
    else:
        reason = (
            "No directional recommendation signal for this underlying — "
            "emitting a neutral, range-bound Iron Condor (direction-"
            "agnostic)."
        )
    return _build_candidate(
        rule_id="IRON_CONDOR",
        bias="neutral",
        directional_view=(
            "Profits if the underlying stays within the short strikes; "
            "defined risk via 1-strike-wide wings."
        ),
        risk_profile="defined",
        base_confidence=0.45, delta_match_bonus=0.05,
        iv_pref="iv_high",
        dte_window=(30, 50),
        why_emitted=reason + note,
        triggering_rule="underlying_level__iron_condor",
        strategy_fit_reason=(
            "Two-sided defined-risk credit; direction-agnostic. "
            "Max loss = wing width − net credit." + note
        ),
        obs=obs, quote=quote, feat=feat, catalyst=catalyst,
        extra_diagnostics={
            "width_strikes": CREDIT_WIDTH_STRIKES,
            "structure_pass": "underlying_level",
            "has_directional_signal": has_directional_signal,
        },
    )


def generate(
    *,
    obs: ShadowObservation,
    quote: ChainQuote,
    feat: UnderlyingFeature,
    catalyst: CatalystEvent | None = None,
    structures: str = "directional",
    bias: str | None = None,
) -> list[StrategyCandidate]:
    """Generate 1-3 strategy candidates for one accepted contract.

    Deterministic: same inputs → same outputs (no randomness, no
    time-dependence beyond obs.run_date which is also an input).

    Skip emission when obs.would_trade is False — interpretation is
    only valuable for contracts that passed the engine's filter chain.

    `structures` selects the output taxonomy (Opt-B):
      * "directional" (default) — legacy debit/long structures.
      * "credit" — engine-aligned SHORT_*_CREDIT_SPREAD; IRON_CONDOR is
        composed separately at the underlying level (build_iron_condor).
        `bias` (bullish|bearish|neutral) comes from the underlying's
        recommendation signal and is REQUIRED in credit mode.

    `catalyst` is the earliest in-DTE-window macro event for the
    underlying (or None). When a high-importance event falls inside
    the DTE window, the directional path may emit an additional
    event-bias adjunct (LONG_STRADDLE).
    """
    if not obs.would_trade:
        return []

    _mode = (structures or "directional").lower()
    if _mode == "credit":
        return _generate_credit(
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            bias=(bias or "neutral").lower(),
        )

    candidates: list[StrategyCandidate] = []
    rejected: list[dict[str, str]] = []

    iv_rank = feat.iv_rank_252d
    abs_delta = _abs_delta(quote)
    dte = (obs.expiration - obs.run_date).days
    option_type = obs.option_type.lower()

    # IV-rank classification for IV-conditional rules.
    iv_low = iv_rank is None or iv_rank < 50
    iv_high = iv_rank is not None and iv_rank >= 50

    # Delta-zone classification.
    if abs_delta is None:
        delta_zone = "unknown"
    elif abs_delta >= 0.50:
        delta_zone = "directional"      # ITM or near-the-money directional
    elif abs_delta >= 0.20:
        delta_zone = "otm_balanced"     # OTM with meaningful exposure
    else:
        delta_zone = "deep_otm"

    # ------------------------------------------------------------------
    # CALL contracts
    # ------------------------------------------------------------------
    if option_type == "call":
        if delta_zone == "directional" and iv_low:
            # Long-call play (debit). Long delta on a cheap-premium env.
            candidates.append(_build_candidate(
                rule_id="LONG_CALL",
                bias="bullish",
                directional_view="Profits when underlying rises past breakeven.",
                risk_profile="defined",
                base_confidence=0.65, delta_match_bonus=0.15,
                iv_pref="iv_low",
                dte_window=(20, 50),
                why_emitted="Directional call with cheap premium "
                            "supports a debit long-call.",
                triggering_rule="call_long_low_iv",
                strategy_fit_reason="Long delta on the call combined "
                                    "with low IV makes the long debit cheap "
                                    "relative to historical premium.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            # Defined-risk variant: spread out the cost.
            candidates.append(_build_candidate(
                rule_id="BULL_CALL_SPREAD",
                bias="bullish",
                directional_view="Modest upside; defined max loss.",
                risk_profile="defined",
                base_confidence=0.55, delta_match_bonus=0.10,
                iv_pref="iv_low",
                dte_window=(25, 60),
                why_emitted="Bullish bias with defined-risk debit spread "
                            "caps the cost of expressing the view.",
                triggering_rule="call_long_low_iv__spread_variant",
                strategy_fit_reason="Selling the further-OTM call funds part "
                                    "of the long; same bullish exposure, "
                                    "lower max loss.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            rejected.append({
                "rule_id": "BULL_PUT_SPREAD",
                "reason": "IV-rank is low; credit-spread premium is too thin "
                          "for an income variant.",
            })
        elif delta_zone == "otm_balanced" and iv_high:
            # Credit-spread (sell puts) on bullish bias with rich premium.
            candidates.append(_build_candidate(
                rule_id="BULL_PUT_SPREAD",
                bias="bullish",
                directional_view="Income with bullish bias; sells OTM put spread.",
                risk_profile="defined",
                base_confidence=0.60, delta_match_bonus=0.15,
                iv_pref="iv_high",
                dte_window=(30, 45),
                why_emitted="Rich premium environment + bullish call "
                            "delta suggests a credit put spread.",
                triggering_rule="call_otm_high_iv__credit_put_spread",
                strategy_fit_reason="Bullish bias expressed via "
                                    "premium-collection structure works "
                                    "in elevated IV.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            candidates.append(_build_candidate(
                rule_id="BULL_CALL_SPREAD",
                bias="bullish",
                directional_view="Modest upside; defined max loss.",
                risk_profile="defined",
                base_confidence=0.50, delta_match_bonus=0.10,
                iv_pref="iv_low",       # imperfect fit; logged
                dte_window=(25, 60),
                why_emitted="Alternative directional expression of the "
                            "bullish bias when IV is elevated.",
                triggering_rule="call_otm_high_iv__spread_variant",
                strategy_fit_reason="Cheaper-than-long-call directional play. "
                                    "Defined max loss preserves discipline "
                                    "while premium is rich.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            rejected.append({
                "rule_id": "LONG_CALL",
                "reason": "IV-rank is elevated; naked long-call premium "
                          "is expensive relative to history.",
            })
        elif iv_high and delta_zone != "unknown":
            # Neutral/income adjunct on any call when IV is rich.
            candidates.append(_build_candidate(
                rule_id="IRON_CONDOR",
                bias="neutral",
                directional_view="Profits if underlying stays in a range.",
                risk_profile="defined",
                base_confidence=0.45,
                delta_match_bonus=0.10,
                iv_pref="iv_high",
                dte_window=(30, 50),
                why_emitted="High IV rank favors range-bound credit "
                            "structures; an Iron Condor monetizes the "
                            "elevated premium environment.",
                triggering_rule="any_call_high_iv__neutral_adjunct",
                strategy_fit_reason="Two-sided credit spread. Underlying "
                                    "direction matters less than vol "
                                    "contraction.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
        else:
            # Fallback: emit BULL_CALL_SPREAD at low confidence so call
            # contracts always produce at least one bullish-family
            # candidate. Future rules can refine this.
            candidates.append(_build_candidate(
                rule_id="BULL_CALL_SPREAD",
                bias="bullish",
                directional_view="Modest upside; defined max loss.",
                risk_profile="defined",
                base_confidence=0.40, delta_match_bonus=0.05,
                iv_pref="iv_low",
                dte_window=(25, 60),
                why_emitted="Default bullish interpretation for a call "
                            "contract that does not match a specialized "
                            "rule.",
                triggering_rule="call_default_fallback",
                strategy_fit_reason="Defined-risk debit spread is the "
                                    "lowest-context-required bullish "
                                    "expression of a call signal.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))

    # ------------------------------------------------------------------
    # PUT contracts (mirror)
    # ------------------------------------------------------------------
    elif option_type == "put":
        if delta_zone == "directional" and iv_low:
            candidates.append(_build_candidate(
                rule_id="LONG_PUT",
                bias="bearish",
                directional_view="Profits when underlying falls past breakeven.",
                risk_profile="defined",
                base_confidence=0.65, delta_match_bonus=0.15,
                iv_pref="iv_low",
                dte_window=(20, 50),
                why_emitted="Directional put with cheap premium "
                            "supports a debit long-put.",
                triggering_rule="put_long_low_iv",
                strategy_fit_reason="Long-put delta combined with low IV "
                                    "yields cheap downside exposure.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            candidates.append(_build_candidate(
                rule_id="BEAR_PUT_SPREAD",
                bias="bearish",
                directional_view="Modest downside; defined max loss.",
                risk_profile="defined",
                base_confidence=0.55, delta_match_bonus=0.10,
                iv_pref="iv_low",
                dte_window=(25, 60),
                why_emitted="Bearish bias with defined-risk debit spread "
                            "reduces cost of expressing the view.",
                triggering_rule="put_long_low_iv__spread_variant",
                strategy_fit_reason="Selling the further-OTM put funds "
                                    "part of the long; same bearish "
                                    "exposure, lower max loss.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            rejected.append({
                "rule_id": "BEAR_CALL_SPREAD",
                "reason": "IV-rank is low; credit-spread premium is too thin.",
            })
        elif delta_zone == "otm_balanced" and iv_high:
            candidates.append(_build_candidate(
                rule_id="BEAR_CALL_SPREAD",
                bias="bearish",
                directional_view="Income with bearish bias; sells OTM call spread.",
                risk_profile="defined",
                base_confidence=0.60, delta_match_bonus=0.15,
                iv_pref="iv_high",
                dte_window=(30, 45),
                why_emitted="Rich premium environment + bearish put "
                            "delta suggests a credit call spread.",
                triggering_rule="put_otm_high_iv__credit_call_spread",
                strategy_fit_reason="Bearish bias expressed via "
                                    "premium-collection structure works "
                                    "in elevated IV.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            candidates.append(_build_candidate(
                rule_id="BEAR_PUT_SPREAD",
                bias="bearish",
                directional_view="Modest downside; defined max loss.",
                risk_profile="defined",
                base_confidence=0.50, delta_match_bonus=0.10,
                iv_pref="iv_low",
                dte_window=(25, 60),
                why_emitted="Alternative directional expression of the "
                            "bearish bias when IV is elevated.",
                triggering_rule="put_otm_high_iv__spread_variant",
                strategy_fit_reason="Defined-risk debit spread keeps "
                                    "the bearish view alive without "
                                    "shorting open-ended risk.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
            rejected.append({
                "rule_id": "LONG_PUT",
                "reason": "IV-rank is elevated; naked long-put premium "
                          "is expensive relative to history.",
            })
        elif iv_high and delta_zone != "unknown":
            candidates.append(_build_candidate(
                rule_id="IRON_CONDOR",
                bias="neutral",
                directional_view="Profits if underlying stays in a range.",
                risk_profile="defined",
                base_confidence=0.45, delta_match_bonus=0.10,
                iv_pref="iv_high",
                dte_window=(30, 50),
                why_emitted="High IV rank favors range-bound credit "
                            "structures; an Iron Condor monetizes the "
                            "elevated premium environment.",
                triggering_rule="any_put_high_iv__neutral_adjunct",
                strategy_fit_reason="Two-sided credit spread; underlying "
                                    "direction matters less than vol "
                                    "contraction.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))
        else:
            # Fallback for unmatched puts.
            candidates.append(_build_candidate(
                rule_id="BEAR_PUT_SPREAD",
                bias="bearish",
                directional_view="Modest downside; defined max loss.",
                risk_profile="defined",
                base_confidence=0.40, delta_match_bonus=0.05,
                iv_pref="iv_low",
                dte_window=(25, 60),
                why_emitted="Default bearish interpretation for a put "
                            "contract that does not match a specialized "
                            "rule.",
                triggering_rule="put_default_fallback",
                strategy_fit_reason="Defined-risk debit spread is the "
                                    "lowest-context-required bearish "
                                    "expression of a put signal.",
                obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            ))

    # ------------------------------------------------------------------
    # Event-driven adjunct — Phase B7.
    # Two emission paths:
    #   1. Confirmed catalyst path: market_event_calendar shows a
    #      high-importance macro event inside the DTE window. Generator
    #      emits a LONG_STRADDLE candidate explicitly grounded in the
    #      named event. This is the strategist-grade event play.
    #   2. Inferred-catalyst path (legacy B6 heuristic): short DTE +
    #      elevated IV but NO calendar event. Generator emits a
    #      LONG_STRADDLE candidate flagged as "catalyst inferred,
    #      operator must confirm". Lower confidence than the named-event
    #      path.
    # ------------------------------------------------------------------
    if catalyst is not None and catalyst.importance == "high" \
            and 0 < catalyst.days_away <= dte and len(candidates) < 3:
        # Confirmed-catalyst path.
        candidates.append(_build_candidate(
            rule_id="LONG_STRADDLE",
            bias="event",
            directional_view="Profits on a large move in either direction.",
            risk_profile="defined",
            base_confidence=0.55, delta_match_bonus=0.10,
            iv_pref="iv_low",   # ideal is low IV; calendar event may be priced in
            dte_window=(7, max(21, catalyst.days_away + 7)),
            why_emitted=(
                f"{catalyst.event_type} on "
                f"{catalyst.event_date.isoformat()} sits inside the "
                f"option's DTE window (+{catalyst.days_away}d). "
                "Long Straddle prices the binary catalyst move."
            ),
            triggering_rule="named_catalyst__event_straddle",
            strategy_fit_reason=(
                f"Direction-agnostic play around a named "
                f"{catalyst.event_type}. "
                "Defined max loss = combined premium paid; profits "
                "scale with realized move size."
            ),
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
        ))
    elif catalyst is None and 0 < dte <= 14 and iv_high \
            and len(candidates) < 3:
        # Inferred-catalyst path (no named event in calendar).
        candidates.append(_build_candidate(
            rule_id="LONG_STRADDLE",
            bias="event",
            directional_view="Profits on a large move in either direction.",
            risk_profile="defined",
            base_confidence=0.35, delta_match_bonus=0.0,
            iv_pref="iv_low",
            dte_window=(7, 21),
            why_emitted=(
                "Short DTE + elevated IV suggests an imminent "
                "catalyst not on the macro calendar. Long Straddle "
                "prices a binary move — operator must confirm catalyst."
            ),
            triggering_rule="short_dte_high_iv__inferred_catalyst",
            strategy_fit_reason="Pure-volatility play; no named event "
                                "in market_event_calendar. Lower "
                                "confidence than a calendar-confirmed setup.",
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
        ))

    # Carry the rejected_alternatives list onto every emission so the
    # UI/educational drawer can show "alternatives considered" per card.
    for c in candidates:
        c.rejected_alternatives = list(rejected)

    # Bounded fan-out: 1-3 directional candidates per accepted contract.
    out = candidates[:3]

    # Hybrid "both" mode (Phase 2) — also emit the engine-aligned credit
    # structure for this contract so the executable lane is populated
    # alongside the research lane. Additive: directional output is
    # unchanged; credit is appended. IRON_CONDOR is composed per-underlying
    # in the service layer (build_iron_condor), not here.
    if _mode == "both":
        out = out + _generate_credit(
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            bias=(bias or "neutral").lower(),
        )
    return out
