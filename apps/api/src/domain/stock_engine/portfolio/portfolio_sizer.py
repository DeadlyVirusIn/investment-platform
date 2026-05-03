"""Deterministic position sizer for the stock engine.

Sizing formula (stated default)::

    base_weight         = 1 / MAX_POSITIONS
    per_asset_weight    = base_weight * (confidence / 100)
    per_asset_weight    = clamp(per_asset_weight, 0, MAX_POSITION_PCT)

Sector cap::

    for each sector with sum(weights) > MAX_SECTOR_PCT:
        rescale sector members so sum == MAX_SECTOR_PCT

Pure function — no DB access. Inputs come from decision engine + asset
metadata. Output = target weight vector, sector totals, and any dropped
candidates with a reason tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from apps.api.src.config import settings
from apps.api.src.domain.ml.sizing import (
    compute_ml_multiplier,
    TradeSizingLog,
)

MAX_POSITIONS = 10
MAX_POSITION_PCT = Decimal("0.30")
MAX_SECTOR_PCT = Decimal("0.50")


@dataclass
class SizingInput:
    asset_id: str
    composite_score: Decimal | None
    confidence: Decimal | None          # 0..100
    sector: str
    # SHADOW: optional ML probability; None → neutral (multiplier=1.0)
    ml_proba: Decimal | None = None
    symbol: str | None = None           # for observability only


@dataclass
class SizingResult:
    target_weights: dict[str, Decimal]                  # asset_id → weight (0..1) — PRODUCTION (deterministic)
    sector_totals: dict[str, Decimal]                   # sector → sum weights (production)
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (asset_id, reason)
    # SHADOW outputs — computed in parallel, never used by live execution
    shadow_weights: dict[str, Decimal] = field(default_factory=dict)           # post-normalization
    shadow_sector_totals: dict[str, Decimal] = field(default_factory=dict)     # post-normalization
    shadow_log: list[TradeSizingLog] = field(default_factory=list)
    shadow_sum_pre_norm: Decimal = Decimal("0")
    shadow_sum_post_norm: Decimal = Decimal("0")
    shadow_scale_factor: Decimal = Decimal("1")
    sizing_mode: str = "deterministic"   # "deterministic" | "ml_sized"


def _d(v: Decimal | float | int | None) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _clamp(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, x))


def size_positions(
    candidates: Sequence[SizingInput],
    *,
    max_positions: int = MAX_POSITIONS,
    max_position_pct: Decimal = MAX_POSITION_PCT,
    max_sector_pct: Decimal = MAX_SECTOR_PCT,
) -> SizingResult:
    if not candidates:
        return SizingResult(target_weights={}, sector_totals={})

    # Deterministic intake order: composite desc, asset_id for ties.
    sorted_cands = sorted(
        candidates,
        key=lambda c: (
            -(float(c.composite_score) if c.composite_score is not None else 0.0),
            c.asset_id,
        ),
    )

    # Respect max_positions — trim the tail deterministically.
    dropped: list[tuple[str, str]] = []
    active = sorted_cands[:max_positions]
    for c in sorted_cands[max_positions:]:
        dropped.append((c.asset_id, "max_positions_exceeded"))

    base_weight = Decimal("1") / Decimal(max_positions)
    weights: dict[str, Decimal] = {}
    for c in active:
        conf = _d(c.confidence)
        # Confidence can legitimately be 0..100; clamp just in case.
        conf = _clamp(conf, Decimal("0"), Decimal("100"))
        w = base_weight * (conf / Decimal("100"))
        w = _clamp(w, Decimal("0"), max_position_pct)
        if w <= 0:
            dropped.append((c.asset_id, "zero_weight"))
            continue
        weights[c.asset_id] = w

    # Sector cap enforcement
    sectors_by_asset: dict[str, str] = {c.asset_id: c.sector for c in active}
    sector_sums: dict[str, Decimal] = {}
    for aid, w in weights.items():
        s = sectors_by_asset.get(aid, "unknown")
        sector_sums[s] = sector_sums.get(s, Decimal("0")) + w

    for sector, total in list(sector_sums.items()):
        if total > max_sector_pct:
            scale = max_sector_pct / total
            for aid, w in list(weights.items()):
                if sectors_by_asset.get(aid) == sector:
                    weights[aid] = (w * scale).quantize(Decimal("0.000001"))
            sector_sums[sector] = max_sector_pct

    # Recompute sector totals from final weights for honesty
    final_sector_totals: dict[str, Decimal] = {}
    for aid, w in weights.items():
        s = sectors_by_asset.get(aid, "unknown")
        final_sector_totals[s] = final_sector_totals.get(s, Decimal("0")) + w

    # ------------------------------------------------------------------
    # SHADOW pathway — ML sizing multiplier, computed in parallel.
    # Does NOT affect `weights` above. For observability only.
    # ------------------------------------------------------------------
    shadow_weights: dict[str, Decimal] = {}
    shadow_log: list[TradeSizingLog] = []
    as_of_str = ""  # caller supplies via symbol map if needed

    # Step 1: base weights (same formula) × ML multiplier
    raw_shadow: dict[str, Decimal] = {}
    cand_by_id = {c.asset_id: c for c in active}
    for c in active:
        conf = _clamp(_d(c.confidence), Decimal("0"), Decimal("100"))
        base_w = base_weight * (conf / Decimal("100"))
        base_w_clamped = _clamp(base_w, Decimal("0"), max_position_pct)
        mult = compute_ml_multiplier(c.ml_proba)
        adj = base_w_clamped * mult
        raw_shadow[c.asset_id] = adj

    # Step 2: re-apply position cap after multiplier
    shadow_cap_reasons: dict[str, str | None] = {}
    for aid, w in raw_shadow.items():
        capped = w
        reason: str | None = None
        if capped > max_position_pct:
            capped = max_position_pct
            reason = "position_cap"
        if capped <= 0:
            continue
        shadow_weights[aid] = capped
        shadow_cap_reasons[aid] = reason

    # Step 3: sector cap on shadow weights
    shadow_sector_sums: dict[str, Decimal] = {}
    for aid, w in shadow_weights.items():
        s = sectors_by_asset.get(aid, "unknown")
        shadow_sector_sums[s] = shadow_sector_sums.get(s, Decimal("0")) + w
    for sector, total in list(shadow_sector_sums.items()):
        if total > max_sector_pct:
            scale = max_sector_pct / total
            for aid, w in list(shadow_weights.items()):
                if sectors_by_asset.get(aid) == sector:
                    shadow_weights[aid] = (w * scale).quantize(Decimal("0.000001"))
                    if shadow_cap_reasons.get(aid) is None:
                        shadow_cap_reasons[aid] = "sector_cap"
            shadow_sector_sums[sector] = max_sector_pct

    # Step 4a: pre-normalization shadow sector totals (for observability).
    pre_norm_shadow_sector: dict[str, Decimal] = {}
    for aid, w in shadow_weights.items():
        s = sectors_by_asset.get(aid, "unknown")
        pre_norm_shadow_sector[s] = pre_norm_shadow_sector.get(s, Decimal("0")) + w
    shadow_sum_pre_norm = sum(shadow_weights.values(), Decimal("0"))

    # Step 4b: NORMALIZE total shadow weight to match production sum_weights.
    # Preserves relative ML sizing while producing a capital-comparable book.
    production_sum = sum(weights.values(), Decimal("0"))
    pre_norm_weights: dict[str, Decimal] = dict(shadow_weights)
    if shadow_sum_pre_norm > 0:
        scale_factor = production_sum / shadow_sum_pre_norm
    else:
        scale_factor = Decimal("1")
    if scale_factor != Decimal("1"):
        for aid in list(shadow_weights.keys()):
            shadow_weights[aid] = (
                shadow_weights[aid] * scale_factor
            ).quantize(Decimal("0.0000000001"))

    # Safety check: post-normalization sum must match production sum to 1e-6.
    shadow_sum_post_norm = sum(shadow_weights.values(), Decimal("0"))
    if production_sum > 0:
        assert abs(shadow_sum_post_norm - production_sum) < Decimal("1e-6"), (
            f"shadow normalization failed: "
            f"post={shadow_sum_post_norm} prod={production_sum}"
        )

    # Step 4c: recompute shadow sector totals from normalized weights.
    final_shadow_sector: dict[str, Decimal] = {}
    for aid, w in shadow_weights.items():
        s = sectors_by_asset.get(aid, "unknown")
        final_shadow_sector[s] = final_shadow_sector.get(s, Decimal("0")) + w

    # Step 4d: build per-trade log including normalized_weight.
    for c in active:
        conf = _clamp(_d(c.confidence), Decimal("0"), Decimal("100"))
        base_w = _clamp(
            base_weight * (conf / Decimal("100")),
            Decimal("0"), max_position_pct,
        )
        mult = compute_ml_multiplier(c.ml_proba)
        adj = base_w * mult
        pre_norm = pre_norm_weights.get(c.asset_id, Decimal("0"))
        normalized = shadow_weights.get(c.asset_id, Decimal("0"))
        was_clipped = shadow_cap_reasons.get(c.asset_id) is not None
        shadow_log.append(TradeSizingLog(
            as_of_date=as_of_str,
            symbol=c.symbol or "",
            asset_id=c.asset_id,
            base_weight=str(base_w),
            ml_proba=str(c.ml_proba) if c.ml_proba is not None else None,
            multiplier=str(mult),
            adjusted_weight=str(adj),
            final_weight=str(pre_norm),
            was_clipped=was_clipped,
            cap_reason=shadow_cap_reasons.get(c.asset_id),
            normalized_weight=str(normalized),
        ))

    # ------------------------------------------------------------------
    # FEATURE FLAG — promote ML-sized weights to production.
    # When True:  target_weights  = ML-sized (normalized); shadow_weights = deterministic
    # When False: target_weights  = deterministic;         shadow_weights = ML-sized
    # Rollback:   set env ENABLE_ML_SIZING=0 and restart.
    # ------------------------------------------------------------------
    if settings.ENABLE_ML_SIZING and shadow_weights:
        production_out_weights = dict(shadow_weights)
        production_out_sector  = dict(final_shadow_sector)
        parallel_shadow_weights = dict(weights)
        parallel_shadow_sector  = dict(final_sector_totals)
        sizing_mode = "ml_sized"
    else:
        production_out_weights = weights
        production_out_sector  = final_sector_totals
        parallel_shadow_weights = dict(shadow_weights)
        parallel_shadow_sector  = dict(final_shadow_sector)
        sizing_mode = "deterministic"

    return SizingResult(
        target_weights=production_out_weights,
        sector_totals=production_out_sector,
        dropped=dropped,
        shadow_weights=parallel_shadow_weights,
        shadow_sector_totals=parallel_shadow_sector,
        shadow_log=shadow_log,
        shadow_sum_pre_norm=shadow_sum_pre_norm,
        shadow_sum_post_norm=shadow_sum_post_norm,
        shadow_scale_factor=scale_factor,
        sizing_mode=sizing_mode,
    )
