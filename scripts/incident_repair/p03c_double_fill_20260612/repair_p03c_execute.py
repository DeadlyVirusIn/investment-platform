"""P0-3C — EXECUTE paper-trading ledger repair (approved 2026-06-12).

Phases (each its own transaction; any assertion failure -> rollback +
hard abort; later phases never run):

  R0  backup tables (2 affected portfolios only) + keep/delete mapping
  R1  archive + delete exactly 31 duplicate legs
  R1b correct exactly 2 oversized COGT sell rows (qty + realized_pnl)
  R2  rebuild paper_position from the now-clean ledger (replay oracle)
  R3  append corrected source='live' snapshots (old rows NEVER deleted)
  R4  set paper_portfolio.cash to ledger truth (negative approved)
  V   verification gates (identity, dup-count 0, oracle equality)

Negative cash approved as truthful state — no fabricated adjustments.
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

TAG = "repair_20260612"

# Oracle expectations (re-confirmed immediately before execution).
EXPECT = {
    CANON: dict(cash=Decimal("-4785.89"), realized=Decimal("4460.06"),
                open_assets=27, starting=Decimal("100000")),
    MIRROR: dict(cash=Decimal("-1142.43"), realized=Decimal("413.96"),
                 open_assets=25, starting=Decimal("10000")),
}

DUP_RANKED = """
  SELECT id, portfolio_id, row_number() OVER (
    PARTITION BY portfolio_id, asset_id, side, fill_ts, quantity, fill_price
    ORDER BY created_at ASC, id ASC) AS rn
  FROM paper_trade
  WHERE fill_ts >= '2026-06-04' AND fill_ts < '2026-06-11'
    AND portfolio_id = ANY(%(pids)s)
