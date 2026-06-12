"""P0-3C DRY RUN — recompute repaired paper ledger. READ-ONLY.

Replays each portfolio's CLEAN trade ledger (duplicate legs excluded via
the same window-function rule the repair will use) through the engine's
position semantics (paper_execution.submit_trade):

  buy  : merge into open position at weighted avg cost (or open new)
  sell : reduce qty; realized += qty * (price - avg_cost); close at 0

Then values open positions at the latest price_bar close and prints
cash / realized / unrealized / NAV / return vs starting_cash.

SELECT-only. No writes of any kind.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import psycopg2

CFG = json.loads(
    (Path.home() / ".claude/skills/read-only-postgres/connections.json")
    .read_text()
)["databases"][0]

PIDS = {
    "166b12ed-4b6d-4ec8-854d-234baa7d029a": "Replay Recovery (canonical)",
    "fdc48224-fb64-4883-973c-206a924bd7a5": "Default Paper (mirror)",
}

CLEAN_TRADES_SQL = """
WITH ranked AS (
  SELECT t.*, row_number() OVER (
    PARTITION BY t.portfolio_id, t.asset_id, t.side, t.fill_ts,
                 t.quantity, t.fill_price
    ORDER BY t.created_at ASC, t.id ASC) AS rn
  FROM paper_trade t
  WHERE t.portfolio_id = %s
)
SELECT asset_id, side, quantity, fill_price, fill_ts, created_at
FROM ranked
WHERE NOT (rn > 1 AND fill_ts >= '2026-06-04' AND fill_ts < '2026-06-11')
ORDER BY fill_ts ASC, created_at ASC, id ASC
"""

LATEST_CLOSE_SQL = """
SELECT DISTINCT ON (pb.asset_id) pb.asset_id, pb.close
FROM price_bar pb
WHERE pb.asset_id = ANY(%s) AND pb.timeframe = '1d'
ORDER BY pb.asset_id, pb.ts DESC
"""


def main() -> None:
    conn = psycopg2.connect(
        host=CFG["host"], port=CFG.get("port", 5432), dbname=CFG["database"],
        user=CFG["user"], password=CFG["password"],
    )
    conn.set_session(readonly=True)
    cur = conn.cursor()

    for pid, label in PIDS.items():
        cur.execute(
            "SELECT starting_cash FROM paper_portfolio WHERE id = %s", (pid,))
        starting = Decimal(cur.fetchone()[0])

        cur.execute(CLEAN_TRADES_SQL, (pid,))
        rows = cur.fetchall()

        cash = starting
        realized = Decimal(0)
        pos: dict[str, tuple[Decimal, Decimal]] = {}  # asset -> (qty, avg)
        anomalies: list[str] = []

        for asset_id, side, qty, price, fill_ts, _created in rows:
            qty = Decimal(qty)
            price = Decimal(price)
            if side == "buy":
                cash -= qty * price
                if asset_id in pos:
                    oq, oa = pos[asset_id]
                    nq = oq + qty
                    pos[asset_id] = (nq, (oq * oa + qty * price) / nq)
                else:
                    pos[asset_id] = (qty, price)
            else:
                if asset_id not in pos:
                    anomalies.append(
                        f"sell without position {asset_id[:8]} {fill_ts.date()} qty={qty}")
                    cash += qty * price
                    continue
                oq, oa = pos[asset_id]
                sell_qty = min(qty, oq)
                if qty > oq + Decimal("0.0001"):
                    # Repair model: kept sell rows whose qty embeds phantom
                    # shares get CORRECTED to the clean position size —
                    # proceeds credited only for real shares.
                    anomalies.append(
                        f"qty-correction {asset_id[:8]} {fill_ts.date()} "
                        f"{qty:.4f} -> {sell_qty:.4f}")
                cash += sell_qty * price
                realized += sell_qty * (price - oa)
                remaining = oq - sell_qty
                if remaining <= Decimal("0.0000001"):
                    pos.pop(asset_id)
                else:
                    pos[asset_id] = (remaining, oa)

        open_assets = list(pos.keys())
        closes: dict[str, Decimal] = {}
        if open_assets:
            cur.execute(LATEST_CLOSE_SQL, (open_assets,))
            closes = {a: Decimal(c) for a, c in cur.fetchall()}

        mkt = Decimal(0)
        unreal = Decimal(0)
        missing_px = 0
        for a, (q, avg) in pos.items():
            px = closes.get(a)
            if px is None:
                missing_px += 1
                px = avg
            mkt += q * px
            unreal += q * (px - avg)

        nav = cash + mkt
        ret = (nav - starting) / starting * 100

        print(f"== {label} ==")
        print(f"  trades replayed (clean): {len(rows)}")
        print(f"  starting_cash : {starting:,.2f}")
        print(f"  cash          : {cash:,.2f}")
        print(f"  open positions: {len(pos)} (missing px: {missing_px})")
        print(f"  positions mkt : {mkt:,.2f}")
        print(f"  realized pnl  : {realized:,.2f}")
        print(f"  unrealized    : {unreal:,.2f}")
        print(f"  NAV           : {nav:,.2f}")
        print(f"  return        : {ret:+.2f}%")
        print(f"  identity check: start+real+unreal = {(starting+realized+unreal):,.2f}")
        for a in anomalies:
            print(f"  ANOMALY: {a}")
        print()

    conn.close()


if __name__ == "__main__":
    main()
