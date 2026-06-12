# P0-3C — Paper Ledger Double-Fill Repair (2026-06-12)

**Status: EXECUTED + VERIFIED. These scripts are an incident-history
record, not reusable tooling. Do not re-run.**

## Incident summary

The worker image deployed 2026-06-04 → 2026-06-10 double-executed every
paper-trading decision batch (`run_paper_trading` buys AND
`run_paper_exit_cycle` sells): two fill rows per decision, ~25ms apart,
in both portfolios (canonical Replay Recovery `166b12ed…` and Default
Paper mirror `fdc48224…`). The defect existed only in a deployed image
built from an uncommitted working tree — it never existed in git
(root cause of the P0-4 build-provenance system). Damage: 31 phantom
fill legs (+2 kept sells carrying doubled quantities), phantom NAV
$161,247.32 / +61.25% on a true ≈ $107k book.

## What ran, when (all 2026-06-12 UTC)

| Script | Phases | Executed | Result |
|---|---|---|---|
| `dryrun_p03c_replay.py` | read-only oracle (replay + expected values) | ~14:30 (re-run pre-mutation) | established corrected truth |
| `repair_p03c_execute.py` | R0 backups, R1 archive+delete 31 legs, R1b 2 COGT qty corrections, R2 position rebuild | ~14:50 | R0–R2 committed; its R3 append aborted cleanly on `uq_paper_equity_snapshot` (migration 094: one live row per date) |
| `repair_p03c_phase34.py` | R3 snapshot UPSERT, R4 cash, verification gates | ~15:10 | **VERIFICATION: PASS** — identity gap 0.0000 both portfolios |

## Corrected values (verified)

| | Canonical | Mirror |
|---|---|---|
| NAV | **$107,250.55 (+7.25%)** | $10,664.03 (+6.64%) |
| Cash (approved negative ledger truth) | **−$4,785.89** | −$1,142.43 |
| Realized / Unrealized | 4,460.06 / 2,790.48 | 413.96 / 250.07 |
| Identity NAV = start + R + U | gap 0.0000 | gap 0.0000 |

## Backup / archive tables (in the prod DB)

- `repair_20260612_paper_trade_bak`
- `repair_20260612_paper_position_bak`
- `repair_20260612_paper_equity_snapshot_bak`  ← pre-repair snapshot rows, verbatim
- `repair_20260612_paper_portfolio_bak`
- `repair_20260612_dup_mapping`                 ← 31 keep/delete id pairs
- `paper_trade_dup_archive_20260612`            ← the 31 deleted legs

Rollback (never needed): re-insert the archive rows; restore the other
tables from the `_bak` copies by id.

## Re-run safety

Accidental re-execution is self-aborting/harmless: `repair_p03c_execute`
dies at R0 (`CREATE TABLE repair_20260612_…` already exists) before any
mutation; `repair_p03c_phase34` re-verifies the 31-leg archive then
idempotently re-upserts identical snapshot values. The dry-run oracle is
read-only (`readonly=True` session).

## Credentials caveat

All three scripts read DB connection settings from a machine-local
path (`~/.claude/skills/read-only-postgres/connections.json`). They are
a historical record of what was executed — not portable tooling. A
generalized copy of the oracle is the seed for the planned nightly
NAV-identity invariant monitor.

## Prevention shipped alongside

- Migration **097** `ux_paper_trade_autotrader_idempotency` — commit `42a48cb` (+ savepoint containment `b4c100d`, revision-id fix `92f041c`)
- Migration **098** `ux_paper_trade_engine_sell_day` — commit `969b621`
- In-run guards (`pending_buy_assets`, sell-loop dedup) — `42a48cb`
- Scheduler failure truthfulness — `f329f50`; build provenance — `a7a810d`
