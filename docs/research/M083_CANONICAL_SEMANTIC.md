# M083 — Canonical Semantic for paper_equity_snapshot Replay Rows

**Status**: locked
**Date**: 2026-05-17
**Scope**: defines truth-model contract for `paper_equity_snapshot` post-Phase-L migration

---

## Decision: Option A — Replay rows are audit-only

### Definition

- Replay-generated equity snapshot rows exist **for forensic and operator visibility only**
- User-facing canonical equity history is composed exclusively from rows with `source='live'`
- Replay rows MUST NOT participate in:
  - AI's Portfolio summary
  - Equity-curve charts (any timeframe)
  - Performance summaries
  - Daily P&L computations
  - Aggregations consumed by user-facing surfaces
- Replay rows MAY appear on:
  - Operator forensic dashboards (explicitly framed as forensic)
  - Engine Inspection page (Advanced persona only)
  - Audit log queries
  - Backfill reconciliation tools

### Why Option A

- **Presentation immutability preserved**: AI's Portfolio for date D shows identical value today, tomorrow, and after any number of replays
- **Storage immutability preserved**: original live rows are never modified; replay rows are additive
- **Forensic visibility preserved**: operators retain full audit trail
- **Trust spine intact**: replay operations cannot silently rewrite historical truth visible to users

### Rejected alternatives

| option | reason rejected |
|---|---|
| B (visible revisionism with banner) | Past values change retroactively; trust fracture risk |
| C (recomputation overlay) | Adds new UI surface; constitutional scope creep |
| D (invisible internal) | Equivalent to A but stricter; A's audit visibility preferred |

---

## Truth contract

> **`source = 'live'` is canonical. Absence of `source = 'live'` filter on any user-facing reader is a constitutional violation.**

### Allowed source values

| value | meaning | who writes |
|---|---|---|
| `live` | Normal write path: scheduled `run_paper_trading` job, real-time event hooks | auto-trader, intraday recompute, end-of-day snapshot job |
| `replay` | Re-run of a past date via `--as-of` operator flag | `scripts/run_paper_exit_cycle.py`, `scripts/replay_paper_*.py` |
| `backfill` | Initial-load or gap-fill across historical dates | `scripts/backfill_paper_*.py` |
| `operator_manual` | Direct operator intervention (rare; emergency) | admin scripts, operator REPL sessions |

### Writer contract (mandatory)

Every write to `paper_equity_snapshot` MUST specify `source` explicitly. The DB default is a safety net — programmatic absence of explicit source is a code-review fail.

### Reader contract (mandatory)

| reader category | required filter |
|---|---|
| User-facing canonical (AI's Portfolio, Today, equity curve, performance) | `WHERE source = 'live'` |
| Operator forensic | optional filter; default unfiltered |
| Engine Inspection (Advanced) | optional filter; default unfiltered |
| Audit log queries | unfiltered |

### Aggregation contract (mandatory)

Any aggregation (SUM, AVG, MAX, GROUP BY, etc.) on user-facing data MUST apply `WHERE source = 'live'` BEFORE aggregation. Aggregations consumed by forensic surfaces may opt out with explicit annotation.

---

## Rollback policy

| environment | policy on M083 downgrade with replay duplicates present |
|---|---|
| dev | snapshot-restore (drop table, restore from pre-deploy `pg_dump`) |
| staging | fail-loud (refuse downgrade if duplicate `(portfolio_id, snapshot_date)` rows exist) |
| production | fail-loud + pre-deploy `pg_dump` snapshot as backup |

`latest-wins` and `earliest-wins` rejected as silent-data-loss patterns.

---

## Enforcement

### CI checks (added with M083)

1. Lint: all calls to `snapshot_equity_now(...)` must include explicit `source=` parameter
2. Lint: all `SELECT ... FROM paper_equity_snapshot` in user-facing API modules must include `source` filter
3. Test: aggregation correctness — synthetic test with mixed live + replay rows asserts user-facing aggregations match live-only values

### Audit (post-deploy)

Daily query log review for queries missing `source` filter on user-facing paths. Any hit = constitutional violation event logged + investigated.

---

## Open questions deferred to implementation

- Whether replay rows surface in the Engine Inspection page (Phase 3 decision; current default: yes, with operator-facing framing)
- Whether backfill rows count as "live truth" once backfill completes and replay no longer applies (current default: no — backfill is forever a distinct source)

These do not block M083 application. Document amendments tracked here.

---

## References

- Phase L Constitution: `PHASE_L_CONSTITUTION.md`
- OVA findings: `OPERATIONAL_VITALITY_AUDIT.md`
- Phase L.3 implementation plan: `PHASE_L_3_IMPLEMENTATION.md`
