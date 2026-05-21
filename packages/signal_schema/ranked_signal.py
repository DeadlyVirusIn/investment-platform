"""RankedSignal — output of the Ensemble Ranker."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from packages.signal_schema.signal import Signal


class RankedSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str
    symbol: str
    score: float
    contributing: list[Signal]        # all signals that rolled up into this rank
