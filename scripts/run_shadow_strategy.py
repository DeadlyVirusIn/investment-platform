"""Daily shadow-strategy runner.

Computes the tsmom_60_no_stress shadow signal for the latest trading
date and upserts a row into paper_shadow_log. Also back-fills realized
forward returns (1d / 5d) for prior rows where bars are now available.

NEVER touches paper_trade_log, decision_log, ML pipeline, or any
production execution path.

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.run_shadow_strategy [--as-of 2026-04-24]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.research.engine_b_decision import (
    evaluate as eval_decision,
)
from apps.api.src.research.engine_b_decision_writer import (
    upsert_decision_snapshot,
)
from apps.api.src.research.engine_b_router import route as b_route
from apps.api.src.research.shadow_strategy import (
    INSTRUMENT_DEFAULT,
    SOURCE_STRATEGY,
    backfill_forward_returns,
    compute_decision,
    engine_b_signal_proxy,
    upsert_decision,
)
from apps.api.src.research.shadow_strategy_v2 import (
    REGIME_LOGIC_VERSION_V2,
    SOURCE_STRATEGY_V2,
    compute_decision_v2,
)


def _load_bars(start: str = "2018-01-01") -> pd.DataFrame:
    from scripts.run_phase12_price_action import fetch_es_daily
    df = fetch_es_daily(start=start)
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    return df


def _load_regime_map(session) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT as_of_date, context_name, value_bool
        FROM context_daily
        WHERE context_name IN ('stress_regime', 'directional_regime')
          AND (status = 'production'
              OR (status = 'diagnostic'
                   AND logic_version = 'research_backfill_v1'))
    """)).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    pivot = df.pivot_table(index="as_of_date", columns="context_name",
                              values="value_bool", aggfunc="first")
    return pivot.fillna(False).astype(bool)


def _load_regime_map_persist3(session) -> pd.DataFrame:
    """Persist-3 variant regime map (V2 strategy input).

    Reads context_daily rows with logic_version=research_backfill_persist3_v1.
    Empty DataFrame if no rows yet (V2 walks permissive in that case).
    """
    rows = session.execute(text(f"""
        SELECT as_of_date, context_name, value_bool
        FROM context_daily
        WHERE context_name IN ('stress_regime', 'directional_regime')
          AND status = 'diagnostic'
          AND logic_version = '{REGIME_LOGIC_VERSION_V2}'
    """)).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    return (df.pivot_table(index="as_of_date", columns="context_name",
                                values="value_bool", aggfunc="first")
            .fillna(False).astype(bool))


def _engine_a_active_on(session, dt: date) -> bool:
    """True if Engine A had a trade entry on `dt`."""
    res = session.execute(text("""
        SELECT 1 FROM paper_trade_log
         WHERE engine = 'A'
           AND entry_date = :dt
         LIMIT 1
    """), {"dt": dt}).first()
    return res is not None


