"""CANDIDATE context labels — evaluated but not live."""

from __future__ import annotations

from dataclasses import dataclass

LOGIC_VERSION = "v0.1.0"


@dataclass(frozen=True)
class CandidateContext:
    backwardation_flag: bool | None
    logic_version: str


def classify_backwardation(ts_ratio: float | None) -> CandidateContext:
    """CANDIDATE. Phase X2 FAILED — kept for shadow evaluation only."""
    flag = None if ts_ratio is None else ts_ratio > 1
    return CandidateContext(
        backwardation_flag=flag,
        logic_version=LOGIC_VERSION,
    )
