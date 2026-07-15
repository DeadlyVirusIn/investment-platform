# Stage-B Production Promotion — Kickoff Checklist (PLAN ONLY, 2026-07-14)

**Nothing in this document is executed.** Every step requires separate
explicit approval. Complements
`ELITE_ARTHOS_PRODUCTION_PROMOTION_PLAN.md` (7-stage plan) with the
post-consolidation specifics. Baseline evidence:
`ELITE_INTEGRATION_REPORT.md` (gates G1–G8).

## 1. Production baseline (verify FIRST, read-only, vm-guard flow)

- [ ] Deployed commit == `1fb6e28` (last verified 2026-07-13)
- [ ] `alembic_version` == `109_research_run` (last verified 2026-07-13)
- [ ] Fresh full prod DB backup taken + `pg_restore --list` readable +
      off-VM copy (open backlog item)
- [ ] Current env flags captured (`docker exec … env | sort` per service)
- [ ] All 6 services healthy; disk ≤ 85% guard (was 83% after cleanup)
- [ ] Scheduler state: job_schedule rows + next_run_at sane; no NULL
      next_run_at; supercronic + tick-loop both accounted (P0-5 context)
- [ ] Release checkout clean (no dirty tree on the VM)
- [ ] Rollback images tagged (`rollback-stageb1` set exists; add
      `rollback-elite` tags at deploy time)

## 2. Migration sequencing 110 → 121 (one maintenance window, in order)

Preconditions for the block: fresh backup (above); ephemeral rehearsal on
a prod CLONE first (gate V1). All twelve are additive; none carries a
data migration; every downgrade exists. Apply with the compose alembic
one-shot (`--env-file .env`!), one `upgrade 121_research_exec_provenance`
invocation (single transaction per revision).

| Rev | Objects | Lock profile | Old code tolerates? | New code requires? | Verify query |
|---|---|---|---|---|---|
| 110 thesis(+revision) | new tables | create-only, no existing-table locks | yes (unknown tables) | only if THESIS flag on | `\dt thesis*` + count 0 |
| 111 evidence/catalyst/risk/link | new tables | create-only | yes | flag-gated | counts 0 |
| 112 research_task/report | new tables | create-only | yes | flag-gated | counts 0 |
| 113 lesson | new table | create-only | yes | flag-gated | count 0 |
| 114 agent_token/audit | new tables | create-only | yes | flag-gated | counts 0 |
| 115 paper_trade.execution_cost_json | nullable col on HOT table | brief ACCESS EXCLUSIVE on paper_trade (nullable, no default → metadata-only) — run OUTSIDE the nightly trading window | yes (never selects it) | only when cost flag on | column exists; existing rows NULL |
| 116 agent_job/event/idempotency | new tables | create-only | yes | flag-gated | counts 0 |
| 117 research_report.generated_by | nullable col (new table anyway) | trivial | yes | flag-gated | column exists |
| 118 execution_lease | new table | create-only | yes | only when lease flag on | count 0 |
| 119 recommendation_preflight | new table + indexes | create-only | yes | preflight flag | count 0 |
| 120 system_posture_event | new table (UNIQUE NULLS NOT DISTINCT — needs PG15+; prod PG version check!) | create-only | yes | posture flag | count 0 |
| 121 agent_job.research_task_id + research_task.source_report_id + composite FK + 2 triggers | cols on NEW tables + triggers | trivial (tables empty in prod) | yes | provenance features | triggers `trg_arthos_*` present |

Downgrade posture: full chain 121→109 exists (G1-proven with data
survival at 109); in prod prefer NEVER downgrading once Elite data
exists — rollback = flags off + leave schema.

## 3. Code deployment order — verdict: **schema-first**

G7 proved code-on-109 boots clean (so code-first also works), but
schema-first is still safest: it removes the only unproven prod pairing
(new code + old schema under real traffic patterns) and G1/G6 proved old
code + DB121 is inert. Sequence:

1. prod backup (fresh, verified);
2. apply 110–121 (window; old code keeps running — additive-only);
3. build + tag rollback images; deploy merged `phase-1/ledger`
   (`3ad3ca7`+) with ALL Elite flags off (api, worker-cron,
   worker-tickloop, web);
4. flag-off parity smoke (gate V2);
5. staged flag enablement (§4), each its own approval.

## 4. Flag enablement order (each = prerequisites → smoke → rollback → monitoring → owner approval)

1. **Baseline era (no flag)** — accounts M1, admin console, model
   portfolios ship enabled-by-architecture; smoke: signup/login/session,
   owner 404 posture. Data: app_user/session rows. Monitor: login_attempt.
2. **`PAPER_EXECUTION_LEASE_ENABLED`** — prereq 118 + one clean nightly
   observed; smoke: single-executor log line, no duplicate exit-cycle;
   rollback: flag off (legacy path byte-identical); monitor: job_run
   duplicates. CLOSES P0-5 in prod.
