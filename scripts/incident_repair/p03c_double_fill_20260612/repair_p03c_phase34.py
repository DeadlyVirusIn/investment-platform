"""P0-3C continuation — R3 (snapshot UPSERT) + R4 (cash) + verification.

R0/R1/R1b/R2 committed by repair_p03c_execute.py. Its R3 append hit
uq_paper_equity_snapshot (migration 094: ONE live row per portfolio/date
— the dup-rows fix) and rolled back cleanly. Lawful write is therefore
an UPSERT; the pre-repair snapshot rows are preserved verbatim in
repair_20260612_paper_equity_snapshot_bak.
"""

from __future__ import annotations

import json
import sys
import uuid
import datetime as dt
from decimal import Decimal
from pathlib import Path

import psycopg2

CFG = json.loads(
    (Path.home() / ".claude/skills/read-only-postgres/connections.json")
    .read_text()
)["databases"][0]

CANON = "166b12ed-4b6d-4ec8-854d-234baa7d029a"
MIRROR = "fdc48224-fb64-4883-973c-206a924bd7a5"
PIDS = [CANON, MIRROR]
START = {CANON: Decimal("100000"), MIRROR: Decimal("10000")}
EXPECT_CASH = {CANON: Decimal("-4785.89"), MIRROR: Decimal("-1142.43")}


def die(conn, msg):
    try:
        conn.rollback()
    except Exception:
        pass
    print(f"ABORT: {msg}")
    sys.exit(1)


def state_asof(cur, pid, dd):
    """Replay clean ledger up to end of date dd."""
    cur.execute(
        "SELECT asset_id, side, quantity, fill_price FROM paper_trade "
        "WHERE portfolio_id=%s AND fill_ts::date <= %s "
        "ORDER BY fill_ts ASC, created_at ASC, id ASC", (pid, dd))
    cash = START[pid]
    realized = Decimal(0)
    pos = {}
    for aid, side, q, px in cur.fetchall():
        q, px = Decimal(q), Decimal(px)
        if side == "buy":
            cash -= q * px
            if aid in pos:
                oq, oa = pos[aid]
                nq = oq + q
                pos[aid] = (nq, (oq * oa + q * px) / nq)
            else:
                pos[aid] = (q, px)
        else:
            oq, oa = pos.get(aid, (Decimal(0), Decimal(0)))
            sq = min(q, oq)
            cash += q * px
            realized += sq * (px - oa)
            rem = oq - sq
            if rem <= Decimal("0.0000001"):
                pos.pop(aid, None)
            else:
                pos[aid] = (rem, oa)
    return cash, realized, pos


def value(cur, pos, dd=None):
    pv = Decimal(0)
    ur = Decimal(0)
    for aid, (q, avg) in pos.items():
        if dd is None:
            cur.execute("SELECT close FROM price_bar WHERE asset_id=%s AND "
                        "timeframe='1d' ORDER BY ts DESC LIMIT 1", (aid,))
        else:
            cur.execute("SELECT close FROM price_bar WHERE asset_id=%s AND "
                        "timeframe='1d' AND ts::date <= %s "
                        "ORDER BY ts DESC LIMIT 1", (aid, dd))
        r = cur.fetchone()
        px = Decimal(r[0]) if r else avg
        pv += q * px
        ur += q * (px - avg)
    return pv, ur


