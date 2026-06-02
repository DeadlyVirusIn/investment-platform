"""Phase B — Opportunity composition + ranking service.

Reads from shadow_decision_log + strategy_bias + feature_daily +
chain_snapshot and projects a canonical opportunity-card payload.

Ranking (composite, weights locked):
   0.40  shadow score (0..1 — `options_shadow_decision_log.score`)
   0.20  freshness (today=1.0, T-1=0.7, T-2=0.4, older=0.1)
   0.15  liquidity (gate passes summed)
   0.15  IV-strategy fit (regime_fit lookup vs current iv_rank)
   0.10  event proximity (earnings within DTE → +1, else 0)

The output preserves enough raw fields that the UI can render the
canonical OptionsOpportunityCard with no derivation: bias label,
strikes, expiry, DTE, max risk/reward (when derivable), confidence,
rationale points, catalysts, timeline, liquidity tier, IV context,
probability profile (delta as proxy).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.opportunities.economics import attach_economics


# Locked bias taxonomy. The migration's CHECK constraint enforces
# these values at the DB level.
LANE = Literal[
    "bullish", "bearish", "neutral", "event", "developing", "conviction",
]


# Composite-score weights — keep in lockstep with the docstring.
WEIGHT_SCORE   = 0.40
WEIGHT_FRESH   = 0.20
WEIGHT_LIQ     = 0.15
WEIGHT_IV_FIT  = 0.15
WEIGHT_EVENT   = 0.10


# Conviction promotion threshold. Items with composite ≥ this float
# appear in the Conviction lane in addition to their bias lane.
CONVICTION_FLOOR = 0.78


# Hybrid (Phase 1) — engine-executable structures the paper engine can
# open + risk-manage. Everything else is a research idea. `family` is
# DERIVED from rule_id at read time (no stored column, no migration).
ENGINE_SUPPORTED_STRUCTURES = (
    "SHORT_PUT_CREDIT_SPREAD",
    "SHORT_CALL_CREDIT_SPREAD",
    "IRON_CONDOR",
)

FAMILY_ENGINE = "engine_executable"
FAMILY_RESEARCH = "research"


def _family_for(rule_id: str) -> str:
    return (
        FAMILY_ENGINE if rule_id in ENGINE_SUPPORTED_STRUCTURES
        else FAMILY_RESEARCH
    )


@dataclass
class OpportunityItem:
    """Canonical payload — matches the frontend card contract."""
    # Identity
    observation_id: int
    underlying: str
    rule_id: str
    option_symbol: str
    expiry: dt.date
    strike: float
    option_type: str
    side: str
    run_date: dt.date

    # Bias
    bias: str
    directional_view: str
    risk_profile: str

    # Ranking
    score: float                          # shadow score 0..1
    composite_score: float                # final ranking score 0..1
    freshness: float
    liquidity_score: float
    iv_fit: float
    event_boost: float
    would_trade: bool
    qualified: bool

    # Card-display fields
    dte: int
    earnings_between: bool
    liquidity_tier: str                   # good|fair|poor|unknown
    iv_rank: float | None
    atm_iv: float | None
    ivt_premium_tier: str                 # rich|elevated|average|cheap|unknown
    bid: float | None
    ask: float | None
    mid: float | None
    spread: float | None
    open_interest: int | None
    volume: int | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    iv: float | None
    quote_age_seconds: int | None
    provider: str | None

    rationale_points: list[str] = field(default_factory=list)
    template_name: str | None = None
    # Phase B6 — explainability passthrough from options_strategy_candidate.
    why_emitted: str | None = None
    triggering_rule: str | None = None
    rejected_alternatives: list[dict[str, Any]] = field(default_factory=list)
    strategy_fit_reason: str | None = None
    iv_fit_reason: str | None = None
    dte_fit_reason: str | None = None
    liquidity_fit_reason: str | None = None
    # Phase B7 — catalyst metadata (NULL when no event in DTE window).
    earliest_event_date: dt.date | None = None
    earliest_event_type: str | None = None
    earliest_event_importance: str | None = None
    event_days_away: int | None = None
    catalyst_title: str | None = None
    catalyst_explanation: str | None = None
    # Hybrid (Phase 1) — family tagging, derived from rule_id.
    family: str = FAMILY_RESEARCH
    engine_compatible: bool = False
    above_floor: bool = False
    # Phase C Stage 2B — read-side, additive. candidate_id keys the
    # persisted legs; economics is derived from them (None when legs are
    # missing/incomplete/uncomputable). Never affects ranking/scoring.
    candidate_id: int = 0
    economics: dict[str, Any] | None = None


# ---- helpers ---------------------------------------------------------------


def _freshness(created_at: dt.datetime | None, now: dt.datetime) -> float:
    """Elapsed-time freshness keyed off the candidate's created_at (the
    real generation instant) — NOT run_date. Removes the UTC-midnight
    cliff: a candidate <24h old scores 1.0 regardless of calendar
    rollover. Buckets: <24h=1.0, 24-48h=0.7, 48-72h=0.4, >72h=0.1.
    Defensive: missing created_at → treat as oldest tier (0.1)."""
    if created_at is None:
        return 0.1
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=dt.timezone.utc)
    hours = (now - created_at).total_seconds() / 3600.0
    if hours < 24: return 1.0
    if hours < 48: return 0.7
    if hours < 72: return 0.4
    return 0.1


def _liquidity_score(
    liquidity_pass: bool, spread_pass: bool,
    open_interest_pass: bool, volume_pass: bool,
) -> float:
    # 4 gates, equal weight; normalized to 0..1.
    return (
        (1.0 if liquidity_pass else 0.0)
        + (1.0 if spread_pass else 0.0)
        + (1.0 if open_interest_pass else 0.0)
        + (1.0 if volume_pass else 0.0)
    ) / 4.0


def _liquidity_tier(score: float) -> str:
    if score >= 0.85: return "good"
    if score >= 0.55: return "fair"
    if score >= 0.30: return "poor"
    return "unknown"


def _iv_fit(iv_rank: float | None, regime_fit: dict[str, Any]) -> float:
    """Score how the current iv_rank aligns with the strategy's
    regime_fit hints. Returns 0..1; defaults to 0.5 when either input
    is unavailable (neutral fit)."""
    if iv_rank is None or not regime_fit:
        return 0.5
    key = "iv_high" if iv_rank >= 50 else "iv_low"
    pref = (regime_fit.get(key) or "").lower()
    if pref == "favored": return 1.0
    if pref == "neutral": return 0.5
    if pref == "avoid":   return 0.0
    return 0.5


def _premium_tier(iv_rank: float | None) -> str:
    if iv_rank is None: return "unknown"
    if iv_rank >= 75: return "rich"
    if iv_rank >= 50: return "elevated"
    if iv_rank >= 25: return "average"
    return "cheap"


def _composite(
    score: float, freshness: float, liquidity: float,
    iv_fit: float, event_boost: float,
) -> float:
    return (
        WEIGHT_SCORE  * score
        + WEIGHT_FRESH  * freshness
        + WEIGHT_LIQ    * liquidity
        + WEIGHT_IV_FIT * iv_fit
        + WEIGHT_EVENT  * event_boost
    )


def _decimal(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v, Decimal): return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---- main query ------------------------------------------------------------


def fetch_opportunities(
    session: Session,
    *,
    lane: str | None = None,
    limit: int = 24,
    lookback_days: int = 7,
    min_score: float | None = None,
    family: str | None = None,
    now: dt.date | None = None,
) -> list[OpportunityItem]:
    """Compose ranked opportunities. When `lane='conviction'`,
    cross-lane top-N are returned; otherwise filters by bias."""
    today = now or dt.datetime.now(dt.timezone.utc).date()
    now_utc = dt.datetime.now(dt.timezone.utc)   # for elapsed-time freshness

    # Phase B6.5 — source: options_strategy_candidate. Each row is one
    # AI-strategist interpretation of an accepted shadow observation.
    # The shadow_decision_log row is joined for the option_symbol +
    # gate-pass booleans used by the ranking math; the bias is read
    # from strategy_candidate.bias directly (denormalized at emission).
    sql = text(
        """
        SELECT
          c.id                              AS candidate_id,
          c.shadow_observation_id           AS observation_id,
          c.run_date,
          c.created_at                      AS candidate_created_at,
          c.underlying,
          c.rule_id                         AS strategy_name,
          c.bias,
          c.directional_view,
          c.risk_profile,
          c.confidence,
          c.iv_suitability,
          c.expiry_suitability,
          c.liquidity_suitability,
          c.composite_score                 AS candidate_composite,
          c.why_emitted,
          c.triggering_rule,
          c.rejected_alternatives,
          c.strategy_fit_reason,
          c.iv_fit_reason,
          c.dte_fit_reason,
          c.liquidity_fit_reason,
          c.diagnostics                     AS candidate_diagnostics,
          c.earliest_event_date,
          c.earliest_event_type,
          c.earliest_event_importance,
          c.event_days_away,
          mec.title                          AS catalyst_title,
          mec.explanation                    AS catalyst_explanation,
          s.option_symbol,
          s.expiration                      AS expiry,
          s.strike,
          s.option_type,
          s.side,
          s.would_trade,
          s.reason,
          s.liquidity_pass,
          s.spread_pass,
          s.open_interest_pass,
          s.volume_pass,
          s.greeks_pass,
          s.iv_rank_pass,
          s.risk_pass,
          s.score                            AS shadow_score,
          s.diagnostics                      AS shadow_diagnostics,
          f.iv_rank_252d                     AS iv_rank,
          f.atm_iv                           AS atm_iv,
          ch.bid, ch.ask, ch.mid,
          ch.open_interest, ch.volume,
          ch.delta, ch.gamma, ch.theta, ch.vega, ch.iv,
          ch.quote_age_seconds, ch.provider
        FROM options_strategy_candidate c
        JOIN options_shadow_decision_log s
          ON s.id = c.shadow_observation_id
        LEFT JOIN options_feature_daily f
          ON f.underlying = c.underlying
         AND f.as_of_date = c.run_date
        LEFT JOIN LATERAL (
          SELECT bid, ask, mid, open_interest, volume,
                 delta, gamma, theta, vega, iv,
                 quote_age_seconds, provider
          FROM options_chain_snapshot
          WHERE option_symbol = s.option_symbol
          ORDER BY snapshot_at_utc DESC
          LIMIT 1
        ) ch ON TRUE
        LEFT JOIN market_event_calendar mec
          ON mec.event_type = c.earliest_event_type
         AND mec.event_date = c.earliest_event_date
        WHERE c.run_date >= (CURRENT_DATE - (:lookback_days)::int)
          AND (CAST(:min_score AS numeric) IS NULL
               OR c.composite_score >= CAST(:min_score AS numeric))
        ORDER BY c.composite_score DESC, c.run_date DESC
        """
    )

    rows = session.execute(
        sql, {"lookback_days": lookback_days, "min_score": min_score},
    ).mappings().all()

    items: list[OpportunityItem] = []
    for r in rows:
        # Phase B6.5 — score is the candidate's confidence (0..1 already);
        # liquidity is the precomputed suitability score. iv_fit comes
        # straight from the candidate. Re-running the composite here
        # adds the run-time freshness + event signals on top so lane
        # ranking still favors today's signals over older ones.
        score = float(_decimal(r["confidence"]) or 0.0)
        liquidity = float(_decimal(r["liquidity_suitability"]) or 0.0)
        iv_fit = float(_decimal(r["iv_suitability"]) or 0.0)
        iv_rank = _decimal(r["iv_rank"])
        freshness = _freshness(r["candidate_created_at"], now_utc)
        dte = (r["expiry"] - today).days if r["expiry"] else 0
        # Phase B7 — Event-proximity boost grounded in the candidate's
        # actual catalyst metadata. Three tiers:
        #   1.0  named high-importance event inside DTE window
        #   0.5  named medium-importance event inside DTE window
        #   0.5  inferred catalyst (event bias + short DTE, no named event)
        #   0.0  no catalyst
        event_days = r["event_days_away"]
        event_importance = r["earliest_event_importance"]
        if event_days is not None and event_importance == "high":
            event_boost = 1.0
        elif event_days is not None and event_importance == "medium":
            event_boost = 0.5
        elif r["bias"] == "event" and 0 < dte <= 14:
            event_boost = 0.5      # inferred-catalyst fallback
        else:
            event_boost = 0.0
        composite = _composite(score, freshness, liquidity, iv_fit, event_boost)

        # Hybrid family tagging (Phase 1) — derived, additive. NOTE: must
        # NOT reuse the name `family` here — that is the function parameter
        # (the requested filter); shadowing it corrupts the post-loop
        # family filter. Use a distinct per-row name.
        engine_compatible = (
            str(r["strategy_name"]) in ENGINE_SUPPORTED_STRUCTURES
        )
        row_family = _family_for(str(r["strategy_name"]))
        above_floor = composite >= CONVICTION_FLOOR

        bid = _decimal(r["bid"])
        ask = _decimal(r["ask"])
        spread = (ask - bid) if (bid is not None and ask is not None) else None

        # Rationale points — surface the strategy candidate's
        # explainability metadata. Educational layer reads these
        # verbatim; nothing is generated at runtime.
        rationale: list[str] = []
        if r["why_emitted"]:
            rationale.append(r["why_emitted"])
        if r["strategy_fit_reason"]:
            rationale.append(r["strategy_fit_reason"])
        if r["iv_fit_reason"]:
            rationale.append(r["iv_fit_reason"])
        if r["dte_fit_reason"]:
            rationale.append(r["dte_fit_reason"])
        if r["liquidity_fit_reason"]:
            rationale.append(r["liquidity_fit_reason"])
        # rejected_alternatives field stays in diagnostics for the
        # educational drawer to render as "alternatives considered".

        items.append(OpportunityItem(
            observation_id=int(r["observation_id"]),
            candidate_id=int(r["candidate_id"]),
            underlying=str(r["underlying"]),
            rule_id=str(r["strategy_name"]),
            option_symbol=str(r["option_symbol"]),
            expiry=r["expiry"],
            strike=float(_decimal(r["strike"]) or 0),
            option_type=str(r["option_type"]),
            side=str(r["side"]),
            run_date=r["run_date"],
            bias=str(r["bias"]),
            directional_view=str(r["directional_view"]),
            risk_profile=str(r["risk_profile"]),
            score=score,
            composite_score=composite,
            freshness=freshness,
            liquidity_score=liquidity,
            iv_fit=iv_fit,
            event_boost=event_boost,
            would_trade=bool(r["would_trade"]),
            qualified=bool(r["would_trade"]),
            dte=dte,
            earnings_between=False,        # Phase B placeholder
            liquidity_tier=_liquidity_tier(liquidity),
            iv_rank=iv_rank,
            atm_iv=_decimal(r["atm_iv"]),
            ivt_premium_tier=_premium_tier(iv_rank),
            bid=bid, ask=ask, mid=_decimal(r["mid"]),
            spread=spread,
            open_interest=(int(r["open_interest"])
                           if r["open_interest"] is not None else None),
            volume=(int(r["volume"]) if r["volume"] is not None else None),
            delta=_decimal(r["delta"]),
            gamma=_decimal(r["gamma"]),
            theta=_decimal(r["theta"]),
            vega=_decimal(r["vega"]),
            iv=_decimal(r["iv"]),
            quote_age_seconds=(
                int(r["quote_age_seconds"])
                if r["quote_age_seconds"] is not None else None
            ),
            provider=str(r["provider"]) if r["provider"] else None,
            rationale_points=rationale,
            template_name=str(r["triggering_rule"] or r["strategy_name"]),
            why_emitted=r["why_emitted"],
            triggering_rule=r["triggering_rule"],
            rejected_alternatives=(
                r["rejected_alternatives"] if isinstance(r["rejected_alternatives"], list)
                else (json.loads(r["rejected_alternatives"])
                      if r["rejected_alternatives"] else [])
            ),
            strategy_fit_reason=r["strategy_fit_reason"],
            iv_fit_reason=r["iv_fit_reason"],
            dte_fit_reason=r["dte_fit_reason"],
            liquidity_fit_reason=r["liquidity_fit_reason"],
            earliest_event_date=r["earliest_event_date"],
            earliest_event_type=r["earliest_event_type"],
            earliest_event_importance=r["earliest_event_importance"],
            event_days_away=r["event_days_away"],
            catalyst_title=r["catalyst_title"],
            catalyst_explanation=r["catalyst_explanation"],
            family=row_family,
            engine_compatible=engine_compatible,
            above_floor=above_floor,
        ))

    # Lane filter — done in Python to keep the SQL portable.
    if lane:
        lane_l = lane.lower()
        if lane_l == "conviction":
            items = [
                i for i in items
                if i.composite_score >= CONVICTION_FLOOR and i.qualified
            ]
        elif lane_l == "developing":
            # Strategy bias may say developing; OR engine didn't
            # would-trade today (but was scored). Either lands here.
            items = [
                i for i in items
                if i.bias == "developing" or not i.would_trade
            ]
        elif lane_l == "event":
            items = [i for i in items if i.bias == "event" or i.event_boost > 0]
        else:
            items = [i for i in items if i.bias == lane_l]

    # Hybrid family filter (Phase 1) — additive; omitted → both families.
    if family:
        fam_l = family.lower()
        if fam_l in (FAMILY_ENGINE, FAMILY_RESEARCH):
            items = [i for i in items if i.family == fam_l]

    # Final ranking by composite score (descending), tie-break by score.
    items.sort(
        key=lambda x: (x.composite_score, x.score, x.run_date.toordinal()),
        reverse=True,
    )
    result = items[:limit]
    # Phase C Stage 2B — attach read-side economics derived from persisted
    # legs (None when legs missing/incomplete). Ranking already finalized
    # above; this never reorders or mutates candidates.
    attach_economics(session, result)
    return result


def opportunity_to_dict(item: OpportunityItem) -> dict[str, Any]:
    """JSON-safe projection. Floats already; dates → ISO strings."""
    return {
        "observation_id":    item.observation_id,
        "underlying":        item.underlying,
        "rule_id":           item.rule_id,
        "option_symbol":     item.option_symbol,
        "expiry":            item.expiry.isoformat() if item.expiry else None,
        "strike":            item.strike,
        "option_type":       item.option_type,
        "side":              item.side,
        "run_date":          item.run_date.isoformat() if item.run_date else None,
        "bias":              item.bias,
        "directional_view":  item.directional_view,
        "risk_profile":      item.risk_profile,
        "score":             round(item.score, 4),
        "composite_score":   round(item.composite_score, 4),
        "ranking_breakdown": {
            "score":     round(item.score, 4),
            "freshness": round(item.freshness, 4),
            "liquidity": round(item.liquidity_score, 4),
            "iv_fit":    round(item.iv_fit, 4),
            "event":     round(item.event_boost, 4),
        },
        "would_trade":       item.would_trade,
        "qualified":         item.qualified,
        # Hybrid (Phase 1) — family tagging for the dual-lane UI.
        "family":            item.family,
        "engine_compatible": item.engine_compatible,
        "above_floor":       item.above_floor,
        "dte":               item.dte,
        "earnings_between":  item.earnings_between,
        "liquidity_tier":    item.liquidity_tier,
        "iv_rank":           item.iv_rank,
        "atm_iv":            item.atm_iv,
        "premium_tier":      item.ivt_premium_tier,
        "bid":               item.bid,
        "ask":               item.ask,
        "mid":               item.mid,
        "spread":            item.spread,
        "open_interest":     item.open_interest,
        "volume":            item.volume,
        "delta":             item.delta,
        "gamma":             item.gamma,
        "theta":             item.theta,
        "vega":              item.vega,
        "iv":                item.iv,
        "quote_age_seconds": item.quote_age_seconds,
        "provider":          item.provider,
        "rationale_points":  item.rationale_points,
        "template_name":     item.template_name,
        # Phase B6 — explainability metadata for the educational drawer.
        "why_emitted":           item.why_emitted,
        "triggering_rule":       item.triggering_rule,
        "rejected_alternatives": item.rejected_alternatives,
        "strategy_fit_reason":   item.strategy_fit_reason,
        "iv_fit_reason":         item.iv_fit_reason,
        "dte_fit_reason":        item.dte_fit_reason,
        "liquidity_fit_reason":  item.liquidity_fit_reason,
        # Phase B7 — catalyst metadata for the catalyst chip + educational
        # drawer "Why this catalyst matters" section. NULL when no
        # named macro event sits inside the option's DTE window.
        "earliest_event_date":
            item.earliest_event_date.isoformat()
            if item.earliest_event_date else None,
        "earliest_event_type":       item.earliest_event_type,
        "earliest_event_importance": item.earliest_event_importance,
        "event_days_away":           item.event_days_away,
        "catalyst_title":            item.catalyst_title,
        "catalyst_explanation":      item.catalyst_explanation,
        # Phase C Stage 2B — economics derived from persisted legs.
        # None until legs exist + are complete + computable. POP reserved.
        "economics":                 item.economics,
    }
