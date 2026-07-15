# Stage-B V1 — Production-Clone Migration Rehearsal Report (2026-07-14)

Scope: **V1 only** (approval point A). Isolated clone; **production was
not mutated** — the only prod interactions were approved read-only
queries and the routine `pg_dump` backup procedure (vm-guard,
per-command markers). No secrets in this report.

## Production baseline (read-only evidence)

| Fact | Value |
|---|---|
| Host | `ptcgp-server` (150.136.38.189) |
| Deployed checkout | `1d9b175` with a **DIRTY tree** (3 modified files: `admin_observability.py`, `auth/identity.py`, `config/__init__.py`) — **production drift finding**; reconcile before Approval B |
| PostgreSQL | **17.10** (aarch64/musl) → migration 120's `UNIQUE NULLS NOT DISTINCT` supported (needs ≥15) — **compatibility gate PASS** |
| Migration head | `109_research_run` |
| DB size | 3,731 MB · extensions: `plpgsql` only |
| Activity | 1 active connection, 0 transactions >5min |
| Top tables | price_bar ~4.71M · recommendation_evidence 1.80M · recommendation 225,414 · outcomes 225,370 · paper_trade 4,042 · paper_position 1,643 |
| Services | 6 up/healthy (api, worker-cron, worker-tickloop, caddy, web, db) |
| VM disk | 85% before / 87% during backup / temp deleted after transfer (df lag noted — re-check at next touch) |

## Backup + restore (the backup-restorability proof)

- Fresh dump: `pg_dump -Fc` in-container → 453,912,844 bytes, sha256
  `6e3d8be8f2377d60ce4858de1e1705b2389a24ca3df3796aaf642daa57646e61`;
  scp'd locally (checksum verified identical); VM temp copies removed.
  Local copy: `.backups/proddb_v1_20260714.dump` (git-ignored).
- Isolated restore: dedicated container `pgv1clone`
  (postgres:17-alpine, port 55440, db `prodclone_v1`, own credentials —
  no production reachability, read-only dump mount, no workers, all
  flags off). Restore ~35–39s (repeated ×4).
- Restore errors triaged to zero unexplained: three missing prod ROLES
  (`research_writer`, `research_reader`, `invest_prod`) pre-created →
  ACL statements clean; ONE data error remains and is a
  **production integrity finding**, not a restore defect:

### FINDING P-1: `job_run` orphans under a "valid" FK

419 of 524 prod `job_run` rows reference `job_schedule` ids that no
longer exist, while `job_run_job_schedule_id_fkey` reports
`convalidated = true` in prod (verified read-only). A past repair likely
bypassed FK enforcement. Consequence: **every prod restore will fail
this constraint** until repaired. Clone handling: constraint recreated
`NOT VALID` (mirrors de-facto prod state). Recommendation before
Approval B: owner decision — delete orphan runs or accept + document;
low risk either way (job telemetry only).

- Verification: head exactly 109; exact count matches vs prod
  (recommendation 225,414, outcomes 225,370, paper_trade 4,042,
  paper_position 1,643; price_bar exact 4,710,143 vs prod stats
  estimate 4,710,175 — estimates + live ingest between reads); id-set
  md5 checksums captured for 8 key tables; sequences and constraints
  restored (single explained exception above); prod personal data
  stayed inside the isolated container.

## Migration rehearsal 110 → 121

Sequential per-revision, exit=0 each, head `121_research_exec_provenance`.
Repeat run (post-downgrade) with timing:

| Rev | Wall time* |
|---|---|
| 110–121 (each) | 0.64–0.69s |
| **Total** | **7.9s** (*includes ~0.4–0.5s alembic/python startup per revision; net DDL is milliseconds) |

Lock findings: no lock waits, no blocked sessions (idle clone), and —
decisive for 115 — **no table rewrite**: whole-DB size moved 3,104 →
3,105 MB across all 12 migrations. `ADD COLUMN … NULL` on PG17 is
metadata-only; the ACCESS EXCLUSIVE on `paper_trade` (4,042 rows) is
held for milliseconds. Not separately load-tested under concurrency
(idle clone) — production window recommendation stands regardless:
**run outside the nightly trading window**, expected total < 1 minute
including operator steps.

Special attentions verified on the migrated clone:
- **115**: all 4,042 historical `paper_trade.execution_cost_json` NULL.
- **118**: `execution_lease` present + empty; no lease acquired (flag
  off); legacy execution path untouched.
