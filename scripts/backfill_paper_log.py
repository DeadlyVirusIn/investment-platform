"""Backfill paper_trade_log + paper_portfolio_snapshot from Phase 24 trades.

Parses artifacts/phase24/trades.jsonl (299 trades 2022-04 to 2026-04) and
writes rows into the DL2/OPS1 DB tables so the UI has real data.

Equity path is computed by walking trades chronologically with the
standard paper rules: $100k starting capital, Engine A 10% position,
Engine B 5% position; slippage already included in net_ret_pct.

Usage:
    python -m scripts.backfill_paper_log
    python -m scripts.backfill_paper_log --reset   # wipe existing first
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal

TRADES_PATH = Path("artifacts/phase24/trades.jsonl")
PORTFOLIO_ID = "default"
STARTING_CAPITAL = 100_000.0
POS_A = 10.0    # Engine A percent notional
POS_B = 5.0     # Engine B percent notional
DECISION_VERSION_A = "engineA-v1.0.0"
DECISION_VERSION_B = "engineB-v1.0.0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="Delete existing paper_trade_log + snapshots first")
    args = ap.parse_args()

    if not TRADES_PATH.exists():
        logger.error("[backfill] {} missing", TRADES_PATH)
        return 1

    with TRADES_PATH.open() as f:
        trades = [json.loads(ln) for ln in f if ln.strip()]
    logger.info("[backfill] parsed {} trades", len(trades))

    trades.sort(key=lambda t: (t["entry_date"], t.get("entry_bar", 0)))

    with SessionLocal() as s:
        if args.reset:
            n1 = s.execute(text(
                "DELETE FROM paper_trade_log WHERE portfolio_id=:p"
            ), {"p": PORTFOLIO_ID}).rowcount
            n2 = s.execute(text(
                "DELETE FROM paper_portfolio_snapshot WHERE portfolio_id=:p"
            ), {"p": PORTFOLIO_ID}).rowcount
            s.commit()
            logger.info("[backfill] reset: {} trade rows, {} snapshot rows",
                        n1, n2)

        # ---------- 1. Write paper_trade_log ----------
        n_tr = 0
        for t in trades:
            eng = t["engine"]
            entry_d = dt.date.fromisoformat(t["entry_date"])
            exit_d = dt.date.fromisoformat(t["exit_date"]) if t.get("exit_date") else None
            gross = t.get("gross_ret_pct")
            net = t.get("net_ret_pct")
            pos_pct = POS_A if eng == "A" else POS_B
            slip_bps = (float(t.get("entry_slip_bps") or 0)
                        + float(t.get("exit_slip_bps") or 0))
            tid = str(uuid.uuid4())

            r = s.execute(text("""
                INSERT INTO paper_trade_log
                  (id, portfolio_id, engine, instrument, action,
                   entry_date, entry_price, exit_date, exit_price,
                   position_size_pct, slippage_bps_assumed,
                   gross_ret_pct, net_ret_pct,
                   regime_at_entry, reason, decision_version, status,
                   target_exit_date)
                VALUES
                  (CAST(:id AS uuid), :pid, :eng, :inst, 'enter_long',
                   :ed, :ep, :xd, :xp,
                   :sz, :sl,
                   :gr, :nr,
                   :reg, :reason, :dv, :st, :ted)
                ON CONFLICT DO NOTHING
            """), {
                "id": tid, "pid": PORTFOLIO_ID, "eng": eng, "inst": "ES",
                "ed": entry_d, "ep": float(t["entry_price"]),
                "xd": exit_d, "xp": float(t["exit_price"]) if t.get("exit_price") is not None else None,
                "sz": pos_pct, "sl": slip_bps,
                "gr": float(gross) if gross is not None else None,
                "nr": float(net) if net is not None else None,
                "reg": t.get("regime_at_decision", "none"),
                "reason": f"backfilled from phase24 trades.jsonl (gates_fav="
                          f"{t.get('gates_favorable_at_decision')})",
                "dv": DECISION_VERSION_A if eng == "A" else DECISION_VERSION_B,
                "st": "closed" if exit_d else "open",
                "ted": exit_d,
            })
            n_tr += r.rowcount or 0
        s.commit()
        logger.info("[backfill] inserted {} paper_trade_log rows", n_tr)

        # ---------- 2. Compute equity path (daily snapshot) ----------
        # Walk trades chronologically. Each trade's net_ret_pct is already
        # on its notional. Apply to equity sequentially at close date.
        equity = STARTING_CAPITAL
        peak = STARTING_CAPITAL
        cum_pct = 0.0
        max_dd = 0.0
        by_close: dict[dt.date, list[dict]] = {}
        for t in trades:
            ed = dt.date.fromisoformat(t.get("exit_date") or t["entry_date"])
            by_close.setdefault(ed, []).append(t)

        if not by_close:
            logger.warning("[backfill] no trade close-dates to snapshot")
            return 0

        # Iterate calendar days between first and last close-date
        first_d = min(by_close.keys())
        last_d = max(by_close.keys())
        n_snap = 0
        d = first_d
        prev_equity = equity
        while d <= last_d:
            # Close out any trades that closed today
            today_trades = by_close.get(d, [])
            daily_pnl = 0.0
            for t in today_trades:
                eng = t["engine"]
                net = float(t.get("net_ret_pct") or 0) / 100.0
                pos_pct = POS_A if eng == "A" else POS_B
                notional = (pos_pct / 100.0) * equity
                pnl = notional * net
                daily_pnl += pnl

            prev_equity = equity
            equity += daily_pnl
            cum_pct = (equity / STARTING_CAPITAL - 1) * 100.0
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100.0
            max_dd = min(max_dd, dd)

            # Determine regime from majority of today's closed trades
            regime = today_trades[0].get("regime_at_decision", "none") if today_trades else "none"
            engine_active = (today_trades[0]["engine"] if today_trades
                             else "none")

            if today_trades:
                r = s.execute(text("""
                    INSERT INTO paper_portfolio_snapshot
                      (as_of_date, portfolio_id, equity, cash, open_positions,
                       daily_pnl, cum_pct, max_dd_pct, regime, engine_active,
                       run_version)
                    VALUES
                      (:d, :pid, :eq, :cs, CAST(:op AS jsonb),
                       :dp, :cum, :dd, :reg, :eng, 'backfill-v1.0.0')
                    ON CONFLICT (portfolio_id, as_of_date) DO UPDATE SET
                      equity=EXCLUDED.equity, cash=EXCLUDED.cash,
                      daily_pnl=EXCLUDED.daily_pnl,
                      cum_pct=EXCLUDED.cum_pct, max_dd_pct=EXCLUDED.max_dd_pct,
                      regime=EXCLUDED.regime,
                      engine_active=EXCLUDED.engine_active
                """), {
                    "d": d, "pid": PORTFOLIO_ID,
                    "eq": equity, "cs": equity,   # flat after close
                    "op": json.dumps([]),
                    "dp": daily_pnl, "cum": cum_pct, "dd": max_dd,
                    "reg": regime, "eng": engine_active,
                })
                n_snap += r.rowcount or 0
            d += dt.timedelta(days=1)
        s.commit()
        logger.info("[backfill] wrote {} portfolio snapshots", n_snap)
        logger.info("[backfill] final equity=${:.2f} cum={:.3f}% maxDD={:.3f}%",
                    equity, cum_pct, max_dd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