"""


def die(conn, msg: str) -> None:
    try:
        conn.rollback()
    except Exception:
        pass
    print(f"ABORT: {msg}")
    sys.exit(1)


def replay(cur, pid: str, conn):
    """Replay the (post-R1/R1b clean) ledger. Returns
    (cash, realized, pos{asset:(qty,avg)}). No capping — ledger must be
    clean; any oversell is an abort condition."""
    cur.execute(
        "SELECT asset_id, side, quantity, fill_price FROM paper_trade "
        "WHERE portfolio_id=%s ORDER BY fill_ts ASC, created_at ASC, id ASC",
        (pid,))
    rows = cur.fetchall()
    cur.execute("SELECT starting_cash FROM paper_portfolio WHERE id=%s", (pid,))
    cash = Decimal(cur.fetchone()[0])
    realized = Decimal(0)
    pos: dict[str, tuple[Decimal, Decimal]] = {}
    for asset_id, side, qty, price in rows:
        qty, price = Decimal(qty), Decimal(price)
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
                die(conn, f"replay oversell (no position) {asset_id} pid={pid[:8]}")
            oq, oa = pos[asset_id]
            if qty > oq + Decimal("0.0001"):
                die(conn, f"replay oversell {asset_id} pid={pid[:8]} {qty} > {oq}")
            cash += qty * price
            realized += qty * (price - oa)
            rem = oq - qty
            if rem <= Decimal("0.0000001"):
                pos.pop(asset_id)
            else:
                pos[asset_id] = (rem, oa)
    return cash, realized, pos


def main() -> None:
    conn = psycopg2.connect(
        host=CFG["host"], port=CFG.get("port", 5432), dbname=CFG["database"],
        user=CFG["user"], password=CFG["password"],
    )
    conn.autocommit = False
    cur = conn.cursor()
    P = {"pids": PIDS}

    # ---------------- R0: backups -------------------------------------
    for src in ["paper_trade", "paper_position", "paper_equity_snapshot",
                "paper_portfolio"]:
        where = ("id = ANY(%(pids)s)" if src == "paper_portfolio"
                 else "portfolio_id = ANY(%(pids)s)")
        cur.execute(
            f"CREATE TABLE {TAG}_{src}_bak AS SELECT * FROM {src} WHERE {where}",
            P)
    cur.execute(
        f"""CREATE TABLE {TAG}_dup_mapping AS
            WITH ranked AS (
              SELECT id, first_value(id) OVER (
                PARTITION BY portfolio_id, asset_id, side, fill_ts,
                             quantity, fill_price
                ORDER BY created_at ASC, id ASC) AS keep_id,
              row_number() OVER (
                PARTITION BY portfolio_id, asset_id, side, fill_ts,
                             quantity, fill_price
                ORDER BY created_at ASC, id ASC) AS rn
              FROM paper_trade
              WHERE fill_ts >= '2026-06-04' AND fill_ts < '2026-06-11'
                AND portfolio_id = ANY(%(pids)s)
            )
            SELECT keep_id, id AS delete_id FROM ranked WHERE rn > 1""", P)
    cur.execute(f"SELECT count(*) FROM {TAG}_dup_mapping")
    n_map = cur.fetchone()[0]
    if n_map != 31:
        die(conn, f"R0 mapping rows {n_map} != 31")
    conn.commit()
    print(f"R0 OK: backups {TAG}_*_bak + {TAG}_dup_mapping (31 pairs)")

    # ---------------- R1: archive + delete 31 -------------------------
    cur.execute("CREATE TABLE paper_trade_dup_archive_20260612 "
                "(LIKE paper_trade)")
    cur.execute(
        f"INSERT INTO paper_trade_dup_archive_20260612 "
        f"SELECT t.* FROM paper_trade t "
        f"JOIN {TAG}_dup_mapping m ON m.delete_id = t.id")
    n_arch = cur.rowcount
    cur.execute(
        f"DELETE FROM paper_trade t USING {TAG}_dup_mapping m "
        f"WHERE t.id = m.delete_id")
    n_del = cur.rowcount
    if n_arch != 31 or n_del != 31:
        die(conn, f"R1 archive={n_arch} delete={n_del}, want 31/31")
    conn.commit()
    print("R1 OK: archived+deleted 31 legs -> paper_trade_dup_archive_20260612")

    # ---------------- R1b: COGT qty corrections -----------------------
    cur.execute("SELECT id FROM asset WHERE symbol = 'COGT'")
    cogt = cur.fetchone()[0]
    fixed = 0
    for pid in PIDS:
        cur.execute(
            "SELECT id, quantity, fill_price FROM paper_trade "
            "WHERE portfolio_id=%s AND asset_id=%s AND side='sell' "
            "  AND fill_ts::date = '2026-06-08'", (pid, cogt))
        rows = cur.fetchall()
        if len(rows) != 1:
            die(conn, f"R1b expected 1 COGT 06-08 sell, got {len(rows)} pid={pid[:8]}")
        tid, qty, price = rows[0]
        qty, price = Decimal(qty), Decimal(price)
        new_qty = qty / 2
        cur.execute(
            "SELECT fill_price FROM paper_trade WHERE portfolio_id=%s "
            "AND asset_id=%s AND side='buy' AND fill_ts::date='2026-06-05'",
            (pid, cogt))
        b = cur.fetchall()
        if len(b) != 1:
            die(conn, f"R1b expected 1 clean COGT 06-05 buy, got {len(b)}")
        avg = Decimal(b[0][0])
        new_realized = new_qty * (price - avg)
        cur.execute(
            "UPDATE paper_trade SET quantity=%s, realized_pnl=%s "
            "WHERE id=%s AND quantity=%s",
            (new_qty, new_realized, tid, qty))
        if cur.rowcount != 1:
            die(conn, f"R1b update matched {cur.rowcount} rows pid={pid[:8]}")
        fixed += 1
        print(f"R1b {pid[:8]} COGT sell {qty} -> {new_qty}, "
              f"realized -> {new_realized:.4f}")
    if fixed != 2:
        die(conn, f"R1b fixed {fixed} != 2")
    conn.commit()
    print("R1b OK: 2 COGT sells corrected")

    # ---------------- R2: rebuild positions ---------------------------
    replays = {}
    for pid in PIDS:
        cash, realized, pos = replay(cur, pid, conn)
        replays[pid] = (cash, realized, pos)
        exp = EXPECT[pid]
        if abs(cash - exp["cash"]) > Decimal("0.01"):
            die(conn, f"R2 cash {cash} != {exp['cash']} pid={pid[:8]}")
        if abs(realized - exp["realized"]) > Decimal("0.01"):
            die(conn, f"R2 realized {realized} != {exp['realized']}")
        if len(pos) != exp["open_assets"]:
            die(conn, f"R2 open assets {len(pos)} != {exp['open_assets']}")

        cur.execute(
            "SELECT id, asset_id, opened_at FROM paper_position "
            "WHERE portfolio_id=%s AND is_open ORDER BY asset_id, opened_at",
            (pid,))
        rows = cur.fetchall()
        open_assets_db = {r[1] for r in rows}
        if open_assets_db != set(pos.keys()):
            die(conn, f"R2 asset set mismatch pid={pid[:8]}")
        updated = deleted = 0
        by_asset: dict[str, list] = {}
        for rid, aid, oat in rows:
            by_asset.setdefault(aid, []).append((oat, rid))
        for aid, lst in by_asset.items():
            lst.sort()
            keep = lst[0][1]
            qty, avg = pos[aid]
            cur.execute(
                "UPDATE paper_position SET quantity=%s, avg_cost=%s, "
                "updated_at=now() WHERE id=%s", (qty, avg, keep))
            updated += cur.rowcount
            for _oat, extra in lst[1:]:
                cur.execute("DELETE FROM paper_position WHERE id=%s", (extra,))
                deleted += cur.rowcount
        print(f"R2 {pid[:8]}: updated={updated} deleted_artifacts={deleted}")
    conn.commit()
    print("R2 OK: positions rebuilt")

    # ---------------- R3: append corrected snapshots ------------------
    now = dt.datetime.now(dt.timezone.utc)
    inserted = 0
    for pid in PIDS:
        cur.execute(
            "SELECT DISTINCT snapshot_date::date FROM paper_equity_snapshot "
            "WHERE portfolio_id=%s AND source='live' "
            "AND snapshot_date >= '2026-06-04' ORDER BY 1", (pid,))
        dates = [r[0] for r in cur.fetchall()]
        if now.date() not in dates:
            dates.append(now.date())
        for dd in dates:
            cur.execute(
                "SELECT asset_id, side, quantity, fill_price FROM paper_trade "
                "WHERE portfolio_id=%s AND fill_ts::date <= %s "
                "ORDER BY fill_ts ASC, created_at ASC, id ASC", (pid, dd))
            rows = cur.fetchall()
            cash_d = EXPECT[pid]["starting"]
            realized_d = Decimal(0)
            pos_d: dict[str, tuple[Decimal, Decimal]] = {}
            for aid, side, q, px in rows:
                q, px = Decimal(q), Decimal(px)
                if side == "buy":
                    cash_d -= q * px
                    if aid in pos_d:
                        oq, oa = pos_d[aid]
                        nq = oq + q
                        pos_d[aid] = (nq, (oq * oa + q * px) / nq)
                    else:
                        pos_d[aid] = (q, px)
                else:
                    oq, oa = pos_d.get(aid, (Decimal(0), Decimal(0)))
                    sq = min(q, oq)
                    cash_d += q * px
                    realized_d += sq * (px - oa)
                    rem = oq - sq
                    if rem <= Decimal("0.0000001"):
                        pos_d.pop(aid, None)
                    else:
                        pos_d[aid] = (rem, oa)
            pv = Decimal(0)
            ur = Decimal(0)
            for aid, (q, avg) in pos_d.items():
                cur.execute(
                    "SELECT close FROM price_bar WHERE asset_id=%s AND "
                    "timeframe='1d' AND ts::date <= %s "
                    "ORDER BY ts DESC LIMIT 1", (aid, dd))
                r = cur.fetchone()
                px = Decimal(r[0]) if r else avg
                pv += q * px
                ur += q * (px - avg)
            te = cash_d + pv
            cur.execute(
                "INSERT INTO paper_equity_snapshot "
                "(id, portfolio_id, snapshot_date, total_equity, cash, "
                " positions_value, unrealized_pnl, realized_pnl_cumulative, "
                " recorded_at, source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'live')",
                (str(uuid.uuid4()), pid, dd, te, cash_d, pv, ur,
                 realized_d, now))
            inserted += 1
            print(f"R3 {pid[:8]} {dd}: te={te:,.2f} cash={cash_d:,.2f} "
                  f"real={realized_d:,.2f} unreal={ur:,.2f}")
    conn.commit()
    print(f"R3 OK: appended {inserted} corrected snapshots (old rows kept)")

    # ---------------- R4: portfolio cash -------------------------------
    for pid in PIDS:
        cash = replays[pid][0]
        cur.execute("UPDATE paper_portfolio SET cash=%s WHERE id=%s",
                    (cash, pid))
        if cur.rowcount != 1:
            die(conn, f"R4 cash update matched {cur.rowcount}")
        print(f"R4 {pid[:8]}: cash -> {cash:,.2f}")
    conn.commit()
    print("R4 OK")

    # ---------------- V: verification gates ---------------------------
    cur.execute(
        f"WITH ranked AS ({DUP_RANKED}) SELECT count(*) FROM ranked WHERE rn>1",
        P)
    dup_after = cur.fetchone()[0]
    print(f"V dup-count after repair: {dup_after} (want 0)")
    ok = dup_after == 0
    for pid in PIDS:
        cash, realized, pos = replay(cur, pid, conn)
        pv = Decimal(0)
        ur = Decimal(0)
        for aid, (q, avg) in pos.items():
            cur.execute(
                "SELECT close FROM price_bar WHERE asset_id=%s AND "
                "timeframe='1d' ORDER BY ts DESC LIMIT 1", (aid,))
            px = Decimal(cur.fetchone()[0])
            pv += q * px
            ur += q * (px - avg)
        nav = cash + pv
        ident = EXPECT[pid]["starting"] + realized + ur
        ret = (nav - EXPECT[pid]["starting"]) / EXPECT[pid]["starting"] * 100
        gap = abs(nav - ident)
        print(f"V {pid[:8]}: NAV={nav:,.2f} ret={ret:+.2f}% cash={cash:,.2f} "
              f"real={realized:,.2f} unreal={ur:,.2f} identity_gap={gap:.4f}")
        if gap > Decimal("0.01"):
            ok = False
    print("VERIFICATION:", "PASS" if ok else "FAIL")
    conn.close()
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
