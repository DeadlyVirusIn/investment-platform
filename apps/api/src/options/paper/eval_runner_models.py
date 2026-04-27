"""Phase 11O — domain models for the manual options paper evaluation
runner.

Pure dataclasses. No I/O. NEVER imports broker / live / execution
modules. NEVER imports V2 / equity / governance modules. Re-uses
LegSpec + RiskMetrics from `paper.strategies` so we do not duplicate
the defined-risk shapes.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from apps.api.src.options.paper.strategies import LegSpec, RiskMetrics


@dataclass(frozen=True)
class RunnerConfig:
    """Validated runner configuration. dry_run XOR commit must hold."""
    date: datetime.date
    underlyings: tuple[str, ...]
    strategy_filter: tuple[str, ...] | None
    dry_run: bool
    commit: bool
    max_open: int
    explain: bool
    skip_ingest: bool

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError(
                "dry_run and commit are mutually exclusive — "
                "exactly one must be True"
            )
        if not (1 <= self.max_open <= 25):
            raise ValueError(
                f"max_open out of bounds 1..25: {self.max_open}"
            )
        if not self.underlyings:
            raise ValueError("underlyings must be non-empty")


@dataclass(frozen=True)
class PlannedTrade:
    """A would-open trade. `committable` is True only when qualified
    AND no rejection reasons were captured."""
    observation_id: str
    underlying: str
    rule_id: str
    legs: tuple[LegSpec, ...]
    risk: RiskMetrics | None
    entry_credit_dollars: Decimal | None
    quote_age_max_seconds: int | None
    rejection_reasons: tuple[str, ...]
    qualified: bool

    @property
    def committable(self) -> bool:
        return (
            self.qualified
            and not self.rejection_reasons
            and self.risk is not None
            and len(self.legs) > 0
        )


@dataclass(frozen=True)
class RunnerSummary:
    config: RunnerConfig
    n_chain_inserted: int
    n_observations_total: int
    n_qualified: int
    n_planned: int
    n_planned_rejected: int
    n_existing_open_trade_dedup: int
    n_committed: int
    planned_trades: tuple[PlannedTrade, ...]
    committed_trade_ids: tuple[int, ...]