3. **Paper cost stamping flag** — prereq 115; smoke: new fills carry
   execution_cost_json, old rows NULL; rollback: flag off (NULL stamps).
4. **`THESIS_LEDGER_ENABLED` / `RESEARCH_INBOX_ENABLED` /
   `LEARNING_LOOP_ENABLED`** (owner-only surfaces) — prereq 110–113,
   117, 121; smoke: owner CRUD + 404 posture as non-owner; data:
   append-only ledgers; rollback: flags off (history retained).
5. **`AGENT_GATEWAY_ENABLED`** — prereq 114/116 + fresh security review
   (documented blocker) + single-replica rate-limiter note; smoke: token
   mint/revoke, scope matrix, audit rows; rollback: flag off + revoke-all.
6. **`RECOMMENDATION_PREFLIGHT_ENABLED` + `SYSTEM_POSTURE_ENABLED`
   (coupled)** — prereq 119+120 + posture schedule row (runbook) + owner
   drill (SAFE → ack → RESTRICTED) on staging first; smoke: truthful
   verdicts, no synthetic-HOLD storms, Discover latency ≤ ~1.2s cold;
   rollback: flags off = byte-parity (pinned); monitor: preflight verdict
   mix + posture events.
7. **`REC_DELTA_ENABLED`** — no migration; smoke: delta on a known
   symbol; rollback trivial.
8. **`DECISION_REPLAY_ENABLED`** — no migration; smoke: timeline for a
   rec with outcome; user-isolation spot check; rollback trivial.
9. **`RESEARCH_INBOX` board surface (`VITE_RESEARCH_INBOX`)** — web-only
   companion of 4; mission-board-2 smoke.
10. **`EXPERIMENT_LAB_ENABLED`** — dev/staging ONLY; not part of prod
    Stage-B (explicit non-goal below for public exposure).

## 5. Verification gates (each with recorded evidence)

- V1: 109→121 rehearsal on a prod-clone restore (also proves backup
  restorability — kills two backlog birds)
- V2: code-on-121 flag-off smoke = G6 parity re-run against prod stack
  (route table, scheduler registry, zero Elite-table writes,
  recommendation parity vs pre-deploy capture)
- V3: paper user-book isolation proof on prod data (read-only queries +
  one observed nightly: zero engine trades on `user:%` books)
- V4: security scan + owner authz matrix against prod URL (owner 404s)
- V5: performance baseline before/after deploy (recommendations, Discover)
- V6: rollback drill on staging (image retag + flags off)
- V7: post-window monitoring: 48h of nightly pipeline green before any
  flag beyond #2

## 6. Explicit non-goals (Stage-B excludes)

Migration 122 · replay campaign · LightGBM adapter · Comparison Arena ·
automatic model promotion · live trading · public leaderboard · public
Experiment Lab. Each requires its own future design/approval cycle.

## Approval points

A. This checklist reviewed → approve V1 rehearsal.
B. V1 green → approve prod migration window (110–121).
C. Migrations verified → approve code deploy (flags off).
D. V2–V5 green → approve flag stage 2 (lease). Subsequent flags: one
   approval each, in order, with its smoke + rollback evidence.

## V1 STATUS — 2026-07-14: production-clone rehearsal completed
**V1 PASS WITH REMEDIATIONS** — full evidence in
`STAGE_B_V1_PROD_CLONE_REHEARSAL_REPORT.md`. PG 17.10 (120 compatible);
fresh prod backup restored (checksum-verified) = backup-restorability
proof; 110→121 sequential clean (<8s, no rewrite — 115 metadata-only);
downgrade+re-upgrade repeatable; both code eras boot on DB 121;
feature-off write audit zero; paper isolation proven on the real 73-book
inventory. Remediations before Approval B: P-1 (419 job_run orphans
under a "valid" FK — restore always errors until repaired) and P-2
(prod checkout drift: 1d9b175 + 3 dirty files). Approval Point B not
crossed.

## Remediation status — 2026-07-15
**P-1 RESOLVED IN PRODUCTION**: 419 orphan job_run rows (prod-genesis
dev-clone artifact, root-caused) archived to CSV + deleted in one
guarded clone-tested transaction; FK re-added with FULL validation
(convalidated now genuinely true); restore-after-cleanup proven ZERO
errors; fresh pre-apply backup retained (~/backups/
proddb_pre_p1_20260715.dump, sha256 7586097d…). **P-2 RESOLVED
(analysis)**: all three audited drifted files are COMMITTED_EQUIVALENT_
EXISTS (two byte-identical to committed blobs, config a strict subset
of ledger's); drift mechanism = file-copy deploys of the admin era;
checkout drift eliminated by the next image replacement — no live
edits. Evidence: docs/ops/P1_P2_REMEDIATION_LOG_20260715.md.
**Rebuild readiness: READY TO REBUILD ON DB 109 — FLAGS OFF** (rebuild
execution + Approval Point B each remain separate explicit decisions).
