"""Frozen v1 deterministic scoring model (Phase 11H).

Pure-fn module. NO ML. NO learned weights. NO optimisation. Stdlib +
Decimal only. Every numeric weight in this file is a frozen module
constant — operator-locked at v1.

Score = clamp(
            liquidity_pts + risk_reward_pts + vol_pts + structure_pts
            + total_penalties,
            lo=0, hi=100,
        )

Rationale for explicit weighting:
  * Liquidity quality reflects whether the engine could actually
    transact paper-side without slippage assumptions falling apart.
  * Risk/reward quality reflects defined-risk math the engine
    already enforces (verticals + iron condors only).
  * Volatility context reflects how rich the market regime was when
    the observation was made (high IV rank / VRP > 0 favors short
    premium; low IV rank doesn't).
  * Structure quality reflects how well the candidate fits the v1
    rule (DTE band, delta band, protective long, same expiry).
  * Penalties subtract from the total when model limitations or
    missing data make the recorded outcome less trustworthy.

NEVER reads from any non-`options_*` table.
NEVER imports V2 / equity / governance / paper engine mutation
modules.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from apps.api.src.options.data.liquidity_filter import (
    MAX_BID_ASK_SPREAD_DOLLARS,
    MIN_OPEN_INTEREST,
)
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.observatory.rules import (
    DTE_MAX_DAYS,
    DTE_MIN_DAYS,
    SHORT_DELTA_MAX_ABS,
    SHORT_DELTA_MIN_ABS,
)
from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


# ---------------------------------------------------------------------------
# Frozen weights — DO NOT change without a revision-history doc update.
# ---------------------------------------------------------------------------

WEIGHT_LIQUIDITY        = 25
WEIGHT_RISK_REWARD      = 25
WEIGHT_VOL_CONTEXT      = 20
WEIGHT_STRUCTURE        = 20
PENALTY_CAP             = 20      # absolute value cap on total penalties

# Per-penalty point values (always negative).
PENALTY_PIN_RISK                      = -8
PENALTY_ASSIGNMENT_SIMPLIFIED_EXIT    = -8
PENALTY_MISSING_SETTLEMENT            = -10
PENALTY_MISSING_GREEKS                = -3
PENALTY_INSUFFICIENT_REALIZED_VOL     = -3
PENALTY_MISSING_IV                    = -3
PENALTY_NAIVE_GEX                     = -2
PENALTY_INSUFFICIENT_IV_HISTORY       = -3

SCORE_MODEL_VERSION = "v1.frozen"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComponentScore:
    """One scoring component + plain-English explanation."""
    component: str           # liquidity / risk_reward / vol_context / structure
    weight_max: int
    score: int
    explanation: str


@dataclass(frozen=True)
class PenaltyEntry:
    code: str                # FLAG_* / token
    label: str               # operator-readable name
    points: int              # negative
    reason: str


@dataclass(frozen=True)
class EvaluationScore:
    rule_id: str
    underlying: str
    as_of_date: str
    qualified: bool
    total_score: int
    components: tuple[ComponentScore, ...]
    penalties: tuple[PenaltyEntry, ...]
    flags: tuple[str, ...]
    inputs: dict           # frozen formula inputs for audit
    model_version: str = SCORE_MODEL_VERSION


# ---------------------------------------------------------------------------
# Scoring inputs the service layer builds + passes in
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringInputs:
    """All deterministic inputs needed to compute one score.

    Service layer constructs this from chain rows + feature row + rule
    evaluation + flag set. Pure-fn `compute_score` consumes it.
    """
    rule_id: str
    underlying: str
    as_of_date: datetime.date
    qualified: bool
    candidate: dict | None       # selected legs, when rule found a shape
    accepted_quotes: tuple[OptionChainQuote, ...]
    feature_row: dict | None     # latest feature row for symbol or None
    flags: tuple[str, ...]       # surfaced flag tokens (engine + features)


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------

def _component_liquidity(inp: ScoringInputs) -> ComponentScore:
    """Up to 25 pts split across spread / OI / volume / quote-age."""
    if inp.candidate is None or not inp.accepted_quotes:
        return ComponentScore(
            component="liquidity", weight_max=WEIGHT_LIQUIDITY,
            score=0,
            explanation=(
                "No selected candidate or no accepted quotes — "
                "liquidity unmeasurable."
            ),
        )
    legs = _legs_for_candidate(inp)
    if not legs:
        return ComponentScore(
            component="liquidity", weight_max=WEIGHT_LIQUIDITY,
            score=0,
            explanation=(
                "Candidate references symbols not present in accepted chain."
            ),
        )

    # Spread quality (up to 8 pts): 1.0 at $0.00 spread, 0 at $0.10 cap
    spreads = [
        float(q.ask - q.bid) for q in legs
        if q.ask is not None and q.bid is not None
    ]
    spread_avg = sum(spreads) / len(spreads) if spreads else 0.0
    spread_pts = max(
        0,
        round(8 * (1 - spread_avg / float(MAX_BID_ASK_SPREAD_DOLLARS))),
    )

    # Open interest (up to 7 pts): 1000 OI = 4 pts, 5000+ = 7 pts
    ois = [q.open_interest for q in legs if q.open_interest is not None]
    oi_min = min(ois) if ois else 0
    oi_pts = (
        7 if oi_min >= 5000
        else 5 if oi_min >= 2000
        else 4 if oi_min >= 1000
        else 2 if oi_min >= MIN_OPEN_INTEREST
        else 0
    )

    # Volume (up to 5 pts): require >0 on every leg
    vols = [q.volume for q in legs if q.volume is not None]
    vol_min = min(vols) if vols else 0
    vol_pts = (
        5 if vol_min >= 200
        else 3 if vol_min >= 50
        else 1 if vol_min > 0
        else 0
    )

    # Quote freshness (up to 5 pts): newer is better
    ages = [q.quote_age_seconds for q in legs]
    age_max = max(ages) if ages else 999
    age_pts = (
        5 if age_max <= 5
        else 3 if age_max <= 20
        else 1 if age_max <= 60
        else 0
    )

    total = spread_pts + oi_pts + vol_pts + age_pts
    return ComponentScore(
        component="liquidity", weight_max=WEIGHT_LIQUIDITY,
        score=min(total, WEIGHT_LIQUIDITY),
        explanation=(
            f"spread_avg=${spread_avg:.2f} → {spread_pts}/8 · "
            f"min_oi={oi_min} → {oi_pts}/7 · "
            f"min_vol={vol_min} → {vol_pts}/5 · "
            f"max_age={age_max}s → {age_pts}/5"
        ),
    )


def _component_risk_reward(inp: ScoringInputs) -> ComponentScore:
    """Up to 25 pts split across credit / max-loss / RR ratio / width."""
    if inp.candidate is None:
        return ComponentScore(
            component="risk_reward", weight_max=WEIGHT_RISK_REWARD,
            score=0,
            explanation="No candidate selected — risk/reward unmeasurable.",
        )

    width, credit_per_contract = _candidate_geometry(inp)
    if width is None or credit_per_contract is None:
        return ComponentScore(
            component="risk_reward", weight_max=WEIGHT_RISK_REWARD,
            score=0,
            explanation=(
                "Could not derive width / credit from candidate legs."
            ),
        )

    # Credit (up to 7 pts): higher absolute credit = higher score
    credit_pts = (
        7 if credit_per_contract >= Decimal("1.50")
        else 5 if credit_per_contract >= Decimal("0.80")
        else 3 if credit_per_contract >= Decimal("0.40")
        else 1 if credit_per_contract > 0
        else 0
    )

    # Max loss (up to 6 pts): smaller is better; computed in dollars
    # per 1-contract unit so v1 universe is comparable.
    max_loss = (width - credit_per_contract) * Decimal("100")
    max_loss_pts = (
        6 if max_loss <= Decimal("250")
        else 4 if max_loss <= Decimal("500")
        else 2 if max_loss <= Decimal("1000")
        else 0
    )

    # Reward / risk (up to 7 pts): credit / max_loss_per_contract
    rr_ratio = (
        credit_per_contract / (width - credit_per_contract)
        if (width - credit_per_contract) > 0
        else Decimal("0")
    )
    rr_pts = (
        7 if rr_ratio >= Decimal("0.40")
        else 5 if rr_ratio >= Decimal("0.25")
        else 3 if rr_ratio >= Decimal("0.15")
        else 1 if rr_ratio > 0
        else 0
    )

    # Width (up to 5 pts): wider defined-risk = more flexibility
    width_pts = (
        5 if width >= Decimal("5")
        else 3 if width >= Decimal("2.5")
        else 1 if width > 0
        else 0
    )

    total = credit_pts + max_loss_pts + rr_pts + width_pts
    return ComponentScore(
        component="risk_reward", weight_max=WEIGHT_RISK_REWARD,
        score=min(total, WEIGHT_RISK_REWARD),
        explanation=(
            f"credit/contract=${credit_per_contract} → {credit_pts}/7 · "
            f"max_loss=${max_loss} → {max_loss_pts}/6 · "
            f"R/R={rr_ratio:.3f} → {rr_pts}/7 · "
            f"width=${width} → {width_pts}/5"
        ),
    )


def _component_vol_context(inp: ScoringInputs) -> ComponentScore:
    """Up to 20 pts split across IV rank / IV percentile / VRP / RV."""
    f = inp.feature_row or {}
    if not f:
        return ComponentScore(
            component="vol_context", weight_max=WEIGHT_VOL_CONTEXT,
            score=0,
            explanation="No feature row — volatility context unavailable.",
        )

    # IV rank (up to 6 pts): higher = more "rich" environment for short prem
    ivr = _to_dec(f.get("iv_rank_252d"))
    ivr_pts = (
        6 if ivr is not None and ivr >= Decimal("0.50")
        else 4 if ivr is not None and ivr >= Decimal("0.30")
        else 2 if ivr is not None and ivr >= Decimal("0.15")
        else 0
    )

    # IV percentile (up to 6 pts)
    ivp = _to_dec(f.get("iv_percentile_252d"))
    ivp_pts = (
        6 if ivp is not None and ivp >= Decimal("0.50")
        else 4 if ivp is not None and ivp >= Decimal("0.30")
        else 2 if ivp is not None and ivp >= Decimal("0.15")
        else 0
    )

    # VRP availability (up to 4 pts)
    vrp = _to_dec(f.get("vrp_30d"))
    vrp_pts = (
        4 if vrp is not None and vrp > 0
        else 2 if vrp is not None
        else 0
    )

    # Realized vol availability (up to 4 pts)
    rv = _to_dec(f.get("realized_vol_20d"))
    rv_pts = 4 if rv is not None else 0

    total = ivr_pts + ivp_pts + vrp_pts + rv_pts
    return ComponentScore(
        component="vol_context", weight_max=WEIGHT_VOL_CONTEXT,
        score=min(total, WEIGHT_VOL_CONTEXT),
        explanation=(
            f"iv_rank={_disp(ivr)} → {ivr_pts}/6 · "
            f"iv_percentile={_disp(ivp)} → {ivp_pts}/6 · "
            f"vrp_30d={_disp(vrp)} → {vrp_pts}/4 · "
            f"realized_vol_20d={_disp(rv)} → {rv_pts}/4"
        ),
    )


def _component_structure(inp: ScoringInputs) -> ComponentScore:
    """Up to 20 pts: DTE band / short-leg delta / long-leg protection / same expiry-qty."""
    if inp.candidate is None:
        return ComponentScore(
            component="structure", weight_max=WEIGHT_STRUCTURE,
            score=0,
            explanation=(
                "No candidate — structure quality unmeasurable. "
                "Rule eligibility evaluator did not select legs."
            ),
        )

    # DTE inside band (5 pts)
    dte = _candidate_dte(inp)
    dte_pts = 5 if (dte is not None and DTE_MIN_DAYS <= dte <= DTE_MAX_DAYS) else 0

    # Short-leg delta inside band (5 pts)
    short_delta = _candidate_short_delta(inp)
    delta_pts = (
        5 if short_delta is not None
        and SHORT_DELTA_MIN_ABS <= abs(short_delta) <= SHORT_DELTA_MAX_ABS
        else 0
    )

    # Long-leg protection present (5 pts) — if candidate has long_strike or
    # iron condor wings, give the points.
    cand = inp.candidate
    has_long = bool(
        cand.get("long_strike")
        or (
            cand.get("put_wing") and cand.get("call_wing")
            and cand["put_wing"].get("long_strike")
            and cand["call_wing"].get("long_strike")
        )
    )
    long_pts = 5 if has_long else 0

    # Same expiry / same qty enforcement: rule validator already requires
    # this. We mirror with 5 pts when chain has consistent legs.
    same_pts = 5 if inp.qualified else 0

    total = dte_pts + delta_pts + long_pts + same_pts
    return ComponentScore(
        component="structure", weight_max=WEIGHT_STRUCTURE,
        score=min(total, WEIGHT_STRUCTURE),
        explanation=(
            f"dte={dte} → {dte_pts}/5 · "
            f"short_delta={short_delta} → {delta_pts}/5 · "
            f"long_protection={has_long} → {long_pts}/5 · "
            f"same_expiry_qty={inp.qualified} → {same_pts}/5"
        ),
    )


# ---------------------------------------------------------------------------
# Penalty assembler
# ---------------------------------------------------------------------------

def _penalties(inp: ScoringInputs) -> list[PenaltyEntry]:
    """Aggregate all applicable penalties from flags + missing data.
    Capped collectively at PENALTY_CAP (subtracted from total)."""
    out: list[PenaltyEntry] = []
    flag_set = set(inp.flags)
    feat_flags = set((inp.feature_row or {}).get("data_quality_flags", []) or [])

    if FLAG_PIN_RISK_UNCERTAIN_OUTCOME in flag_set:
        out.append(PenaltyEntry(
            code=FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
            label="Pin risk — outcome uncertain",
            points=PENALTY_PIN_RISK,
            reason=(
                "An expiration event for this underlying landed within "
                "$0.05 of a strike; the recorded payoff is a model "
                "approximation only."
            ),
        ))
    if FLAG_ASSIGNMENT_SIMPLIFIED_EXIT in flag_set:
        out.append(PenaltyEntry(
            code=FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
            label="Assignment — simplified exit model",
            points=PENALTY_ASSIGNMENT_SIMPLIFIED_EXIT,
            reason=(
                "v1 paper engine treats assignment as terminal at "
                "intrinsic value; no synthetic equity position is "
                "created."
            ),
        ))
    if FLAG_MISSING_SETTLEMENT in flag_set:
        out.append(PenaltyEntry(
            code=FLAG_MISSING_SETTLEMENT,
            label="Missing settlement — expiry unresolved",
            points=PENALTY_MISSING_SETTLEMENT,
            reason="An expiration event was missing settlement price.",
        ))

    # Missing Greeks across selected legs
    if inp.candidate is not None and _has_missing_greeks(inp):
        out.append(PenaltyEntry(
            code="MISSING_GREEKS",
            label="Missing Greeks",
            points=PENALTY_MISSING_GREEKS,
            reason="One or more selected legs lack delta/gamma/theta/vega.",
        ))

    if "INSUFFICIENT_VOLUME_HISTORY" in feat_flags:
        out.append(PenaltyEntry(
            code="INSUFFICIENT_VOLUME_HISTORY",
            label="Insufficient volume history",
            points=PENALTY_INSUFFICIENT_REALIZED_VOL,
            reason=(
                "Feature engine flagged insufficient trailing volume "
                "history; unusual-volume z-scores unavailable."
            ),
        ))
    if "NO_PRICE_HISTORY" in feat_flags:
        out.append(PenaltyEntry(
            code="NO_PRICE_HISTORY",
            label="Insufficient realized vol",
            points=PENALTY_INSUFFICIENT_REALIZED_VOL,
            reason=(
                "Feature engine flagged no price history; "
                "realized_vol_20d + vrp_30d unavailable."
            ),
        ))
    if "INSUFFICIENT_IV_HISTORY" in feat_flags:
        out.append(PenaltyEntry(
            code="INSUFFICIENT_IV_HISTORY",
            label="Insufficient IV history",
            points=PENALTY_INSUFFICIENT_IV_HISTORY,
            reason="iv_rank_252d / iv_percentile_252d unavailable.",
        ))

    if inp.candidate is not None and _has_missing_iv(inp):
        out.append(PenaltyEntry(
            code="MISSING_IV",
            label="Missing IV on a leg",
            points=PENALTY_MISSING_IV,
            reason="One or more selected legs lack implied volatility.",
        ))

    if "NO_OPEN_INTEREST" in feat_flags:
        out.append(PenaltyEntry(
            code="NO_OPEN_INTEREST",
            label="Naive gamma exposure proxy",
            points=PENALTY_NAIVE_GEX,
            reason=(
                "Gamma exposure proxy is naive — no open interest base "
                "data; not equivalent to dealer GEX."
            ),
        ))

    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compute_score(inp: ScoringInputs) -> EvaluationScore:
    """Deterministic 0-100 score with breakdown + penalties."""
    components = (
        _component_liquidity(inp),
        _component_risk_reward(inp),
        _component_vol_context(inp),
        _component_structure(inp),
    )
    penalties = _penalties(inp)
    raw_penalty = sum((p.points for p in penalties), start=0)
    capped_penalty = max(raw_penalty, -PENALTY_CAP)
    raw_total = sum(c.score for c in components) + capped_penalty
    total = max(0, min(100, raw_total))

    return EvaluationScore(
        rule_id=inp.rule_id,
        underlying=inp.underlying,
        as_of_date=inp.as_of_date.isoformat(),
        qualified=inp.qualified,
        total_score=int(total),
        components=components,
        penalties=tuple(penalties),
        flags=inp.flags,
        inputs={
            "score_model_version": SCORE_MODEL_VERSION,
            "weight_max_total": (
                WEIGHT_LIQUIDITY + WEIGHT_RISK_REWARD
                + WEIGHT_VOL_CONTEXT + WEIGHT_STRUCTURE
            ),
            "penalty_cap_abs": PENALTY_CAP,
            "raw_penalty_sum": int(raw_penalty),
            "capped_penalty": int(capped_penalty),
            "raw_total_pre_clamp": int(raw_total),
            "n_accepted_quotes": len(inp.accepted_quotes),
            "has_candidate": inp.candidate is not None,
        },
    )


def serialise(s: EvaluationScore) -> dict:
    return {
        "rule_id": s.rule_id,
        "underlying": s.underlying,
        "as_of_date": s.as_of_date,
        "qualified": s.qualified,
        "total_score": s.total_score,
        "model_version": s.model_version,
        "components": [
            {
                "component": c.component,
                "weight_max": c.weight_max,
                "score": c.score,
                "explanation": c.explanation,
            }
            for c in s.components
        ],
        "penalties": [
            {
                "code": p.code, "label": p.label,
                "points": p.points, "reason": p.reason,
            }
            for p in s.penalties
        ],
        "flags": list(s.flags),
        "inputs": s.inputs,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:    # noqa: BLE001
        return None


def _disp(d: Decimal | None) -> str:
    return str(d) if d is not None else "n/a"


def _legs_for_candidate(inp: ScoringInputs) -> list[OptionChainQuote]:
    if inp.candidate is None:
        return []
    symbols = _candidate_symbols(inp.candidate)
    if not symbols:
        return []
    by_sym = {q.option_symbol: q for q in inp.accepted_quotes}
    return [by_sym[s] for s in symbols if s in by_sym]


def _candidate_symbols(cand: dict) -> list[str]:
    out: list[str] = []
    if "short_symbol" in cand:
        out.append(cand["short_symbol"])
    if "long_symbol" in cand:
        out.append(cand["long_symbol"])
    if "put_wing" in cand:
        for k in ("short_symbol", "long_symbol"):
            if cand["put_wing"].get(k):
                out.append(cand["put_wing"][k])
    if "call_wing" in cand:
        for k in ("short_symbol", "long_symbol"):
            if cand["call_wing"].get(k):
                out.append(cand["call_wing"][k])
    return out


def _candidate_geometry(inp: ScoringInputs) -> tuple[Decimal | None, Decimal | None]:
    """Return (max_width, credit_per_contract) at observation time.
    Iron condor uses the WIDER wing for max_width."""
    if inp.candidate is None:
        return None, None
    legs = _legs_for_candidate(inp)
    if not legs:
        return None, None

    cand = inp.candidate
    if "put_wing" in cand and "call_wing" in cand:
        put_w = abs(
            Decimal(cand["put_wing"]["short_strike"])
            - Decimal(cand["put_wing"]["long_strike"])
        )
        call_w = abs(
            Decimal(cand["call_wing"]["short_strike"])
            - Decimal(cand["call_wing"]["long_strike"])
        )
        width = put_w if put_w > call_w else call_w
    elif "short_strike" in cand and "long_strike" in cand:
        width = abs(
            Decimal(cand["short_strike"]) - Decimal(cand["long_strike"])
        )
    else:
        return None, None

    # Credit per contract = sum of mid for SELL legs - sum of mid for BUY legs
    credit = Decimal("0")
    contributing = 0
    for q in legs:
        if q.mid is None:
            continue
        sym = q.option_symbol
        # Treat any leg whose symbol matches a "short_symbol" key as SELL
        is_short = (
            sym == cand.get("short_symbol")
            or sym == (cand.get("put_wing") or {}).get("short_symbol")
            or sym == (cand.get("call_wing") or {}).get("short_symbol")
        )
        sign = Decimal("1") if is_short else Decimal("-1")
        credit += sign * q.mid
        contributing += 1
    if contributing == 0:
        return width, None
    return width, credit


def _candidate_dte(inp: ScoringInputs) -> int | None:
    if inp.candidate is None:
        return None
    cand = inp.candidate
    expiry_str = cand.get("expiry") or (
        (cand.get("put_wing") or {}).get("expiry")
        or (cand.get("call_wing") or {}).get("expiry")
    )
    if not expiry_str:
        return None
    try:
        e = datetime.date.fromisoformat(expiry_str)
    except ValueError:
        return None
    return (e - inp.as_of_date).days


def _candidate_short_delta(inp: ScoringInputs) -> Decimal | None:
    if inp.candidate is None:
        return None
    legs = _legs_for_candidate(inp)
    cand = inp.candidate
    short_syms = [
        cand.get("short_symbol"),
        (cand.get("put_wing") or {}).get("short_symbol"),
        (cand.get("call_wing") or {}).get("short_symbol"),
    ]
    short_syms = [s for s in short_syms if s]
    by_sym = {q.option_symbol: q for q in legs}
    deltas = [
        by_sym[s].delta for s in short_syms
        if s in by_sym and by_sym[s].delta is not None
    ]
    if not deltas:
        return None
    # For iron condor we report whichever leg has higher abs delta
    return max(deltas, key=lambda d: abs(d))


def _has_missing_greeks(inp: ScoringInputs) -> bool:
    legs = _legs_for_candidate(inp)
    for q in legs:
        if any(g is None for g in (q.delta, q.gamma, q.theta, q.vega)):
            return True
    return False


def _has_missing_iv(inp: ScoringInputs) -> bool:
    legs = _legs_for_candidate(inp)
    return any(q.iv is None for q in legs)