def _backfill_returns(session, bars: pd.DataFrame) -> int:
    """For shadow rows older than 5 trading days where fwd_return_5d is
    NULL, fill in realized 1d/5d returns from bars.

    Covers BOTH source_strategy values (B2 + V2) — same fwd-return
    columns are valid for either.
    """
    rows = session.execute(text("""
        SELECT as_of_date, instrument, source_strategy, entry_price
          FROM paper_shadow_log
         WHERE source_strategy IN (:src, :src_v2)
           AND fwd_return_5d IS NULL
         ORDER BY as_of_date DESC
    """), {"src": SOURCE_STRATEGY, "src_v2": SOURCE_STRATEGY_V2}
    ).mappings().all()
    updated = 0
    for r in rows:
        d = pd.Timestamp(r["as_of_date"]).normalize()
        if d not in bars.index:
            continue
        idx = bars.index.get_loc(d)
        if not isinstance(idx, int):
            continue
        # Need at least t+1 for 1d, t+5 for 5d
        if idx + 1 >= len(bars):
            continue
        c0 = float(bars["close"].iloc[idx])
        c1 = float(bars["close"].iloc[idx + 1])
        ret1 = (c1 / c0 - 1.0) if c0 else None
        ret5 = None
        exit_price = None
        if idx + 5 < len(bars):
            c5 = float(bars["close"].iloc[idx + 5])
            ret5 = (c5 / c0 - 1.0) if c0 else None
            exit_price = c5
        n = backfill_forward_returns(
            session,
            as_of_date=r["as_of_date"],
            instrument=r["instrument"],
            source_strategy=r["source_strategy"],
            fwd_return_1d=ret1,
            fwd_return_5d=ret5,
            exit_price=exit_price,
        )
        updated += n
    if updated:
        session.commit()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None,
                          help="ISO date; defaults to last bar")
    parser.add_argument("--instrument", default=INSTRUMENT_DEFAULT)
    parser.add_argument("--no-backfill", action="store_true",
                          help="skip forward-return backfill")
    parser.add_argument("--backfill-from", default=None,
                          help="ISO date; if set, run shadow signal "
                               "for every trading day from this date "
                               "through --as-of (one-time historical fill)")
    args = parser.parse_args()

    bars = _load_bars()
    if bars.empty:
        print("No bars; aborting.")
        return 0

    if args.as_of:
        target = pd.Timestamp(args.as_of).normalize()
    else:
        target = bars.index[-1]

    if target not in bars.index:
        print(f"Target date {target.date()} not in bars; aborting.")
        return 0

    idx = bars.index.get_loc(target)
    if not isinstance(idx, int):
        print(f"Ambiguous target date {target.date()}; aborting.")
        return 0

    # Determine date range to compute
    if args.backfill_from:
        start_dt = pd.Timestamp(args.backfill_from).normalize()
        date_range = [d for d in bars.index
                       if d >= start_dt and d <= target]
    else:
        date_range = [target]

    with SessionLocal() as s:
        regime_map = _load_regime_map(s)
        regime_map_v2 = _load_regime_map_persist3(s)
        n_long = n_flat = 0
        n_long_v2 = n_flat_v2 = 0
        last_decision = None
        last_decision_v2 = None
        for dt in date_range:
            i = bars.index.get_loc(dt)
            if not isinstance(i, int):
                continue
            cl = list(bars["close"].iloc[: i + 1].astype(float).values)
            stress = direct = False
            if not regime_map.empty and dt in regime_map.index:
                row = regime_map.loc[dt]
                stress = bool(row.get("stress_regime", False))
                direct = bool(row.get("directional_regime", False))
            a_active = _engine_a_active_on(s, dt.date())
            decision = compute_decision(
                as_of_date=dt.date(),
                closes_thru_today=cl,
                stress_regime=stress,
                directional_regime=direct,
                engine_a_active=a_active,
                instrument=args.instrument,
            )

            # Engine B research-proxy + router output
            b_proxy = engine_b_signal_proxy(directional_regime=direct)
            b2_proxy = decision.signal
            mode = (settings.ENGINE_B_MODE or "LEGACY").upper()
            try:
                routed = b_route(
                    mode=mode, as_of=dt.date(),
                    engine_b_signal=b_proxy, b2_signal=b2_proxy,
                )
                routed_signal = routed.routed_signal
            except Exception:
                # Defensive: any router error → keep LEGACY semantics
                routed_signal = b_proxy

            upsert_decision(
                s, decision,
                engine_b_signal=b_proxy,
                b2_signal=b2_proxy,
                mode_at_decision=mode,
                routed_signal=routed_signal,
            )
            last_decision = decision

            # ---- V2 strategy (persist-3 MA200 stress) ----
            stress_v2 = direct_v2 = False
            if (not regime_map_v2.empty
                    and dt in regime_map_v2.index):
                row_v2 = regime_map_v2.loc[dt]
                stress_v2 = bool(row_v2.get("stress_regime", False))
                direct_v2 = bool(row_v2.get("directional_regime", False))
            decision_v2 = compute_decision_v2(
                as_of_date=dt.date(),
                closes_thru_today=cl,
                stress_regime_persist3=stress_v2,
                directional_regime_persist3=direct_v2,
                engine_a_active=a_active,
                instrument=args.instrument,
            )
            # Reuse the same upsert function — it keys on
            # (date, instrument, source_strategy) so V2 row is distinct.
            upsert_decision(
                s, decision_v2,
                engine_b_signal=b_proxy,
                b2_signal=decision_v2.signal,
                mode_at_decision=mode,
                routed_signal=routed_signal,
            )
            last_decision_v2 = decision_v2
            if decision_v2.signal == "LONG":
                n_long_v2 += 1
            else:
                n_flat_v2 += 1
            if decision.signal == "LONG":
                n_long += 1
            else:
                n_flat += 1
        s.commit()

        bf = 0
        if not args.no_backfill:
            bf = _backfill_returns(s, bars)

        # Persist daily decision snapshot (idempotent on (date, state))
        try:
            from sqlalchemy import text as _t
            shadow_rows = s.execute(_t("""
                SELECT as_of_date, signal,
                       engine_b_signal, b2_signal, routed_signal,
                       divergence_flag, divergence_outcome,
                       fwd_return_1d, regime_label
                  FROM paper_shadow_log
                 WHERE source_strategy = :strat
                 ORDER BY as_of_date
            """), {"strat": SOURCE_STRATEGY}).mappings().all()
            shadow_rows = [dict(r) for r in shadow_rows]
            mode_now = (settings.ENGINE_B_MODE or "LEGACY").upper()
            verdict = eval_decision(
                rows=shadow_rows,
                current_state=mode_now,
                operator_approval=bool(
                    settings.ENGINE_B_OPERATOR_APPROVAL),
            )
            if shadow_rows:
                upsert_decision_snapshot(
                    s, as_of_date=shadow_rows[-1]["as_of_date"],
                    decision=verdict,
                )
                s.commit()
        except Exception as e:
            s.rollback()
            print(f"  warn: decision snapshot persist failed: {e}")

    if last_decision:
        print(f"B2  decision @ {last_decision.as_of_date}: "
              f"signal={last_decision.signal} "
              f"regime={last_decision.regime_label} "
              f"engine_a_active={last_decision.engine_a_active}")
        print(f"  trend_score={last_decision.trend_score} "
              f"note={last_decision.note}")
    if last_decision_v2:
        print(f"V2  decision @ {last_decision_v2.as_of_date}: "
              f"signal={last_decision_v2.signal} "
              f"regime={last_decision_v2.regime_label}")
        print(f"  note={last_decision_v2.note}")
    if len(date_range) > 1:
        print(f"Processed {len(date_range)} days "
              f"(B2: {n_long} LONG / {n_flat} FLAT) "
              f"(V2: {n_long_v2} LONG / {n_flat_v2} FLAT)")
    print(f"Backfill updated {bf} prior rows with realized fwd returns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
