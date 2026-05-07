"""Concrete agents."""

from .trade_quality import TradeQualityAgent
from .risk import RiskAgent
from .exit_analysis import ExitAnalysisAgent
from .signal_validation import SignalValidationAgent

ALL_AGENTS = (
    TradeQualityAgent(),
    RiskAgent(),
    ExitAnalysisAgent(),
    SignalValidationAgent(),
)

__all__ = (
    "ALL_AGENTS",
    "TradeQualityAgent",
    "RiskAgent",
    "ExitAnalysisAgent",
    "SignalValidationAgent",
)
