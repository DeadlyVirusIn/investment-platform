# Elite Program Consolidation Review — 2026-07-14

**PLAN-ONLY.** Nothing merged, rebased, deployed, migrated, tagged, or
deleted. Companion: `ELITE_MERGE_BACK_PLAN.md`.

## 1. Repository truth (verified now, not from handoffs)

| Ref | SHA | Notes |
|---|---|---|
| `feature/elite-arthos-provable-ideas` | `fb477e0` | local == origin; this worktree; clean except untracked `ge_tl.json` (owner artifact) |
| `phase-1/ledger` | `d4286e7` | == origin; **origin default branch**; STALE (2026-05 era, pre-migration-101) |
| `hotfix/user-paper-engine-isolation` | `dc36058` | == origin; **ancestor of elite** |
| `mvp/ideas-you-can-follow` | `52a5e3b` | main-repo worktree branch; = elite's parent line (`e091453`) + ONE duplicate cherry-pick |
| `release/stage-b1-ingest-contracts` | `1fb6e28` | **prod-deployed code line** |
| `release/stage-b1-redaction` | `08ed935` | prod redaction release (pushed, not deployed) |

Worktrees (5 — all other sessions' dirs untouched): main repo
(`mvp/ideas-you-can-follow`), `-b1` (stage-b1-redaction), `-elite` (this),
`-hotfix` dir (on `research/external-quant-ai-review`), `-recon`.
Stashes: 3 (pre-elite eras) — **do not drop**. Tags: 4 historical. No
submodules, no LFS. Local-only branches: the old v2/feat/docs lines +
`main`, `phase-x/*`, `wip/*` — none block consolidation.

### The topology headline

```
merge-base(elite, phase-1/ledger) = d4286e7 = phase-1/ledger HEAD
elite ahead: 195 commits · ledger ahead: 0
```

**Elite is a strict descendant of `phase-1/ledger`.** The merge-back is a
fast-forward by construction — `git merge-tree` degenerates: there are
ZERO textual conflicts and zero divergent history to reconcile.
Everything below is therefore about *auditability, data hygiene, and
flag-off proof*, not conflict resolution.

## 2. Diff inventory (d4286e7 → fb477e0)

195 commits · 423 files · +56,262 / −955. By area: web 100 · docs 91 ·
backend tests 58 · screenshots 33 · backend api/config 33 · backend
domain 29 · **migrations 21 (101–121)** · web tests 19 · scripts 14 ·
worker 7 · ml 7 · infra (compose/docker/caddy/Makefile/CI security
workflow/.env.example) 8 · SECURITY_AUDIT/BACKLOG 2.

Dependencies: **Python unchanged** (no statsmodels, no Optuna, no new
libs — verified: pyproject/requirements absent from the diff). Web adds
ONLY test tooling (vitest, jsdom, @testing-library/*) as devDependencies.
No AGPL code or dependency anywhere (clean-room policy held; verified
against the gap-review's licensing wall). `.env.example` additions are
auth/session/CORS documentation (M6) — **no Elite feature flag appears in
any deployment template**; all live in config defaults, OFF.

## 3. Commit archaeology — supersession chains (must merge as FINAL states)

Because this is a descendant merge, intermediate defective states cannot
be "stopped at" accidentally — but for audit these chains are recorded:

| Chain | Defective intermediate | Final state (in elite) |
|---|---|---|
| Preflight pf-1 → pf-2 | wall clock in verdict hash | pf-2 fact-bucket identity + bulk path + cap fix |
| Replay replay-1 → replay-2 | unproven lifecycle continuity | replay-2 stored-fact continuity |
| Mission Board 1 → 2 | task-less Running/Failed | mission-board-2 task-aware via migration 121 |
| Lab lab-1 → lab-1.1 | replay-variant pooling; incomparable returns | lab-1.1 scoping + CRITICAL warning + matched accounting |
| Hotfix `7876124`/`dc36058` → lease `5fa29c8`/`a876558` | dual-scheduler double-run | fence-token execution lease (flag off) |
| Wave 2A corrections → Wave 2C | free-text follow-up provenance | composite-FK `source_report_id` + triggers |

No cherry-pick plan may take an earlier link without its chain; the
recommended strategy (below) takes all-of-it atomically, which moots the
risk.

## 4. Migration audit 101–121

Verified: **single linear head `121_research_exec_provenance`**, no
duplicate revision ids, no branch labels, no merge revision needed, all
version strings ≤32 chars (121 was renamed for this during Wave 2C).
101–108 are the accounts/roles/portfolio era (pre-Elite, carried because
ledger is stale); 109–121 are the Elite program. All additive: new
tables, nullable columns, CHECKs, two triggers (121). Data migrations:
none (no UPDATE/backfill in any revision). Downgrade: every revision has
a tested downgrade; 121's was proven up/down/up on postgres:16 with
behavioral matrix 16/16; full-chain 109→121 upgrade was exercised
piecewise on dev (each applied after backup) and 110–121 run as a block
on ephemeral containers in earlier waves. Feature-flag dependency: every
feature reading 110+ tables is flag-mounted; migrations can exist with
features off (proven daily on dev since each landed).

Prod dependency: prod is at `109_research_run` — **verified read-only via
the vm-guard flow on 2026-07-13** (`ptcgp-server`, `alembic_version =
109_research_run`); prod code = `1fb6e28`, all Elite flags absent/off
(per stage-B evidence; unchanged since). Promotion applies 110–121 in
sequence during the SEPARATE Stage-B plan — never part of this merge.

## 5. Flag matrix (authoritative; all defaults verified in config)

| Feature | Server flag (default) | Web flag | Off-behavior | Prod recommendation |
|---|---|---|---|---|
| Thesis Ledger | `THESIS_LEDGER_ENABLED` (False) | — | router unmounted | keep off; Stage-B item |
| Research Inbox (+Board) | `RESEARCH_INBOX_ENABLED` (False) | `VITE_RESEARCH_INBOX` | routes absent, zero queries | keep off; staged dev use |
| Learning Loop | `LEARNING_LOOP_ENABLED` (False) | — | unmounted | keep off |
| Agent Gateway | `AGENT_GATEWAY_ENABLED` (False) | — | router+middleware absent; /agent 404 | keep off |
| Paper cost stamp | `PAPER_COST_MODEL_ENABLED`-family (False) | — | no stamp writes | keep off until 115 applied |
| Execution lease | `PAPER_EXECUTION_LEASE_ENABLED` (False) | — | byte-identical legacy path | enable ONLY after 118 in prod (P0-5 fix) |
| Preflight | `RECOMMENDATION_PREFLIGHT_ENABLED` (False) | — | no verdict writes/reads | keep off until 119 |
| System Posture | `SYSTEM_POSTURE_ENABLED` (False, + override seam) | — | Wave-1A byte-parity | keep off until 120; couple with Preflight |
| Delta | `REC_DELTA_ENABLED` (False) | — | route absent | eligible (no migration) after merge |
| Decision Replay | `DECISION_REPLAY_ENABLED` (False) | — | routes absent | eligible (no migration) |
| Experiment Lab | `EXPERIMENT_LAB_ENABLED` (False) | `VITE_EXPERIMENT_LAB` | routes/UI absent, zero registry writes | dev-only indefinitely |
| Ingest contracts | `INGEST_CONTRACTS_ENABLED` (False) | — | ingest unchanged | prod decision belongs to Stage-B line |
| Meets-buy-bar copy | — | `VITE_MEETS_BUY_BAR` (on) | wording only | as-is |

No temporary overrides found. **No new flag appears in
docker-compose*.yml or .env.example** — defaults rule.

## 6. Hotfix interaction verdict: **NO CONFLICT (contained + hardened)**

- `dc36058` (hotfix head) is an **ancestor of elite**; elite additionally
  carries `7876124` ("engine jobs must never trade per-user paper books")
  and the later lease/fencing fixes on the same paths.
- `52a5e3b` on `mvp/ideas-you-can-follow` is a **duplicate cherry-pick of
  the same P1 fix** (same title/content); diffing it against elite HEAD
  on all its files shows elite ⊇ 52a5e3b (elite adds only the flag-gated
  lease guard). After merge-back, `mvp/ideas-you-can-follow` is
  semantically superseded (do NOT delete; record).
- The defect (engine jobs trading user books) cannot be reintroduced:
  elite's guards are supersets, pinned by `test_user_book_guard.py`,
  `test_exit_cycle_scoped_pg.py`, `test_paper_user_portfolio_pg.py` — all
  in elite and required gates below.
- `hotfix/user-paper-engine-isolation` is **NOT in phase-1/ledger** — the
  merge-back is what finally lands it in the default branch.

## 7. Release-line (prod) relationship

`release/stage-b1-*` branched from `5cdb099` (in elite). Their unique
commits (`eeb7c0c`, `f9e85c0`, `1fb6e28`, `08ed935`) = ingest contracts +
redaction release. Byte-comparison: contracts files identical to elite;
redaction module identical with elite carrying superset comments + one
extra `_redact_store` application. **Single artifact existing ONLY on the
release line: `docs/security/POLYGON_CREDENTIAL_INCIDENT.md`** — carry it
into the consolidation as a doc copy (no code impact). Prod continuity is
therefore preserved: everything running in prod exists (or is improved)
in elite.

## 8. Data classification

**Merge-safe (code+schema, flags off):** everything in the 423-file diff.

**Must NEVER reach prod (dev DB data, not in git):** rebuilt
`historical_label` rows (1,601, engine_version
`stock_swing_v1:f9a7e0dc3cf3f74c`); Lab `research_run` evidence rows
(`rr_20260714_*`, 7 lab rows); posture drill events; preflight dev
verdicts; append-only inbox/audit fixtures. These live only in the dev
database — merge moves no data.

**Immutable dev evidence to RETAIN in dev:** the 7 lab research_run rows,
posture event ledger, agent_audit rows.

**Generated files in git (reviewed for leakage):** 33 screenshots + JSON
matrix + reports. Scan: no secrets, no emails beyond
`smoke-*@example.com` / `owner@example.com` fixtures, token PREFIXES only
(public by design), dev UUIDs only (dev-DB identifiers, non-sensitive),
no hostnames beyond localhost. Acceptable to keep; nothing blocks.

## 9. Code/schema compatibility matrix

| State | Old code (`d4286e7`/`1fb6e28`) | New code (`fb477e0`, flags off) |
|---|---|---|
| DB @ prod 109 | **SUPPORTED** (prod today) | **EXPECTED SUPPORTED — must be PROVEN** by the feature-off gate: risk points are always-mounted surfaces touching ≥110 columns. Known-safe by design: admin_guard has a pre-108 fallback; every 110+ consumer is flag-mounted; paper cost stamping is flag-gated. Gate G6 (below) is the proof. |
| DB @ 121 | **SUPPORTED** (additive-only: new tables/nullable columns; triggers fire only on columns old code never writes) | **SUPPORTED — proven** (dev runs this exact pair daily) |

Staged-deployment constraint: none hard; preferred order remains
schema-then-code per the Stage-B promotion plan.

## 10. Risk register

- Ownership: 5 worktrees, 3 stashes — plan touches none.
- `phase-1/ledger` being stale means the merge is big (56k lines) but
  conflict-free; the risk is REVIEW fatigue, not integration failure —
  mitigated by the group-by-wave review map in the plan.
- Force-push/rebase: prohibited and unnecessary (descendant merge).
- Unpushed local branches (v2-era) are historical; not part of this plan.

## Final verdicts

1. Target: `phase-1/ledger` @ `d4286e7` (origin default; stale by design)
2. Elite: `feature/elite-arthos-provable-ideas` @ `fb477e0` (== origin)
3. Hotfix: `dc36058` — ancestor of elite; not in ledger; duplicate
   cherry-pick `52a5e3b` on mvp superseded by elite
4. Merge base = `d4286e7` (= target head); elite +195 / target +0
5. Migrations: 101–121 linear, single head, additive, all downgrades
   present; prod at 109 (verified 2026-07-13)
6. Conflicts: **ZERO** (strict descendant)
7. Flag-off parity: designed-in and per-wave verified; final proof =
   required gate G6, not yet re-run as one suite
8. Compatibility: matrix above — no blocked state
9. Hotfix interaction: **no conflict — contained and hardened**
10. Dev-only data: §8 (DB rows only; git carries no dev data)
11. Gates: plan §Gates (G1–G8)
12. Strategy: **Option D-lite / Option A** — `--no-ff` merge commit via a
    short-lived integration branch (plan §Strategy)
13. Rollback: revert-merge / per-flag / schema-stays (plan §Rollback)
14. Integration risk: **LOW**

## Overall verdict: **READY FOR CONSOLIDATION BRANCH**
