"""Strategy rule registry + eligibility evaluator (Phase 11G).

Frozen v1 strategies + the per-criterion checks that historically would
have qualified or rejected a candidate. Output is OBSERVATIONAL — it
never produces a trade, never ranks strategies, never says one is
"best". Each criterion carries a plain-English explanation operators
can audit.

Pure-fn module. No DB. No I/O. Stdlib + Decimal only.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from apps.api.src.options.data.liquidity_filter import (
    MAX_BID_ASK_SPREAD_DOLLARS,
    MAX_QUOTE_AGE_SECONDS,
    MIN_OPEN_INTEREST,
    evaluate_quote,
)
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.strategies import (
    DEFINED_RISK_STRATEGIES,
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


# ---------------------------------------------------------------------------
# Frozen rule registry — v1 (mirrors paper engine's defined-risk universe)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CriterionDef:
    code: str                  # short token for UI/test pattern matching
    label: str                 # operator-readable name
    description: str           # plain-English explanation


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    name: str
    summary: str
    criteria: tuple[CriterionDef, ...]


_LIQUIDITY = CriterionDef(
    code="LIQUIDITY",
    label="Quote liquidity",
    description=(
        f"Each leg's quote must pass the v1 liquidity filter: "
        f"open_interest >= {MIN_OPEN_INTEREST}, "
        f"(ask - bid) <= ${MAX_BID_ASK_SPREAD_DOLLARS}, "
        f"bid > 0, ask > bid, "
        f"quote_age_seconds <= {MAX_QUOTE_AGE_SECONDS}."
    ),
)

_DELTA_BAND = CriterionDef(
    code="SHORT_LEG_DELTA_BAND",
    label="Short leg in target delta band",
    description=(
        "Short leg delta within the strategy's target band "
        "(short put / short call ~0.20-0.35 absolute delta). "
        "Reject if outside the band or delta missing."
    ),
)

_LONG_PROTECTION = CriterionDef(
    code="LONG_LEG_PROTECTION",
    label="Long leg present beyond short leg",
    description=(
        "Long protective leg exists at the correct side of the short "
        "strike (long put strictly below short put for a put credit "
        "spread; long call strictly above short call for a call credit "
        "spread). Defines the max-loss cap."
    ),
)

_DTE_BAND = CriterionDef(
    code="DTE_BAND",
    label="Days-to-expiry in 21-45 day band",
    description=(
        "Both legs share an expiry with 21-45 calendar days remaining. "
        "Outside this band the standard tastytrade-style edge profile "
        "does not hold."
    ),
)

_SAME_QTY = CriterionDef(
    code="SAME_QTY_SAME_EXPIRY",
    label="All legs same quantity + same expiry",
    description=(
        "Defined-risk shapes require identical contract counts and one "
        "expiry across all legs."
    ),
)

_IRON_CONDOR_SHAPE = CriterionDef(
    code="IRON_CONDOR_SHAPE",
    label="4-leg shape: long put + short put + short call + long call",
    description=(
        "Iron condor requires 2 puts (long below, short above) and 2 "
        "calls (short below, long above), with short put strike < short "
        "call strike."
    ),
)


RULE_DEFS: dict[str, RuleDef] = {
    STRATEGY_SHORT_PUT_CREDIT_SPREAD: RuleDef(
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        name="Short put credit spread",
        summary=(
            "Sell an out-of-the-money put, buy a further OTM put for "
            "defined-risk protection. Net credit; max profit = credit; "
            "max loss = (width - credit) * 100 * qty."
        ),
        criteria=(_LIQUIDITY, _DELTA_BAND, _LONG_PROTECTION,
                  _DTE_BAND, _SAME_QTY),
    ),
    STRATEGY_SHORT_CALL_CREDIT_SPREAD: RuleDef(
        rule_id=STRATEGY_SHORT_CALL_CREDIT_SPREAD,
        name="Short call credit spread",
        summary=(
            "Sell an OTM call, buy a further OTM call for defined-risk "
            "protection. Same risk math as short put credit spread."
        ),
        criteria=(_LIQUIDITY, _DELTA_BAND, _LONG_PROTECTION,
                  _DTE_BAND, _SAME_QTY),
    ),
    STRATEGY_IRON_CONDOR: RuleDef(
        rule_id=STRATEGY_IRON_CONDOR,
        name="Iron condor",
        summary=(
            "Combine an OTM short put credit spread + OTM short call "
            "credit spread on the same expiry. Profit zone between the "
            "two short strikes; max loss = max(wing widths) - credit."
        ),
        criteria=(_LIQUIDITY, _DELTA_BAND, _IRON_CONDOR_SHAPE,
                  _DTE_BAND, _SAME_QTY),
    ),
}


def list_rule_defs() -> list[dict[str, Any]]:
    """Serialise the rule registry for the API.
    Stable shape; UI consumes verbatim."""
    return [
        {
            "rule_id": r.rule_id,
            "name": r.name,
            "summary": r.summary,
            "criteria": [
                {
                    "code": c.code,
                    "label": c.label,
                    "description": c.description,
                }
                for c in r.criteria
            ],
        }
        for r in RULE_DEFS.values()
    ]


# ---------------------------------------------------------------------------
# Eligibility evaluator
# ---------------------------------------------------------------------------

# Frozen v1 thresholds. Mirror paper.engine + chain ingest where
# applicable; constants kept local so the eligibility model can be
# audited in one place.
DTE_MIN_DAYS = 21
DTE_MAX_DAYS = 45
SHORT_DELTA_MIN_ABS = Decimal("0.20")
SHORT_DELTA_MAX_ABS = Decimal("0.35")


@dataclass(frozen=True)
class CriterionCheck:
    code: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    name: str
    qualified: bool
    n_criteria: int
    n_passed: int
    checks: tuple[CriterionCheck, ...]
    candidate: dict[str, Any] | None = None     # selected legs at eval time
    notes: tuple[str, ...] = field(default_factory=tuple)


def _calls(quotes: Sequence[OptionChainQuote]) -> list[OptionChainQuote]:
    return [q for q in quotes if q.option_type == "CALL"]


def _puts(quotes: Sequence[OptionChainQuote]) -> list[OptionChainQuote]:
    return [q for q in quotes if q.option_type == "PUT"]


def _quote_passes_liquidity(q: OptionChainQuote) -> str | None:
    return evaluate_quote(q)


def _select_short_leg(
    side_quotes: Sequence[OptionChainQuote],
    *,
    target_abs_delta: Decimal,
) -> OptionChainQuote | None:
    """Pick the candidate with delta closest to ±target_abs_delta within
    the [SHORT_DELTA_MIN_ABS, SHORT_DELTA_MAX_ABS] band."""
    target = -target_abs_delta if (
        side_quotes and side_quotes[0].option_type == "PUT"
    ) else target_abs_delta
    in_band = [
        q for q in side_quotes
        if q.delta is not None
        and SHORT_DELTA_MIN_ABS <= abs(q.delta) <= SHORT_DELTA_MAX_ABS
    ]
    if not in_band:
        return None
    return min(in_band, key=lambda q: abs(q.delta - target))


def _evaluate_credit_spread(
    *,
    rule: RuleDef,
    side: str,                      # "PUT" or "CALL"
    quotes: Sequence[OptionChainQuote],
    as_of: datetime.date,
) -> RuleEvaluation:
    side_quotes = _puts(quotes) if side == "PUT" else _calls(quotes)
    checks: list[CriterionCheck] = []
    candidate: dict[str, Any] | None = None
    notes: list[str] = []

    if not side_quotes:
        return RuleEvaluation(
            rule_id=rule.rule_id, name=rule.name, qualified=False,
            n_criteria=len(rule.criteria), n_passed=0,
            checks=tuple(
                CriterionCheck(code=c.code, passed=False,
                               reason=f"no {side.lower()} quotes available")
                for c in rule.criteria
            ),
            candidate=None, notes=("NO_QUOTES",),
        )

    target_abs = Decimal("0.30")
    short_leg = _select_short_leg(side_quotes, target_abs_delta=target_abs)

    delta_pass = short_leg is not None
    delta_reason = (
        f"selected short {side.lower()} strike={short_leg.strike} "
        f"delta={short_leg.delta}"
        if short_leg
        else f"no {side.lower()} found with |delta| in "
             f"[{SHORT_DELTA_MIN_ABS}, {SHORT_DELTA_MAX_ABS}]"
    )
    checks.append(CriterionCheck(
        code="SHORT_LEG_DELTA_BAND", passed=delta_pass, reason=delta_reason,
    ))

    long_leg: OptionChainQuote | None = None
    if short_leg is not None:
        if side == "PUT":
            candidates = sorted(
                [q for q in side_quotes if q.strike < short_leg.strike],
                key=lambda q: q.strike, reverse=True,
            )
        else:
            candidates = sorted(
                [q for q in side_quotes if q.strike > short_leg.strike],
                key=lambda q: q.strike,
            )
        long_leg = candidates[0] if candidates else None
    long_pass = long_leg is not None
    long_reason = (
        f"selected long {side.lower()} strike={long_leg.strike}"
        if long_leg
        else f"no protective long {side.lower()} beyond short strike"
    )
    checks.append(CriterionCheck(
        code="LONG_LEG_PROTECTION", passed=long_pass, reason=long_reason,
    ))

    legs_for_liq = [q for q in (short_leg, long_leg) if q is not None]
    liq_failures = [
        (q, _quote_passes_liquidity(q))
        for q in legs_for_liq
    ]
    bad = [(q, r) for q, r in liq_failures if r is not None]
    liq_pass = bool(legs_for_liq) and not bad
    liq_reason = (
        "all selected legs pass liquidity filter"
        if liq_pass
        else (
            "; ".join(f"strike={q.strike}: {r}" for q, r in bad)
            if bad else "no legs to check"
        )
    )
    checks.append(CriterionCheck(
        code="LIQUIDITY", passed=liq_pass, reason=liq_reason,
    ))

    expiries = sorted({q.expiry for q in legs_for_liq})
    if not expiries:
        dte_pass = False
        dte_reason = "no legs to evaluate DTE"
    else:
        dte = (expiries[0] - as_of).days
        dte_pass = DTE_MIN_DAYS <= dte <= DTE_MAX_DAYS
        dte_reason = (
            f"expiry={expiries[0]} dte={dte} "
            f"({'in' if dte_pass else 'outside'} {DTE_MIN_DAYS}-{DTE_MAX_DAYS} band)"
        )
    checks.append(CriterionCheck(
        code="DTE_BAND", passed=dte_pass, reason=dte_reason,
    ))

    qty_expiry_pass = bool(legs_for_liq) and len(expiries) <= 1
    qty_reason = (
        "single shared expiry across legs"
        if qty_expiry_pass
        else f"expiries differ: {expiries}"
    )
    checks.append(CriterionCheck(
        code="SAME_QTY_SAME_EXPIRY", passed=qty_expiry_pass, reason=qty_reason,
    ))

    if short_leg and long_leg:
        candidate = {
            "side": side,
            "short_strike": str(short_leg.strike),
            "short_delta":  (str(short_leg.delta) if short_leg.delta is not None else None),
            "long_strike":  str(long_leg.strike),
            "expiry":       short_leg.expiry.isoformat(),
            "short_symbol": short_leg.option_symbol,
            "long_symbol":  long_leg.option_symbol,
        }

    n_pass = sum(1 for c in checks if c.passed)
    qualified = (n_pass == len(checks))
    return RuleEvaluation(
        rule_id=rule.rule_id, name=rule.name,
        qualified=qualified,
        n_criteria=len(checks), n_passed=n_pass,
        checks=tuple(checks),
        candidate=candidate,
        notes=tuple(notes),
    )


def _evaluate_iron_condor(
    *,
    rule: RuleDef,
    quotes: Sequence[OptionChainQuote],
    as_of: datetime.date,
) -> RuleEvaluation:
    put_eval = _evaluate_credit_spread(
        rule=RULE_DEFS[STRATEGY_SHORT_PUT_CREDIT_SPREAD],
        side="PUT", quotes=quotes, as_of=as_of,
    )
    call_eval = _evaluate_credit_spread(
        rule=RULE_DEFS[STRATEGY_SHORT_CALL_CREDIT_SPREAD],
        side="CALL", quotes=quotes, as_of=as_of,
    )

    checks: list[CriterionCheck] = []
    # Reuse component checks but flatten + dedupe
    by_code: dict[str, CriterionCheck] = {}
    for c in (*put_eval.checks, *call_eval.checks):
        if c.code in by_code:
            existing = by_code[c.code]
            by_code[c.code] = CriterionCheck(
                code=c.code,
                passed=existing.passed and c.passed,
                reason=f"PUT: {existing.reason} | CALL: {c.reason}",
            )
        else:
            by_code[c.code] = c

    shape_pass = (
        put_eval.candidate is not None
        and call_eval.candidate is not None
        and Decimal(put_eval.candidate["short_strike"])
            < Decimal(call_eval.candidate["short_strike"])
    )
    shape_reason = (
        "4-leg iron condor shape valid"
        if shape_pass
        else "missing put or call wing, or strikes overlap"
    )
    by_code["IRON_CONDOR_SHAPE"] = CriterionCheck(
        code="IRON_CONDOR_SHAPE", passed=shape_pass, reason=shape_reason,
    )

    ordered_codes = [c.code for c in rule.criteria]
    checks = [by_code[c] for c in ordered_codes if c in by_code]
    candidate = None
    if (put_eval.candidate is not None
            and call_eval.candidate is not None):
        candidate = {
            "put_wing":  put_eval.candidate,
            "call_wing": call_eval.candidate,
        }
    n_pass = sum(1 for c in checks if c.passed)
    qualified = n_pass == len(checks)
    return RuleEvaluation(
        rule_id=rule.rule_id, name=rule.name, qualified=qualified,
        n_criteria=len(checks), n_passed=n_pass,
        checks=tuple(checks), candidate=candidate, notes=(),
    )


def evaluate_rules(
    quotes: Sequence[OptionChainQuote],
    *,
    as_of: datetime.date,
) -> list[RuleEvaluation]:
    """Evaluate all v1 rules against a chain snapshot. Returns one
    RuleEvaluation per rule. Output is OBSERVATIONAL — never used to
    create trades, never ranked, never labeled "best".
    """
    out: list[RuleEvaluation] = []
    for rid in DEFINED_RISK_STRATEGIES:
        rule = RULE_DEFS[rid]
        if rid == STRATEGY_SHORT_PUT_CREDIT_SPREAD:
            out.append(_evaluate_credit_spread(
                rule=rule, side="PUT", quotes=quotes, as_of=as_of,
            ))
        elif rid == STRATEGY_SHORT_CALL_CREDIT_SPREAD:
            out.append(_evaluate_credit_spread(
                rule=rule, side="CALL", quotes=quotes, as_of=as_of,
            ))
        elif rid == STRATEGY_IRON_CONDOR:
            out.append(_evaluate_iron_condor(
                rule=rule, quotes=quotes, as_of=as_of,
            ))
    return out


def serialise_evaluation(ev: RuleEvaluation) -> dict[str, Any]:
    return {
        "rule_id": ev.rule_id,
        "name": ev.name,
        "qualified": ev.qualified,
        "n_criteria": ev.n_criteria,
        "n_passed": ev.n_passed,
        "checks": [
            {"code": c.code, "passed": c.passed, "reason": c.reason}
            for c in ev.checks
        ],
        "candidate": ev.candidate,
        "notes": list(ev.notes),
    }