def main():
    conn = psycopg2.connect(
        host=CFG["host"], port=CFG.get("port", 5432), dbname=CFG["database"],
        user=CFG["user"], password=CFG["password"])
    conn.autocommit = False
    cur = conn.cursor()
    now = dt.datetime.now(dt.timezone.utc)

    # Sanity: prior phases really landed.
    cur.execute("SELECT count(*) FROM paper_trade_dup_archive_20260612")
    if cur.fetchone()[0] != 31:
        die(conn, "R1 archive missing/incomplete — wrong DB state")

    # ---------------- R3: UPSERT corrected snapshots -------------------
    upserts = 0
    for pid in PIDS:
        cur.execute(
            "SELECT DISTINCT snapshot_date::date FROM paper_equity_snapshot "
            "WHERE portfolio_id=%s AND source='live' "
            "AND snapshot_date >= '2026-06-04' ORDER BY 1", (pid,))
        dates = [r[0] for r in cur.fetchall()]
        if now.date() not in dates:
            dates.append(now.date())
        for dd in dates:
            cash_d, real_d, pos_d = state_asof(cur, pid, dd)
            pv, ur = value(cur, pos_d, dd)
            te = cash_d + pv
            cur.execute(
                """INSERT INTO paper_equity_snapshot
                   (id, portfolio_id, snapshot_date, total_equity, cash,
                    positions_value, unrealized_pnl,
                    realized_pnl_cumulative, recorded_at, source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'live')
                   ON CONFLICT ON CONSTRAINT uq_paper_equity_snapshot
                   DO UPDATE SET
                     total_equity=EXCLUDED.total_equity,
                     cash=EXCLUDED.cash,
                     positions_value=EXCLUDED.positions_value,
                     unrealized_pnl=EXCLUDED.unrealized_pnl,
                     realized_pnl_cumulative=EXCLUDED.realized_pnl_cumulative,
                     recorded_at=EXCLUDED.recorded_at""",
                (str(uuid.uuid4()), pid, dd, te, cash_d, pv, ur, real_d, now))
            upserts += 1
            print(f"R3 {pid[:8]} {dd}: te={te:,.2f} cash={cash_d:,.2f} "
                  f"real={real_d:,.2f} unreal={ur:,.2f}")
    conn.commit()
    print(f"R3 OK: upserted {upserts} corrected snapshots "
          f"(originals preserved in repair_20260612_paper_equity_snapshot_bak)")

    # ---------------- R4: portfolio cash --------------------------------
    for pid in PIDS:
        cash, _, _ = state_asof(cur, pid, now.date())
        if abs(cash - EXPECT_CASH[pid]) > Decimal("0.01"):
            die(conn, f"R4 cash {cash} != {EXPECT_CASH[pid]} pid={pid[:8]}")
        cur.execute("UPDATE paper_portfolio SET cash=%s WHERE id=%s",
                    (cash, pid))
        if cur.rowcount != 1:
            die(conn, f"R4 update matched {cur.rowcount}")
        print(f"R4 {pid[:8]}: cash -> {cash:,.2f}")
    conn.commit()
    print("R4 OK")

    # ---------------- V: gates ------------------------------------------
    cur.execute("""
      WITH ranked AS (
        SELECT row_number() OVER (
          PARTITION BY portfolio_id, asset_id, side, fill_ts, quantity,
                       fill_price ORDER BY created_at, id) AS rn
        FROM paper_trade
        WHERE fill_ts >= '2026-06-04' AND fill_ts < '2026-06-11'
          AND portfolio_id = ANY(%s))
      SELECT count(*) FROM ranked WHERE rn > 1""", (PIDS,))
    dup_after = cur.fetchone()[0]
    ok = dup_after == 0
    print(f"V dup-count after repair: {dup_after} (want 0)")
    for pid in PIDS:
        cash, realized, pos = state_asof(cur, pid, now.date())
        pv, ur = value(cur, pos, None)
        nav = cash + pv
        ident = START[pid] + realized + ur
        ret = (nav - START[pid]) / START[pid] * 100
        gap = abs(nav - ident)
        print(f"V {pid[:8]}: NAV={nav:,.2f} ret={ret:+.2f}% cash={cash:,.2f} "
              f"real={realized:,.2f} unreal={ur:,.2f} gap={gap:.4f}")
        if gap > Decimal("0.01"):
            ok = False
    print("VERIFICATION:", "PASS" if ok else "FAIL")
    conn.close()
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
