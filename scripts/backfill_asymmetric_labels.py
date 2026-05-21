"""Asymmetric-barrier relabeling pivot.

Re-labels existing HistoricalLabel rows IN-PLACE WITH VERSIONING.

Per 2026-04-21 debate synthesis + E1 FAIL diagnostic (Sonnet D1 Spearman
-0.2001 → barrier structurally vol-entangled):

  - Source engine_version = MODEL_VERSION (symmetric PT=SL=2σ)
  - Target engine_version = MODEL_VERSION + ":asym_2_1"
  - PT_SIGMAS = 2.0  (profit target)
  - SL_SIGMAS = 1.0  (tighter stop per AFML Ch.3 directional recommendation)

No new features. No new model. Label-only pivot. Lockbox-untouched rule
does NOT apply to relabeling (labels are data, not metric reads). The
lockbox ROWS get new labels but are still reserved for a single final
metric read.

Usage::

    python -m scripts.backfill_asymmetric_labels
    python -m scripts.backfill_asymmetric_labels --pt 2.0 --sl 1.0
    python -m scripts.backfill_asymmetric_labels --source-version X --target-suffix ':asym_2_1'
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from collections import Counter
from decimal import Decimal

from loguru import logger
from sqlalchemy import delete, func, select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import HistoricalLabel
from apps.api.src.domain.ml.backfill_service import (
    N_BARS_FORWARD,
    _load_forward_bars,
    _upsert_label,
    compute_triple_barrier_prices,
    label_from_bars,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION


# ---------------------------------------------------------------------------
# Pure per-row relabel
# ---------------------------------------------------------------------------


def _copy_row_with_new_label(
    row: HistoricalLabel, target_version: str,
    label: int, first_touch: int | None,
    exit_price: Decimal, forward_return_pct: Decimal,
    pt_price: Decimal, sl_price: Decimal, entry_price: Decimal,
    pt_sigma: float, sl_sigma: float,
) -> dict:
    """Build a new historical_label row dict carrying features from `row`
    but with recomputed label fields under `target_version`.
    """
    raw = dict(row.raw_payload) if row.raw_payload else {}
    raw["relabel_parent_engine_version"] = row.engine_version
    raw["relabel_pt_sigma"] = float(pt_sigma)
    raw["relabel_sl_sigma"] = float(sl_sigma)
    raw["relabel_source_row_id"] = row.id
    raw["relabeled_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    return {
        "id": str(uuid.uuid4()),
        "as_of_date": row.as_of_date,
        "asset_id": row.asset_id,
        "symbol": row.symbol,
        "engine_version": target_version,
        "action": row.action,
        "composite_score": row.composite_score,
        "confidence": row.confidence,
        "residual_momentum_20d": row.residual_momentum_20d,
        "residual_momentum_60d": row.residual_momentum_60d,
        "sector_relative_rank": row.sector_relative_rank,
        "trend_strength_20d": row.trend_strength_20d,
        "price_vs_200sma": row.price_vs_200sma,
        "atr_percent_14": row.atr_percent_14,
        "avg_dollar_volume_20d": row.avg_dollar_volume_20d,
        "market_trend": row.market_trend,
        "vol_regime": row.vol_regime,
        "realized_vol_20d": row.realized_vol_20d,
        "atr_pctile_1y": row.atr_pctile_1y,
        "label": label,
        "forward_return_pct": forward_return_pct,
        "barrier_first_touch_bar": first_touch,
        "barrier_n_bars": N_BARS_FORWARD,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pt_price": pt_price,
        "sl_price": sl_price,
        "sector": row.sector,
        "raw_payload": raw,
    }


# ---------------------------------------------------------------------------
# Per-day relabel
# ---------------------------------------------------------------------------


def _relabel_day(
    session, as_of: dt.date,
    source_version: str, target_version: str,
    pt_sigma: Decimal, sl_sigma: Decimal,
) -> tuple[int, int, Counter[str]]:
    rows = list(session.execute(
        select(HistoricalLabel).where(
            HistoricalLabel.as_of_date == as_of,
            HistoricalLabel.engine_version == source_version,
        )
    ).scalars().all())

    labeled = 0
    skipped = 0
    skip_reasons: Counter[str] = Counter()

    for row in rows:
        if row.realized_vol_20d is None:
            skip_reasons["no_realized_vol"] += 1
            skipped += 1
            continue
        rv = Decimal(str(row.realized_vol_20d))
        if rv <= 0:
            skip_reasons["zero_vol"] += 1
            skipped += 1
            continue

        bars = _load_forward_bars(
            session, row.asset_id, as_of, N_BARS_FORWARD,
        )
        if len(bars) < 2:
            skip_reasons["insufficient_forward_bars"] += 1
            skipped += 1
            continue
        entry_bar = bars[0]
        if entry_bar.close is None:
            skip_reasons["no_entry_close"] += 1
            skipped += 1
            continue
        entry = Decimal(str(entry_bar.close))
        forward_bars = bars[1 : 1 + N_BARS_FORWARD]
        if len(forward_bars) < N_BARS_FORWARD:
            skip_reasons["insufficient_forward_bars"] += 1
            skipped += 1
            continue

        pt, sl = compute_triple_barrier_prices(
            entry, rv, N_BARS_FORWARD,
            pt_sigma=pt_sigma, sl_sigma=sl_sigma,
        )
        label, first_touch, exit_price, fwd_ret = label_from_bars(
            entry, pt, sl, forward_bars,
        )

        new_row = _copy_row_with_new_label(
            row, target_version, label, first_touch,
            exit_price, fwd_ret, pt, sl, entry,
            float(pt_sigma), float(sl_sigma),
        )
        _upsert_label(session, new_row)
        labeled += 1

    session.commit()
    return labeled, skipped, skip_reasons


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class RelabelValidationError(RuntimeError):
    pass


def _validate(session, target_version: str, source_version: str) -> dict:
    src_total = session.execute(
        select(func.count()).select_from(HistoricalLabel).where(
            HistoricalLabel.engine_version == source_version,
        )
    ).scalar_one()
    tgt_total = session.execute(
        select(func.count()).select_from(HistoricalLabel).where(
            HistoricalLabel.engine_version == target_version,
        )
    ).scalar_one()
    if tgt_total == 0:
        raise RelabelValidationError("no target rows written")

    src_dist = dict(session.execute(
        select(HistoricalLabel.label, func.count())
        .where(HistoricalLabel.engine_version == source_version)
        .group_by(HistoricalLabel.label)
    ).all())
    tgt_dist = dict(session.execute(
        select(HistoricalLabel.label, func.count())
        .where(HistoricalLabel.engine_version == target_version)
        .group_by(HistoricalLabel.label)
    ).all())

    src_min_d, src_max_d = session.execute(
        select(
            func.min(HistoricalLabel.as_of_date),
            func.max(HistoricalLabel.as_of_date),
        ).where(HistoricalLabel.engine_version == source_version)
    ).one()
    tgt_min_d, tgt_max_d = session.execute(
        select(
            func.min(HistoricalLabel.as_of_date),
            func.max(HistoricalLabel.as_of_date),
        ).where(HistoricalLabel.engine_version == target_version)
    ).one()

    src_buys = session.execute(
        select(func.count()).select_from(HistoricalLabel).where(
            HistoricalLabel.engine_version == source_version,
            HistoricalLabel.action == "Buy",
        )
    ).scalar_one()
    tgt_buys = session.execute(
        select(func.count()).select_from(HistoricalLabel).where(
            HistoricalLabel.engine_version == target_version,
            HistoricalLabel.action == "Buy",
        )
    ).scalar_one()

    summary = {
        "source_version": source_version,
        "target_version": target_version,
        "source_rows": src_total,
        "target_rows": tgt_total,
        "source_buys": src_buys,
        "target_buys": tgt_buys,
        "source_label_dist": src_dist,
        "target_label_dist": tgt_dist,
        "source_date_range": (str(src_min_d), str(src_max_d)),
        "target_date_range": (str(tgt_min_d), str(tgt_max_d)),
    }
    logger.info("[relabel.validate] summary={}", summary)

    # Sanity: same row count expected (Buy rows relabeled 1:1)
    if tgt_buys < int(src_buys * 0.90):
        raise RelabelValidationError(
            f"target_buys={tgt_buys} < 90% of source_buys={src_buys} "
            "— too many rows dropped during relabel"
        )
    tgt_timeout_rate = (
        tgt_dist.get(0, 0) / tgt_total if tgt_total else 0
    )
    if tgt_timeout_rate > 0.90:
        raise RelabelValidationError(
            f"target timeout rate {tgt_timeout_rate:.2%} > 90% — "
            "barrier math likely wrong"
        )
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pt", type=float, default=2.0,
        help="profit-target sigma multiplier (default 2.0)",
    )
    parser.add_argument(
        "--sl", type=float, default=1.0,
        help="stop-loss sigma multiplier (default 1.0, AFML Ch.3 asymmetric)",
    )
    parser.add_argument(
        "--source-version", type=str, default=MODEL_VERSION,
        help="source engine_version (default: current MODEL_VERSION)",
    )
    parser.add_argument(
        "--target-suffix", type=str, default=":asym_2_1",
        help="suffix appended to source version for target (default ':asym_2_1')",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="delete existing target-version rows before relabeling",
    )
    args = parser.parse_args()

    pt_sigma = Decimal(str(args.pt))
    sl_sigma = Decimal(str(args.sl))
    target_version = f"{args.source_version}{args.target_suffix}"
    logger.info(
        "[relabel] source={} target={} PT_SIGMA={} SL_SIGMA={}",
        args.source_version, target_version, pt_sigma, sl_sigma,
    )

    with SessionLocal() as session:
        if args.reset:
            n = session.execute(
                delete(HistoricalLabel).where(
                    HistoricalLabel.engine_version == target_version,
                )
            ).rowcount
            session.commit()
            logger.warning("[relabel] RESET deleted {} existing rows", n)

        # Enumerate distinct source dates
        dates = list(session.execute(
            select(func.distinct(HistoricalLabel.as_of_date))
            .where(HistoricalLabel.engine_version == args.source_version)
            .order_by(HistoricalLabel.as_of_date.asc())
        ).scalars().all())
        logger.info("[relabel] source dates: {}", len(dates))

        total_labeled = 0
        total_skipped = 0
        agg_skips: Counter[str] = Counter()
        for i, d in enumerate(dates):
            labeled, skipped, reasons = _relabel_day(
                session, d, args.source_version, target_version,
                pt_sigma, sl_sigma,
            )
            total_labeled += labeled
            total_skipped += skipped
            agg_skips.update(reasons)
            if (i + 1) % 50 == 0:
                logger.info(
                    "[relabel] progress {}/{} labeled_so_far={} skipped={}",
                    i + 1, len(dates), total_labeled, total_skipped,
                )

        logger.info("=" * 72)
        logger.info(
            "[relabel] DONE labeled={} skipped={} skip_reasons={}",
            total_labeled, total_skipped, dict(agg_skips),
        )
        logger.info("=" * 72)

        _validate(session, target_version, args.source_version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
