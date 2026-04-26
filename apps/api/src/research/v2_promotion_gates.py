"""V2 promotion-trigger framework — gate evaluation.

Phase 2. Pure functions. NEVER mutates state. NEVER writes anything.
NEVER imports any execution / routing / ENGINE_B_MODE / ML / risk module.
NEVER modifies the comparison framework.

Inputs are explicit:
- `bundle`   the read-only output of `b2_v2_comparison.compute_all(...)`
- `prior_snapshots`  list of snapshot dicts (most-recent last) — see _SnapshotShape
- `governance_state` dict provided by the caller (Phase 4 snapshot job
                     will populate from settings + health probes — this
                     module does NOT query them)
- `approval_records` list of approval dicts for the snapshot under
                     evaluation (Phase 5 API will write these — this
                     module only reads them)

Spec: docs/research/V2_PROMOTION_TRIGGER_DESIGN.md (Hard Gates §).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Frozen module-level thresholds. Changing any value REQUIRES a revision-history
# entry in V2_PROMOTION_TRIGGER_DESIGN.md. No config-driven tuning.
# ---------------------------------------------------------------------------

# Gate 1
GATE1_MIN_INPUT_ROWS = 60
GATE1_MIN_DIVERGENT_ROWS = 30
GATE1_MIN_B2_FLAT_V2_LONG = 10
GATE1_MIN_OOS_DAYS = 10
FRAMEWORK_IMPLEMENTATION_DATE = date(2026, 4, 25)

# Gate 2
GATE2_VERDICT_STREAK_REQUIRED = 4
GATE2_READINESS_STREAK_REQUIRED = 2
GATE2_MIN_CONFIDENCE = 0.70

# Gate 3
GATE3_MIN_EDGE_BPS = 5.0
GATE3_MIN_CUM_DIFF_PCT = 0.5
GATE3_IMPACT_WEIGHTED_TREND_LOOKBACK = 4
GATE3_IMPACT_WEIGHTED_NOISE_BAND = 0.10  # ±10% noise tolerance

# Gate 4
GATE4_MAX_P99_DELTA_NEGATIVE_BPS = -10.0    # tail_delta_p99_bps must be ≥ this
GATE4_MAX_P95_DELTA_NEGATIVE_BPS = -5.0
GATE4_WORST5_DEEPER_FACTOR = 1.10            # V2 may be at most 10% deeper

# Gate 5
GATE5_MIN_DIRECTIONAL_EDGE_BPS = 0.0         # strict > 0
GATE5_MAX_NEUTRAL_NEG_EDGE_BPS = -2.0        # ≥ -2 bps tolerated
GATE5_REGIME_CONCENTRATION_MAX = 0.80
GATE5_STRESS_TAIL_DELTA_BPS = -10.0          # V2 stress p99 ≥ B2 stress p99 - 10

# Gate 7
GATE7_VALID_ENGINE_B_MODES = ("LEGACY", "SHADOW_COMPARE")
GATE7_HEALTHY_FETCH_HISTORY_REQUIRED = 7

# Gate 8
GATE8_APPROVAL_STALENESS_DAYS = 14


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateResult:
    """One gate's evaluation outcome.

    `passed` is the only thing the state machine consumes. `reason`
    and `details` are surfaced in UI + audit.
    """
    name: str
    passed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


def _r(
    name: str,
    passed: bool,
    reason: str,
    **details: Any,
) -> GateResult:
    return GateResult(name=name, passed=passed, reason=reason, details=details)


# ---------------------------------------------------------------------------
# Snapshot shape (for type-hinting the prior_snapshots input)
# ---------------------------------------------------------------------------

# A prior_snapshot dict is expected to contain at minimum:
#   as_of_date            date | str (ISO)
#   state                 str
#   verdict               dict — the verdict block from comparison bundle
#   metrics               dict — divergence_metrics output
#   tail                  dict — tail_comparison output
#   readiness             str  — same value as verdict.readiness
#   comparison_fetch_ok   bool — set by snapshot job; True if comparison
#                                bundle was fetched without error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_date(d: Any) -> date | None:
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        try:
            return date.fromisoformat(d)
        except ValueError:
            return None
    return None


def _to_datetime(d: Any) -> datetime | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    if isinstance(d, date):
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if isinstance(d, str):
        try:
            dt = datetime.fromisoformat(d)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _f(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------------------
# Gate 1 — Minimum Sample
# ---------------------------------------------------------------------------

def evaluate_gate_1(
    bundle: dict,
    *,
    snapshot_as_of_date: date,
) -> GateResult:
    """Sample size gates (sub-conditions all required)."""
    n_input = int(bundle.get("n_input_rows") or 0)
    n_div = int(bundle.get("n_divergent_rows") or 0)
    metrics = bundle.get("metrics") or {}
    n_b2flat_v2long = int(metrics.get("n_b2_flat_v2_long") or 0)
    oos_days = max(
        0,
        (snapshot_as_of_date - FRAMEWORK_IMPLEMENTATION_DATE).days,
    )

    fails: list[str] = []
    if n_input < GATE1_MIN_INPUT_ROWS:
        fails.append(f"n_input_rows={n_input} < {GATE1_MIN_INPUT_ROWS}")
    if n_div < GATE1_MIN_DIVERGENT_ROWS:
        fails.append(f"n_divergent_rows={n_div} < {GATE1_MIN_DIVERGENT_ROWS}")
    if n_b2flat_v2long < GATE1_MIN_B2_FLAT_V2_LONG:
        fails.append(
            f"n_b2_flat_v2_long={n_b2flat_v2long} "
            f"< {GATE1_MIN_B2_FLAT_V2_LONG}"
        )
    if oos_days < GATE1_MIN_OOS_DAYS:
        fails.append(
            f"oos_days_since_implementation={oos_days} "
            f"< {GATE1_MIN_OOS_DAYS}"
        )

    return _r(
        "gate_1_minimum_sample",
        passed=not fails,
        reason="; ".join(fails) if fails else "all sample-size sub-conditions met",
        n_input_rows=n_input,
        n_divergent_rows=n_div,
        n_b2_flat_v2_long=n_b2flat_v2long,
        oos_days=oos_days,
    )


# ---------------------------------------------------------------------------
# Gate 2 — Verdict Stability
# ---------------------------------------------------------------------------

def _trailing_streak(
    snapshots: list[dict],
    *,
    field_path: tuple[str, ...],
    target: str,
) -> int:
    """Count consecutive trailing snapshots whose nested field == target."""
    streak = 0
    for snap in reversed(snapshots):
        cur: Any = snap
        for k in field_path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(k)
        if cur == target:
            streak += 1
        else:
            break
    return streak


def evaluate_gate_2(
    bundle: dict,
    *,
    prior_snapshots: list[dict],
) -> GateResult:
    """Verdict stability: streaks + current confidence.

    Streaks are computed against `prior_snapshots + [current_synthetic]`
    where `current_synthetic` is built from the bundle's verdict so that
    the current snapshot contributes to the streak it must satisfy.
    """
    verdict = bundle.get("verdict") or {}
    current_verdict = verdict.get("verdict")
    current_readiness = verdict.get("readiness")
    confidence = _f(verdict.get("confidence"))

    history = list(prior_snapshots) + [
        {"verdict": {"verdict": current_verdict, "readiness": current_readiness}}
    ]
    verdict_streak = _trailing_streak(
        history, field_path=("verdict", "verdict"), target="V2_BETTER",
    )
    readiness_streak = _trailing_streak(
        history,
        field_path=("verdict", "readiness"),
        target="STRONG_CANDIDATE",
    )

    fails: list[str] = []
    if verdict_streak < GATE2_VERDICT_STREAK_REQUIRED:
        fails.append(
            f"verdict_streak={verdict_streak} "
            f"< required {GATE2_VERDICT_STREAK_REQUIRED}"
        )
    if readiness_streak < GATE2_READINESS_STREAK_REQUIRED:
        fails.append(
            f"readiness_streak={readiness_streak} "
            f"< required {GATE2_READINESS_STREAK_REQUIRED}"
        )
    if confidence is None or confidence < GATE2_MIN_CONFIDENCE:
        fails.append(
            f"confidence={confidence!r} < {GATE2_MIN_CONFIDENCE}"
        )

    return _r(
        "gate_2_verdict_stability",
        passed=not fails,
        reason="; ".join(fails) if fails else "verdict / readiness / confidence stable",
        verdict_streak=verdict_streak,
        readiness_streak=readiness_streak,
        confidence=confidence,
        current_verdict=current_verdict,
        current_readiness=current_readiness,
    )


# ---------------------------------------------------------------------------
# Gate 3 — Edge Quality
# ---------------------------------------------------------------------------

def _impact_weighted_trend(
    prior_snapshots: list[dict],
    current_iwe: float,
    *,
    lookback: int,
    noise_band: float,
) -> tuple[bool, str, list[float | None]]:
    """Trend non-decreasing OR within ±noise_band of prior peak."""
    series: list[float | None] = []
    for snap in prior_snapshots[-(lookback - 1):]:
        m = (snap.get("metrics") or {})
        series.append(_f(m.get("impact_weighted_edge")))
    series.append(current_iwe)

    finite = [v for v in series if v is not None]
    if len(finite) < 2:
        # Not enough history → trend gate passes if current is positive
        return True, "insufficient history → vacuously stable", series

    # Non-decreasing pairwise check
    non_decreasing = all(
        finite[i] >= finite[i - 1] - 1e-12 for i in range(1, len(finite))
    )
    if non_decreasing:
        return True, "non-decreasing", series

    # Otherwise — within +noise_band of prior max
    prior_max = max(finite[:-1])
    if prior_max <= 0:
        # Prior all ≤ 0 — current positive trivially passes
        if finite[-1] >= 0:
            return True, "prior series ≤ 0 and current ≥ 0", series
        return False, f"declining: current {finite[-1]:.4f} < prior_max {prior_max:.4f}", series

    threshold = prior_max * (1 - noise_band)
    if finite[-1] >= threshold:
        return True, (
            f"within noise band: current {finite[-1]:.4f} ≥ "
            f"{(1 - noise_band):.2f} × prior_max {prior_max:.4f}"
        ), series
    return False, (
        f"declining beyond noise band: current {finite[-1]:.4f} < "
        f"{(1 - noise_band):.2f} × prior_max {prior_max:.4f}"
    ), series


def evaluate_gate_3(
    bundle: dict,
    *,
    prior_snapshots: list[dict],
) -> GateResult:
    metrics = bundle.get("metrics") or {}
    edge_bps = _f(metrics.get("avg_return_diff_1d_bps"))
    cum_diff = _f(metrics.get("cumulative_return_diff_pct"))
    iwe = _f(metrics.get("impact_weighted_edge"))

    fails: list[str] = []
    if edge_bps is None or edge_bps < GATE3_MIN_EDGE_BPS:
        fails.append(f"edge_bps={edge_bps!r} < {GATE3_MIN_EDGE_BPS}")
    if cum_diff is None or cum_diff < GATE3_MIN_CUM_DIFF_PCT:
        fails.append(
            f"cumulative_return_diff_pct={cum_diff!r} < {GATE3_MIN_CUM_DIFF_PCT}"
        )
    if iwe is None or iwe <= 0:
        fails.append(f"impact_weighted_edge={iwe!r} ≤ 0")

    if iwe is not None:
        ok, why, series = _impact_weighted_trend(
            prior_snapshots, iwe,
            lookback=GATE3_IMPACT_WEIGHTED_TREND_LOOKBACK,
            noise_band=GATE3_IMPACT_WEIGHTED_NOISE_BAND,
        )
    else:
        ok, why, series = False, "impact_weighted_edge missing", []
    if not ok:
        fails.append(f"impact_weighted_trend: {why}")

    return _r(
        "gate_3_edge_quality",
        passed=not fails,
        reason="; ".join(fails) if fails else (
            f"edge {edge_bps:.2f} bps, cum {cum_diff:.3f}%, "
            f"iwe {iwe:.4f}, trend ok"
        ),
        edge_bps=edge_bps,
        cumulative_return_diff_pct=cum_diff,
        impact_weighted_edge=iwe,
        impact_weighted_series=series,
        impact_weighted_trend_reason=why,
    )


# ---------------------------------------------------------------------------
# Gate 4 — Tail Risk
# ---------------------------------------------------------------------------

def _worst5_rank_aligned_check(
    b2_w5: list[float],
    v2_w5: list[float],
    *,
    deeper_factor: float,
) -> tuple[bool, list[dict]]:
    """V2[i] may be at most `deeper_factor`× as deep as B2[i] (rank-aligned).

    Both lists are sorted ascending (most-negative first). Comparison is
    pairwise on rank. Pairs are skipped when neither side has a loss
    (both ≥ 0). When B2 has no loss at rank i but V2 does, that pair
    fails (V2 introduces a loss B2 doesn't have).
    """
    rows: list[dict] = []
    ok = True
    n = min(len(b2_w5), len(v2_w5))
    for i in range(n):
        b2v = float(b2_w5[i])
        v2v = float(v2_w5[i])
        # Pair skip: both non-loss
        if b2v >= 0 and v2v >= 0:
            rows.append(
                {"rank": i, "b2": b2v, "v2": v2v, "passed": True,
                 "reason": "neither has a loss at this rank"}
            )
            continue
        if b2v >= 0 and v2v < 0:
            ok = False
            rows.append(
                {"rank": i, "b2": b2v, "v2": v2v, "passed": False,
                 "reason": "V2 loss where B2 has none"}
            )
            continue
        if v2v >= 0 and b2v < 0:
            rows.append(
                {"rank": i, "b2": b2v, "v2": v2v, "passed": True,
                 "reason": "V2 has no loss; B2 does → V2 strictly better"}
            )
            continue
        # Both negative — V2 may be at most `deeper_factor`× as deep.
        # i.e. V2 ≥ B2 × deeper_factor (more-negative is deeper).
        threshold = b2v * deeper_factor
        passed = v2v >= threshold - 1e-12
        rows.append(
            {"rank": i, "b2": b2v, "v2": v2v, "passed": passed,
             "threshold": round(threshold, 4),
             "reason": (
                 f"V2 {v2v:.2f} ≥ {deeper_factor:.2f}× B2 ({threshold:.2f})"
                 if passed else
                 f"V2 {v2v:.2f} < {deeper_factor:.2f}× B2 ({threshold:.2f})"
             )}
        )
        if not passed:
            ok = False
    return ok, rows


def evaluate_gate_4(bundle: dict) -> GateResult:
    verdict = bundle.get("verdict") or {}
    tail = bundle.get("tail") or {}
    guard = bool(verdict.get("tail_guard_triggered"))
    p99_d = _f(tail.get("tail_delta_p99_bps"))
    p95_d = _f(tail.get("tail_delta_p95_bps"))
    b2_w5 = list((tail.get("b2") or {}).get("worst_5_losses_bps") or [])
    v2_w5 = list((tail.get("v2") or {}).get("worst_5_losses_bps") or [])

    fails: list[str] = []
    if guard:
        fails.append("tail_guard_triggered=true")
    if p99_d is not None and p99_d < GATE4_MAX_P99_DELTA_NEGATIVE_BPS:
        fails.append(
            f"tail_delta_p99_bps={p99_d:.2f} < {GATE4_MAX_P99_DELTA_NEGATIVE_BPS}"
        )
    if p95_d is not None and p95_d < GATE4_MAX_P95_DELTA_NEGATIVE_BPS:
        fails.append(
            f"tail_delta_p95_bps={p95_d:.2f} < {GATE4_MAX_P95_DELTA_NEGATIVE_BPS}"
        )

    w5_ok, w5_rows = _worst5_rank_aligned_check(
        b2_w5, v2_w5, deeper_factor=GATE4_WORST5_DEEPER_FACTOR,
    )
    if not w5_ok:
        fails.append("worst_5_rank_aligned: V2 materially deeper at one or more ranks")

    return _r(
        "gate_4_tail_risk",
        passed=not fails,
        reason="; ".join(fails) if fails else "tail risk within bounds",
        tail_guard_triggered=guard,
        tail_delta_p99_bps=p99_d,
        tail_delta_p95_bps=p95_d,
        worst_5_rows=w5_rows,
    )


# ---------------------------------------------------------------------------
# Gate 5 — Regime Validation
# ---------------------------------------------------------------------------

def _regime_concentration(by_regime: dict) -> tuple[float | None, dict[str, float]]:
    """Compute max(regime_cum / sum_cum) for regimes whose cum_diff > 0.

    Returns (max_share, per_regime_share). When sum_cum ≤ 0, returns
    (None, {}) — concentration check is N-A, gate handles separately.
    """
    contribs: dict[str, float] = {}
    for regime, m in (by_regime or {}).items():
        if not isinstance(m, dict):
            continue
        v = _f(m.get("cumulative_return_diff_pct"))
        if v is not None and v > 0:
            contribs[regime] = v
    total = sum(contribs.values())
    if total <= 0:
        return None, {}
    shares = {r: v / total for r, v in contribs.items()}
    return max(shares.values()), shares


def evaluate_gate_5(bundle: dict) -> GateResult:
    by_regime = bundle.get("metrics_by_regime") or {}
    directional = by_regime.get("directional") or {}
    neutral = by_regime.get("neutral") or {}
    stress = by_regime.get("stress") or {}

    fails: list[str] = []

    dir_edge = _f(directional.get("avg_return_diff_1d_bps"))
    if dir_edge is None or dir_edge <= GATE5_MIN_DIRECTIONAL_EDGE_BPS:
        fails.append(
            f"directional edge_bps={dir_edge!r} ≤ {GATE5_MIN_DIRECTIONAL_EDGE_BPS}"
        )

    neu_edge = _f(neutral.get("avg_return_diff_1d_bps"))
    # Empty neutral bucket (n=0, edge=None) is acceptable
    if neu_edge is not None and neu_edge < GATE5_MAX_NEUTRAL_NEG_EDGE_BPS:
        fails.append(
            f"neutral edge_bps={neu_edge!r} < {GATE5_MAX_NEUTRAL_NEG_EDGE_BPS}"
        )

    # Stress-tail proxy:
    # bundle does NOT currently expose tail_by_regime; per Phase 2 spec
    # we compute a defensible proxy from available stress-bucket fields.
    # Proxy: V2 must NOT have introduced new losses on stress days that
    # average more than 100 bps deeper than B2's stress-day baseline.
    # When stress bucket is empty (n=0), this sub-condition is vacuously
    # passing (no stress-day evidence to indict V2).
    stress_n = int(stress.get("n_divergent_days") or 0)
    stress_new_loss = _f(stress.get("new_losses_avg_bps"))
    stress_avoided = _f(stress.get("avoided_losses_avg_bps"))
    stress_proxy_ok = True
    stress_proxy_reason = "stress bucket empty → vacuously passing"
    if stress_n > 0 and stress_new_loss is not None:
        # If V2's added losses on stress days exceed avoided losses by
        # more than abs(GATE5_STRESS_TAIL_DELTA_BPS), tail in stress is worse.
        net = stress_new_loss - (stress_avoided or 0.0)
        if net > abs(GATE5_STRESS_TAIL_DELTA_BPS):
            stress_proxy_ok = False
            stress_proxy_reason = (
                f"stress new_losses {stress_new_loss:.2f} bps − "
                f"avoided {stress_avoided or 0.0:.2f} bps = net {net:.2f} bps "
                f"> {abs(GATE5_STRESS_TAIL_DELTA_BPS)} bps"
            )
        else:
            stress_proxy_reason = (
                f"stress net loss-introduction {net:.2f} bps "
                f"≤ {abs(GATE5_STRESS_TAIL_DELTA_BPS)} bps"
            )
    if not stress_proxy_ok:
        fails.append(f"stress_tail: {stress_proxy_reason}")

    # Concentration check
    max_share, shares = _regime_concentration(by_regime)
    conc_reason = "no regime contributes positive cumulative diff"
    conc_ok = True
    if max_share is not None:
        conc_ok = max_share <= GATE5_REGIME_CONCENTRATION_MAX
        conc_reason = (
            f"max_regime_share={max_share:.3f} ≤ "
            f"{GATE5_REGIME_CONCENTRATION_MAX}"
            if conc_ok else
            f"max_regime_share={max_share:.3f} > "
            f"{GATE5_REGIME_CONCENTRATION_MAX}"
        )
        if not conc_ok:
            fails.append(f"regime concentration: {conc_reason}")

    return _r(
        "gate_5_regime_validation",
        passed=not fails,
        reason="; ".join(fails) if fails else "regime conditions met",
        directional_edge_bps=dir_edge,
        neutral_edge_bps=neu_edge,
        stress_n_divergent_days=stress_n,
        stress_proxy_reason=stress_proxy_reason,
        regime_concentration_shares=shares,
        regime_concentration_max=max_share,
        regime_concentration_reason=conc_reason,
    )


# ---------------------------------------------------------------------------
# Gate 6 — Stability
# ---------------------------------------------------------------------------

def evaluate_gate_6(bundle: dict) -> GateResult:
    stab = bundle.get("stability") or {}
    fh = stab.get("first_half_vs_second_half") or {}
    last_30 = stab.get("last_30_vs_prior_30") or {}

    fh_e = _f(fh.get("first_half_edge_bps"))
    sh_e = _f(fh.get("second_half_edge_bps"))
    trend = last_30.get("trend")

    fails: list[str] = []
    if fh_e is None or fh_e <= 0:
        fails.append(f"first_half_edge_bps={fh_e!r} ≤ 0")
    if sh_e is None or sh_e <= 0:
        fails.append(f"second_half_edge_bps={sh_e!r} ≤ 0")
    if trend in ("DECLINING", "INSUFFICIENT", None):
        fails.append(f"last_30_vs_prior_30.trend={trend!r}")

    return _r(
        "gate_6_stability",
        passed=not fails,
        reason="; ".join(fails) if fails else "both halves positive; trend healthy",
        first_half_edge_bps=fh_e,
        second_half_edge_bps=sh_e,
        last_30_trend=trend,
    )


# ---------------------------------------------------------------------------
# Gate 7 — No Conflict With Governance
# ---------------------------------------------------------------------------

def evaluate_gate_7(
    *,
    governance_state: dict,
    prior_snapshots: list[dict],
) -> GateResult:
    """Caller supplies governance_state — this module never imports the
    underlying systems. Required keys:
        engine_b_mode             str
        ml_advisory_only          bool
        comparison_framework_healthy bool   (current snapshot health)
    Optional informational:
        b2_promotion_paused       bool
    """
    mode = governance_state.get("engine_b_mode")
    ml_advisory = bool(governance_state.get("ml_advisory_only", False))
    healthy_now = bool(governance_state.get("comparison_framework_healthy", False))

    fails: list[str] = []
    if mode not in GATE7_VALID_ENGINE_B_MODES:
        fails.append(
            f"engine_b_mode={mode!r} not in {GATE7_VALID_ENGINE_B_MODES}"
        )
    if not ml_advisory:
        fails.append("ml_advisory_only=False (ML must remain advisory)")

    # Trailing comparison-framework health: last N snapshots' comparison_fetch_ok
    fetch_history = [
        bool(s.get("comparison_fetch_ok"))
        for s in prior_snapshots[-(GATE7_HEALTHY_FETCH_HISTORY_REQUIRED - 1):]
    ]
    fetch_history.append(healthy_now)
    history_n = len(fetch_history)
    if history_n < GATE7_HEALTHY_FETCH_HISTORY_REQUIRED:
        # Insufficient history yet — accept current health as sufficient
        history_ok = healthy_now
        history_reason = (
            f"only {history_n} fetch-history rows available; "
            f"current health = {healthy_now}"
        )
    else:
        history_ok = all(fetch_history)
        history_reason = (
            "all comparison fetches healthy"
            if history_ok else
            "comparison fetch failed within trailing window"
        )
    if not history_ok:
        fails.append(f"comparison framework: {history_reason}")

    b2_paused = bool(governance_state.get("b2_promotion_paused", False))
    return _r(
        "gate_7_governance",
        passed=not fails,
        reason="; ".join(fails) if fails else "governance clean",
        engine_b_mode=mode,
        ml_advisory_only=ml_advisory,
        comparison_fetch_ok_history=fetch_history,
        comparison_fetch_history_reason=history_reason,
        b2_promotion_paused=b2_paused,  # informational only
    )


# ---------------------------------------------------------------------------
# Gate 8 — Operator Approval
# ---------------------------------------------------------------------------

def evaluate_gate_8(
    *,
    snapshot_as_of_date: date,
    snapshot_id: int | None,
    approval_records: list[dict],
) -> GateResult:
    """Approval row exists, addresses this snapshot, fresh, not rescinded.

    Each approval_record dict must have:
        decision     "APPROVE" | "RESCIND"
        approver     str
        approved_at  datetime | str (ISO)
        snapshot_id  int   (must match the snapshot under evaluation)
    """
    rows_for_snap = [
        r for r in approval_records
        if r.get("snapshot_id") == snapshot_id
    ]

    rescinded = any(r.get("decision") == "RESCIND" for r in rows_for_snap)
    if rescinded:
        return _r(
            "gate_8_operator_approval",
            passed=False,
            reason="approval rescinded",
            n_records=len(rows_for_snap),
        )

    cutoff_dt = datetime(
        snapshot_as_of_date.year,
        snapshot_as_of_date.month,
        snapshot_as_of_date.day,
        tzinfo=timezone.utc,
    ) - timedelta(days=GATE8_APPROVAL_STALENESS_DAYS)

    fresh_approvals = []
    for r in rows_for_snap:
        if r.get("decision") != "APPROVE":
            continue
        approver = (r.get("approver") or "").strip()
        if not approver:
            continue
        approved_at = _to_datetime(r.get("approved_at"))
        if approved_at is None:
            continue
        if approved_at < cutoff_dt:
            continue
        fresh_approvals.append(r)

    if not fresh_approvals:
        return _r(
            "gate_8_operator_approval",
            passed=False,
            reason=(
                f"no fresh approval (≥ {snapshot_as_of_date.isoformat()} − "
                f"{GATE8_APPROVAL_STALENESS_DAYS}d) for snapshot_id={snapshot_id}"
            ),
            n_records=len(rows_for_snap),
        )

    # Use most-recent fresh approval
    approver = sorted(
        fresh_approvals,
        key=lambda r: _to_datetime(r.get("approved_at")) or cutoff_dt,
    )[-1].get("approver")
    return _r(
        "gate_8_operator_approval",
        passed=True,
        reason=f"approved by {approver}",
        n_records=len(rows_for_snap),
    )


# ---------------------------------------------------------------------------
# evaluate_all_gates
# ---------------------------------------------------------------------------

def evaluate_all_gates(
    bundle: dict,
    *,
    snapshot_as_of_date: date,
    snapshot_id: int | None = None,
    prior_snapshots: list[dict] | None = None,
    governance_state: dict | None = None,
    approval_records: list[dict] | None = None,
) -> dict[str, GateResult]:
    """Run all 8 gates; return ordered dict keyed by gate name."""
    prior = list(prior_snapshots or [])
    governance = dict(governance_state or {})
    approvals = list(approval_records or [])

    results: dict[str, GateResult] = {}
    g1 = evaluate_gate_1(bundle, snapshot_as_of_date=snapshot_as_of_date)
    results[g1.name] = g1
    g2 = evaluate_gate_2(bundle, prior_snapshots=prior)
    results[g2.name] = g2
    g3 = evaluate_gate_3(bundle, prior_snapshots=prior)
    results[g3.name] = g3
    g4 = evaluate_gate_4(bundle)
    results[g4.name] = g4
    g5 = evaluate_gate_5(bundle)
    results[g5.name] = g5
    g6 = evaluate_gate_6(bundle)
    results[g6.name] = g6
    g7 = evaluate_gate_7(
        governance_state=governance, prior_snapshots=prior,
    )
    results[g7.name] = g7
    g8 = evaluate_gate_8(
        snapshot_as_of_date=snapshot_as_of_date,
        snapshot_id=snapshot_id,
        approval_records=approvals,
    )
    results[g8.name] = g8
    return results
