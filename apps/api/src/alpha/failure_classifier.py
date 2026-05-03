"""Deterministic failure classifier for losing paper trades."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FailureAnalysis:
    trade_id: str
    failure_reasons: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    version: str = "failure-v1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "failure_reasons": list(self.failure_reasons),
            "summary": self.summary,
            "version": self.version,
        }


def classify_failure(
    *,
    trade_id: str,
    net_ret_pct: float,
    regime_at_entry: str,
    data_confidence: float | None,
    catalyst_policy: str | None,
    days_to_earnings: int | None,
    entry_quality_score: float | None,
    max_adverse: float | None,
    max_favorable: float | None,
    concentration_at_entry: float | None = None,
    version: str = "failure-v1.0.0",
) -> FailureAnalysis:
    """Return multi-reason classification. Empty reasons list if not a loss."""
    if net_ret_pct is None or net_ret_pct >= 0:
        return FailureAnalysis(trade_id=trade_id, version=version,
                                 summary="not a loss")

    reasons: list[dict[str, Any]] = []

    # Bad timing — adverse move immediately after entry
    if entry_quality_score is not None and entry_quality_score < 0.5:
        reasons.append({
            "reason": "bad_timing",
            "confidence": round(min(1.0, (0.5 - entry_quality_score) * 2), 4),
        })

    # Bad regime — stress regime → loss likelihood elevated
    if regime_at_entry == "stress":
        reasons.append({"reason": "bad_regime", "confidence": 0.6})

    # Catalyst ignored — earnings within 2 days
    if days_to_earnings is not None and 0 <= days_to_earnings <= 2:
        reasons.append({
            "reason": "catalyst_ignored", "confidence": 0.75,
        })
    elif catalyst_policy in {"block_new_entry", "watch_only"}:
        reasons.append({"reason": "catalyst_ignored", "confidence": 0.85})

    # Data issue
    if data_confidence is not None and data_confidence < 0.4:
        reasons.append({
            "reason": "data_issue",
            "confidence": round(min(1.0, (0.4 - data_confidence) * 2.5), 4),
        })

    # Exit issue — MFE > 2% but net < 0, i.e. trade was up but round-tripped
    if (max_favorable is not None and max_favorable > 0.02
            and net_ret_pct < 0):
        reasons.append({"reason": "exit_issue", "confidence": 0.7})

    # Risk concentration
    if (concentration_at_entry is not None
            and concentration_at_entry > 0.4):
        reasons.append({
            "reason": "risk_concentration", "confidence": 0.55,
        })

    # Bad signal — none of the above strong
    if not reasons:
        reasons.append({"reason": "normal_loss", "confidence": 0.5})

    summary = _summarize(net_ret_pct, reasons,
                          regime_at_entry, days_to_earnings)
    return FailureAnalysis(
        trade_id=trade_id,
        failure_reasons=reasons,
        summary=summary,
        version=version,
    )


def _summarize(
    net_ret_pct: float, reasons: list[dict[str, Any]],
    regime: str, d_earn: int | None,
) -> str:
    top = reasons[0]["reason"] if reasons else "normal_loss"
    fragments: list[str] = [
        f"Loss {net_ret_pct:.2%}.",
        f"Likely root cause: {top}.",
    ]
    if regime == "stress":
        fragments.append("Stress regime in effect.")
    if d_earn is not None and 0 <= d_earn <= 2:
        fragments.append(f"Earnings {d_earn} day(s) away.")
    return " ".join(fragments)
