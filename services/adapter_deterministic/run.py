"""DeterministicAdapter — wraps existing `generate_candidates`.

NO logic changes. Pure transformation layer from CandidateRow →
signal_schema.Signal. Golden-tested against the underlying function.

Maps:
  - CandidateRow.action == "Buy"  → direction="long"
  - CandidateRow.action == "Sell" → direction="short"
  - CandidateRow.action == "Trim" → direction="short" (reducing exposure)
  - CandidateRow.action == "Hold" → direction="neutral"
  - anything else / None          → dropped (not emitted)

signal_strength = |composite_score| clipped to [0, 1]
confidence      = confidence/100 clipped to [0, 1]
holding_period_bars = 20 (swing default — matches existing triple-barrier)
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset
from apps.api.src.domain.stock_engine.decision_engine import (
    DEFAULT_UNIVERSE,
    CandidateRow,
    generate_candidates,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION
from packages.signal_schema.signal import (
    DIRECTION_LONG,
    DIRECTION_NEUTRAL,
    DIRECTION_SHORT,
    Direction,
    Signal,
)

STRATEGY_ID = "deterministic_v1"
MODEL_FAMILY = "deterministic"
FEATURES_VERSION = "factor_snapshot_v1"
DEFAULT_HOLDING_BARS = 20


def _direction_from(action: str | None) -> Direction | None:
    if action == "Buy":
        return DIRECTION_LONG
    if action in ("Sell", "Trim"):
        return DIRECTION_SHORT
    if action == "Hold":
        return DIRECTION_NEUTRAL
    return None


def _clip_unit(v: Decimal | float | int | None) -> Decimal:
    if v is None:
        return Decimal("0")
    d = Decimal(str(v)) if not isinstance(v, Decimal) else v
    if d < 0:
        d = -d     # signal_strength is magnitude; sign captured by direction
    if d > 1:
        return Decimal("1")
    return d.quantize(Decimal("0.0001"))


def _confidence_from(raw: Decimal | float | None) -> Decimal:
    """confidence column in candidate_idea is 0..100 scale."""
    if raw is None:
        return Decimal("0")
    v = Decimal(str(raw)) / Decimal("100")
    if v < 0:
        v = Decimal("0")
    if v > 1:
        v = Decimal("1")
    return v.quantize(Decimal("0.0001"))


class DeterministicAdapter:
    strategy_id: str = STRATEGY_ID
    model_family: str = MODEL_FAMILY
    model_version: str = MODEL_VERSION
    features_version: str = FEATURES_VERSION

    def generate_signals(
        self,
        session: Session,
        as_of: dt.date,
        universe_name: str = DEFAULT_UNIVERSE,
    ) -> list[Signal]:
        """Call existing engine. Map accepted rows to Signals. Preserve order."""
        rows: Iterable[CandidateRow] = generate_candidates(
            session, as_of, universe_name=universe_name,
        )
        # Phase 1 scope: Buy candidates only — 1:1 shadow comparison vs
        # the existing scheduler (which only emits Buy actions). Short /
        # trim / neutral emission deferred to Phase 2.
        accepted = [
            r for r in rows
            if r.status == "accepted" and r.action == "Buy"
        ]

        # Asset lookup for symbol mapping.
        asset_ids = [r.asset_id for r in accepted]
        asset_map: dict[str, Asset] = {}
        if asset_ids:
            for a in session.scalars(
                select(Asset).where(Asset.id.in_(asset_ids))
            ):
                asset_map[a.id] = a

        now = dt.datetime.now(dt.timezone.utc)
        signals: list[Signal] = []
        for r in accepted:
            direction = _direction_from(r.action)
            if direction is None:
                continue
            asset = asset_map.get(r.asset_id)
            if asset is None:
                continue
            signals.append(Signal(
                asset_id=r.asset_id,
                symbol=asset.symbol,
                timestamp=now,
                as_of_date=as_of,
                timeframe="1d",
                strategy_id=self.strategy_id,
                model_family=self.model_family,
                model_version=self.model_version,
                features_version=self.features_version,
                signal_direction=direction,
                signal_strength=_clip_unit(r.composite_score),
                confidence=_confidence_from(r.confidence),
                holding_period_bars=DEFAULT_HOLDING_BARS,
                regime_tag=(r.regime_snapshot or {}).get("vol_regime"),
                raw_payload_ref=None,
            ))
        return signals

    def healthcheck(self) -> dict:
        return {
            "ok": True,
            "strategy_id": self.strategy_id,
            "model_family": self.model_family,
            "model_version": self.model_version,
        }
