"""Phase L worker integration — paper-trade -> envelope helper.

Resolves the engine source row (CandidateIdea for replay paths,
Recommendation for live paths) attached to a paper_trade, builds a
DecisionContext, and runs the envelope generator.

CRITICAL CONTRACT:
  * Never raises out of this module — every exception is swallowed
    and returned as `None` so the caller's trade flow continues.
  * Returns (envelope_or_none, source_kind, reason) where:
      - source_kind ∈ {"candidate_idea", "recommendation", "unknown"}
      - reason is a short structured string for logs (not user-facing)
  * Honest absence: if features unavailable, returns None envelope.
    The caller MUST NOT fabricate a substitute.

Live-path coverage today: Recommendation rows do not carry the
factor_breakdown + regime_snapshot bundle the generator needs.
Coverage will lift when a feature-payload surface lands. Until then
live trades get None envelopes — Decision Detail surfaces
incomplete_lifecycle on those, which is the truthful state.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Mapping, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import CandidateIdea, PaperTrade, Recommendation
from apps.api.src.reasoning.catalyst_substrate import lookup_catalysts
from apps.api.src.reasoning.envelope import (
    EnvelopeSource, ReasoningEnvelope,
)
from apps.api.src.reasoning.generator import (
    DecisionContext, generate_envelope_detailed,
)
from apps.api.src.reasoning.recommendation_bridge import (
    assemble_features_from_recommendation,
)


GenResult = Tuple[Optional[ReasoningEnvelope], str, str]


def _resolve_source(
    session: Session, trade: PaperTrade, as_of: Optional[dt.date],
) -> Tuple[str, Optional[Mapping[str, Any]], Optional[Mapping[str, Any]]]:
    """Return (source_kind, factor_breakdown, regime_snapshot).

    Looks up the engine source row. Source_kind = "unknown" when no
    row resolvable.
    """
    if trade.recommendation_id is not None:
        rec = session.get(Recommendation, trade.recommendation_id)
        if rec is None:
            return "unknown", None, None
        # Build factor_breakdown + regime_snapshot from
        # recommendation_evidence rows. Honest absence if none.
        factor, regime = assemble_features_from_recommendation(
            session, trade.recommendation_id,
        )
        return "recommendation", factor, regime

    if as_of is not None:
        cand = session.scalars(
            select(CandidateIdea)
            .where(
                CandidateIdea.asset_id == trade.asset_id,
                CandidateIdea.as_of_date == as_of,
                CandidateIdea.status == "accepted",
            )
            .order_by(CandidateIdea.created_at.desc())
            .limit(1)
        ).first()
        if cand is None:
            return "unknown", None, None
        return "candidate_idea", cand.factor_breakdown, cand.regime_snapshot

    return "unknown", None, None


def _dec(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def generate_envelope_for_paper_trade(
    session: Session,
    paper_trade_id: str,
    *,
    as_of: Optional[dt.date] = None,
) -> GenResult:
    """Resolve features, run generator, return envelope or honest None.

    Never raises. Designed to be safe to call inside the worker hot path.
    """
    try:
        trade = session.get(PaperTrade, paper_trade_id)
        if trade is None:
            return None, "unknown", "trade_not_found"

        source_kind, factor, regime = _resolve_source(session, trade, as_of)
        if factor is None and regime is None:
            return None, source_kind, "features_unavailable"

        # Pull realized_vol_20d from regime snapshot if present.
        realized_vol = None
        if isinstance(regime, dict):
            realized_vol = _dec(regime.get("realized_vol_20d"))

        envelope_source = (
            EnvelopeSource.REPLAY if as_of is not None else EnvelopeSource.LIVE
        )

        # Catalyst substrate lookup — pure DB read; returns False/False
        # on any error. Window anchored on the trade's fill date.
        catalyst = lookup_catalysts(
            session,
            asset_id=trade.asset_id,
            as_of=trade.fill_ts.date(),
        )

        ctx = DecisionContext(
            side=trade.side,
            asset_class="equity",  # paper_trade is equity-only today
            factor_breakdown=factor,
            regime_snapshot=regime,
            fill_price=_dec(trade.fill_price),
            realized_vol_20d=realized_vol,
            source=envelope_source,
            generated_at=trade.fill_ts,
            catalyst_proximate_macro=catalyst.proximate_macro,
            catalyst_proximate_earnings=catalyst.proximate_earnings,
        )
        result = generate_envelope_detailed(ctx)
        if result.envelope is None:
            # Surface the discrete generator-side reason for observability.
            return None, source_kind, result.none_reason or "generator_returned_none"
        return result.envelope, source_kind, "ok"

    except Exception as exc:
        logger.warning(
            "envelope generation failed for trade {}: {}",
            paper_trade_id, exc,
        )
        return None, "unknown", f"exception:{type(exc).__name__}"
