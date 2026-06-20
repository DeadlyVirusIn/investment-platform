# Repair note — 2026-06-19: demo device portfolio clone

## Summary

For ~3 months the UI surfaced the **Replay Recovery Account**
(`paper_portfolio.id = 166b12ed-4b6d-4ec8-854d-234baa7d029a`) as the visible
portfolio. Product-wise it had become the owner/demo account: the book people
saw and demoed against. When per-user portfolio isolation landed
(`resolve_user_stock_portfolio`, name `user:<device>:stock`), the owner/demo
device started resolving to a **fresh empty personal book**, which read as the
account being wiped — a trust break, not a data loss.

This repair clones the Replay Recovery **state** into the owner/demo device's
own private book so that device sees its expected portfolio again, **without**
touching the shared Replay Recovery source and **without** changing behaviour
for any other user or device.

## What changed (data only — no schema change)

- **Source (untouched, read-only):** Replay Recovery Account
  `166b12ed-4b6d-4ec8-854d-234baa7d029a`.
- **Owner/demo device:** `305fcf0b-bc89-4d9d-ba47-b6de6810dfd6`.
- **Target (private per-device book):**
  `bc207e65-89a7-4f28-bef1-e2e5a7d47e7c`, name
  `user:305fcf0b-bc89-4d9d-ba47-b6de6810dfd6:stock`.

The target's prior (near-empty) rows were replaced with deep copies of the
source's portfolio-scoped rows:

- `paper_position` — 93 rows (30 open / 63 closed), exact quantity / avg_cost /
  realized_pnl / timestamps.
- `paper_trade` — 154 rows (full closed-trade history, realized P/L
  **+$5,951.82**).
- `paper_equity_snapshot` — 46 rows (the equity curve, original dates +
  `source` discriminator).
- `paper_portfolio.cash` (**$171.45**) and `config_json` mirrored from source.

### What could NOT be copied verbatim

- **Primary-key IDs are regenerated.** Copied positions/trades/snapshots get
  fresh UUIDs (PKs are globally unique). All *relationships* were ID-remapped,
  so internal attribution (position → opening/closing trade) and links to
  global `recommendation` rows are preserved; only the raw id strings differ.
- **Portfolio name stays `user:305fcf0b…:stock`**, not "Replay Recovery
  Account" (that name is UNIQUE and owned by the untouched source). This is the
  correct end state — the device now has a **private** book, not the shared
  demo.
- **Telemetry/social not cloned:** `paper_execution_funnel` and
  `portfolio_follow` were not copied (they do not affect NAV / positions /
  realized P/L).
- **Live NAV / unrealized P/L** is not stored — it is recomputed from positions
  × live price at read time. Because the target now holds identical positions,
  it computes the same NAV/unrealized as the source automatically.

## Verification (post-clone, via live `/api/paper/canonical/stock`)

Resolving as device `305fcf0b-…`:

| field | value |
|---|---|
| portfolio_id | `bc207e65-89a7-4f28-bef1-e2e5a7d47e7c` |
| nav | 105,211.76 |
| cash | 171.45 |
| realized_pnl | 5,951.82 |
| open_positions_count | 30 |
| starting_capital | 100,000 |
| status / freshness | live / fresh |

Source Replay Recovery: open positions still **30**, unchanged. Only the target
portfolio row was mutated.

## Backups

- Full DB dump: `.backups/devdb_full_20260619_212700.dump` (custom format).
- Targeted CSV extracts: `.backups/extract_paper_{portfolio,position,trade,
  equity_snapshot}_20260619_212700.csv`.
- Surgical in-DB rollback of the target's pre-clone rows:
  `clonebak_20260619_target_{portfolio,position,trade,eqsnap}`.

### Rollback (target only)

Restore the target from the in-DB backup tables (single transaction): delete
the target's `paper_position` / `paper_trade` / `paper_equity_snapshot` rows and
re-insert from `clonebak_20260619_target_*`, then restore
`paper_portfolio.cash` / `config_json` from
`clonebak_20260619_target_portfolio`. Full restore available from the dump.

## Resolver policy (unchanged, reaffirmed)

- **New users/devices still get a fresh EMPTY personal book.** This repair is a
  one-off data clone for the single owner/demo device; it does not alter
  `resolve_user_stock_portfolio` behaviour.
- A device that already owns a per-device book must keep resolving to **that**
  book. A resolver change must never silently repoint a known/demo device to
  the shared Replay-Recovery fallback (`CANONICAL_STOCK_PORTFOLIO_ID`).
- Guardrail test:
  `apps/api/tests/integration/test_paper_user_portfolio_pg.py::`
  `test_known_device_resolution_is_stable_and_never_shared_fallback`.

See also: [`DEMO_PORTFOLIO_SEED.md`](DEMO_PORTFOLIO_SEED.md),
[`DB_BACKUP_AND_REPLAY_POLICY.md`](DB_BACKUP_AND_REPLAY_POLICY.md).