- **119/120**: zero preflight/posture rows created by migration;
  constraints present.
- **121**: both `trg_arthos_*` triggers present; valid task insert OK;
  illegal `source_report_id` update **RAISES** (proven on real restored
  data); unrelated status update OK; historical rows NULL; no backfill.

Post-migration integrity: **id-set checksums identical pre/post** for
all 8 sampled tables; all 17 new tables empty; one alembic head.

## Compatibility matrix (on the clone)

| State | Old prod code (`1fb6e28` proxy†) | New `phase-1/ledger` code (flags off) |
|---|---|---|
| DB 109 | prod today (baseline) | **PASS** — G7 integration evidence (boot + endpoints + zero errors) |
| DB 121 | **PASS** — boots; health/recommendations/session/canonical-paper/model-portfolios all 200; scheduler registry imports clean | **PASS (mandatory case)** — boots; same endpoints 200 against REAL prod data; Elite routes 404; route table = G6 evidence |

†The exact deployed code is `1d9b175`+dirty (finding above); `1fb6e28`
is the nearest committed state.

## Feature-off write audit

After the new-code smoke on DB 121: combined row count across thesis,
research_task, research_report, lesson, agent_token, agent_job,
execution_lease, recommendation_preflight, system_posture_event =
**0**. Zero Elite writes.

## Paper-safety rehearsal (real prod inventory)

73 paper books restored, **54 `user:` books**: `user_paper_book_ids`
resolves exactly those 54; engine-set ∩ user-set = **0**;
`is_user_paper_book` classifies all names correctly both directions;
cost stamps 0; leases 0. Engine-path selection (nightly/rebalance/
exit-cycle/pending-fill) is pinned by the isolation suites run this
session on the same tree (`test_user_book_guard` +
`test_exit_cycle_scoped_pg` + `test_paper_user_portfolio_pg` = 12
passed; gateway/paper route selection 149 passed). No broker/webhook/
email/Discord paths exercised; no schedulers ran.

## Downgrade + repeatability + fallback

- Snapshot copy (`clone_snap`, TEMPLATE of the migrated clone) +
  planted `research_run` probe → `downgrade 109`: **0.8s**, head 109,
  probe SURVIVED, all sampled Elite tables/triggers gone, pre-109 data
  intact (recs 225,414 / trades 4,042). Elite-era schema+data removed =
  exactly the 110–121 objects (all empty in this rehearsal).
- Re-upgrade 109→121 on the snapshot: clean (the timing table above) —
  **repeatable**.
- Fallback: second independent restore (`clone_refetch`) from the
  ORIGINAL dump — same single explained error, head 109, counts match;
  dump checksum re-verified unchanged. Production downgrade remains
  NOT the recommended rollback — code rollback with additive schema
  retained is preferred.

## Storage + performance summary

Restore 35–39s · full migration <8s wall · DB 3,104→3,105 MB (+1MB) ·
dump 433MB · free-space multiplier for the prod host: dump (~0.45GB) +
restored copy only if restoring ON-VM (not required; local rehearsal) —
prod migration itself needs no extra space beyond +~1MB. API startup
(clone): old ~15s, new ~18s to ready (single sample each, same box).
Recommendation endpoint parity previously measured 65–90ms both codes.

## Security controls

No emails/webhooks/Discord/broker calls (no such code paths exercised;
old-code market-tape poller self-disabled without its API key; new code
had MARKET_TAPE_ENABLED=false). No live scheduler. No production
callbacks. Logs redacted; no secrets in this report or in Git; dump is
git-ignored and local-only. Retention: `pgv1clone` container STOPPED
and retained (db `prodclone_v1` at 121) for Approval-B reuse — remove
with `docker rm pgv1clone`; scratch DBs dropped; VM temp files deleted.

## Issues / remediations

1. **P-1 job_run orphans** (above) — owner decision before Approval B.
2. **P-2 prod checkout drift** (`1d9b175` + 3 dirty files) — diff the
   dirty files vs the release branch and commit or revert them before
   the Stage-B deploy, so the deployed state is reproducible.
3. df lag / disk 87% reading on the VM — re-check on next touch
   (temp files were deleted).

## Verdict

**V1 PASS WITH REMEDIATIONS** (P-1, P-2 — neither blocks migration
mechanics; both should be resolved or explicitly accepted at Approval
Point B).

Approval Point B (next human decision): authorize applying migrations
110–121 to production with every feature flag remaining off. This
mission does not cross it.
