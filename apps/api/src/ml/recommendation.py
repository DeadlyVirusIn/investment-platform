"""Deterministic recommendation text based on diagnostic inputs."""

from __future__ import annotations


def build_recommendation(
    *,
    n_rows: int,
    tier: str,
    leakage_ok: bool,
    catalyst_coverage: float,
    best_baseline_sharpe: float,
    engine_c_status: str,
    warnings: list[str],
) -> str:
    """Short human-readable next-step recommendation."""
    if not leakage_ok:
        return ("Fix leakage before anything else — all other signals "
                "are unreliable while contamination exists.")
    if n_rows == 0:
        return ("No decision_log rows yet. Run the daily paper pipeline "
                "for a few sessions before revisiting ML research.")
    if tier == "diagnostics_only":
        return ("Continue collecting data. Diagnostics only until we pass "
                "200 labelled decisions.")
    if tier == "baselines_only":
        if catalyst_coverage < 0.3:
            return ("Improve catalyst coverage (currently "
                    f"{catalyst_coverage:.0%}). Wire Finnhub / paid providers "
                    "before ML becomes useful.")
        return ("Baselines only. Focus on rule-based baselines + data "
                "quality tightening. Not enough rows for walk-forward.")
    # walk_forward_ok or rich_experiments_allowed
    if engine_c_status in {"DISABLED_INSUFFICIENT_DATA",
                            "DISABLED_LEAKAGE_RISK"}:
        return ("Engine C gating active — address blockers listed in "
                "engine_c_blockers before training.")
    if engine_c_status == "BASELINES_ONLY":
        return "Keep accumulating labelled outcomes; run baselines in shadow."
    if engine_c_status == "ADVISORY_READY":
        return ("Ready for walk-forward ML evaluation in advisory mode. "
                "Do NOT enable ML_CAN_AFFECT_TRADES yet.")
    if engine_c_status == "SHADOW_READY":
        return ("Run ML in shadow mode — ML has not beaten baselines. "
                "Collect more out-of-sample evidence.")
    if engine_c_status == "ACTIVE_CANDIDATE":
        return ("Engine C is a promotion candidate — baseline has been "
                "beaten in-sample. Stay in shadow across ≥ 1 regime cycle "
                "before promoting.")
    # Catch-all
    if best_baseline_sharpe <= 0:
        return ("Even non-ML baselines are not producing positive risk-"
                "adjusted returns. Reassess core signal before adding ML.")
    return "Continue nightly diagnostics. Advisory-only for now."
