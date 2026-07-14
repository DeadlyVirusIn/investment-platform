# Elite Merge-Back Plan — 2026-07-14 (PLAN ONLY — awaits explicit approval)

Evidence: `ELITE_PROGRAM_CONSOLIDATION_REVIEW.md`. Topology makes this a
**conflict-free descendant merge**: `phase-1/ledger` (`d4286e7`) is the
exact merge base; elite (`fb477e0`) is +195 commits, already containing
the paper-isolation hotfix and the prod redaction/ingest-contract content.

## Strategy decision

- **Chosen: Option A executed through a short-lived integration branch
  (Option D-lite).** A `--no-ff` merge preserves the full audited wave
  history (195 commits with their verification evidence in messages),
  creates one revertable integration point, and costs nothing since
  conflicts are zero.
- Option B (rebase): REJECTED — pushed shared branch; history rewrite
  prohibited; zero benefit on a descendant.
- Option C (cherry-pick by wave): REJECTED — reintroduces the
  supersession-chain risk (pf-1/replay-1/board-1/lab-1 intermediates) for
  no gain; migrations 101–121 must travel together anyway.
- Squashing: REJECTED for the program body (audit-critical migration and
  fix history); the merge commit itself is the release unit.

## Review groups (for the PR read, not for splitting the merge)

1. Migrations 101–121 + ORM (`models.py`) — read against the migration
   audit table.
2. Accounts/roles/admin era (101–108 consumers; pre-Elite backlog).
3. Thesis Ledger + Learning Loop + Research Inbox (110–113 consumers).
4. Agent Gateway + execution provenance (114/116/117/121 + Wave 2C).
5. Trust-control spine: Preflight, Posture, Delta, Replay (119/120).
6. Mission Board + research operations (Wave 2B/2C UI).
7. Experiment Lab + evidence corrections (Wave 3A/3A.1).
8. Paper isolation + execution lease (hotfix chain + 118).
9. Security hardening (redaction, CI security workflow, SECURITY_*).
10. Docs/screenshots (91 + 33 files — no code).

## Proposed sequence (NO step executes without approval)

1. **Freeze + record**: capture `phase-1/ledger`@`d4286e7`,
   elite@`fb477e0`; tag `pre-elite-consolidation` on both (annotated,
   pushed) — tags only, no branch mutation.
2. **Create** `integration/elite-arthos-consolidation` from
   `phase-1/ledger`.
3. Hotfix step: **not needed** (already contained — evidence in review
   §6); instead run the three paper-isolation suites as a gate.
4. `git merge --no-ff feature/elite-arthos-provable-ideas` (expected
   clean; abort if ANY conflict appears — that would falsify the
   topology evidence).
5. Copy `docs/security/POLYGON_CREDENTIAL_INCIDENT.md` from
   `release/stage-b1-redaction` (the one release-line-only artifact).
6. Run gates G1–G8 (below) on the integration branch.
7. Produce `docs/roadmap/ELITE_INTEGRATION_REPORT.md` with the gate
   evidence; push the branch; open the review PR into `phase-1/ledger`.
8. On approval: merge PR (merge commit, no squash). Elite flags remain
   OFF everywhere.
9. No deployment; no prod migration; Stage-B promotion stays a separate
   gated plan (`ELITE_ARTHOS_PRODUCTION_PROMOTION_PLAN.md`).
10. Post-merge bookkeeping: mark `mvp/ideas-you-can-follow` superseded
    (do not delete); update session handoff.

## Required gates (all must be green on the integration branch)

- **G1 repo/schema**: clean tree; `alembic heads` = exactly
  `121_research_exec_provenance`; ephemeral postgres:16 upgrade
  base→121 and 121→109 downgrade chain; ORM metadata creates cleanly
  (`Base.metadata.create_all` on ephemeral).
- **G2 backend**: the Wave-1 focused suite (9 files, one command);
  inbox completeness + legacy inbox; mission board unit+pg; provenance
  pg; gateway jobs + gateway http + authz matrix; experiment lab
  unit+pg; lab splits; **paper isolation**: `test_user_book_guard.py`,
  `test_exit_cycle_scoped_pg.py`, `test_paper_user_portfolio_pg.py`;
  scheduler/lease suites. Evidence rule: every claim ships the exact
  command + counts; environment-dependent failures must be shown
  failing IDENTICALLY on clean `phase-1/ledger` with the same command
  (no "byte-identical" assertions without the paired runs).
- **G3 frontend**: `npx tsc --noEmit` · `npm run lint` ·
  `npm run lint:portfolio` · `npm run build` · `npx vitest run` (287
  baseline) · route smoke with ALL `VITE_*` Elite flags unset (no admin
  research/experiments routes registered; no nav links) · 390px smoke.
- **G4 security**: staged-diff secret scan; authz route matrix; owner
  404 posture; agent scope checks; public projection redaction suites;
  no-arbitrary-code Lab pins; migration-121 trigger integrity tests.
- **G5 performance**: `/api/recommendations` timing flags-off vs
  target baseline; board/replay/delta/lab timings (dev baselines: 7ms /
  157ms cold / 127ms cold / 0.5s); API startup import time.
- **G6 feature-off parity (the central proof)**: with every Elite flag
  off on the integration branch — route table diff vs target (only M1
  auth/admin-era routes may differ, each justified); scheduler registry
  diff (no new registered jobs); zero writes to 110+ tables during a
  smoke pass; paper-trading nightly selection identical on the fixture
  suite; recommendation filtering identical (preflight off = byte
  parity, pinned by existing tests); web bundle contains no new nav.
- **G7 code-on-109**: boot the integration API against a 109-schema
  ephemeral DB with all flags off; hit the always-on surfaces (health,
  recommendations, auth, portfolio); zero 500s.
- **G8 docs**: integration report complete; status ledger updated;
  session handoff updated.

## Rollback strategy

- **Code**: `git revert -m 1 <merge-commit>` on `phase-1/ledger`
  restores the pre-merge tree in one commit (tags from step 1 give the
  exact reference); images/deploys are untouched by this plan anyway.
- **Flags**: every feature disables independently; couple
  Preflight+Posture (posture consumes preflight seams); lease flag
  independent; no feature leaves irreversible writes running when
  disabled (append-only ledgers simply stop growing).
- **Schema**: additive-only ⇒ prefer LEAVING schema in place on any code
  rollback (verified safe: old code ignores new tables/columns;
  triggers only guard columns old code never writes). Full downgrade
  121→109 exists and was exercised for 121 (and per-revision earlier);
  it deletes only Elite-era data (acceptable in dev; in prod it would
  delete promoted-era data — never run casually). Dev restore point:
  `.backups/devdb_full_20260714_pre3a1.dump`.

## What stays dev-only after the merge (and its unlock)

| Item | Why dev-only | Unlock evidence |
|---|---|---|
| Migrations 110–121 in prod | prod promotion is Stage-B gated | Stage-B plan stages 1–7 |
| Preflight/Posture flags | need prod calibration + owner drills | staged Stage-B enablement |
| Delta/Replay flags | no migration, but user-facing wording | owner review post-merge |
| Inbox/Board/Gateway/Thesis/Learning | operator surfaces; single-owner beta posture | Stage-B + owner usage |
| Execution lease flag | needs 118 in prod first | apply 118, then P0-5 closure evidence |
| Experiment Lab | evidence tool; INSUFFICIENT verdicts; single-user | indefinite dev; Arena gate |
| LightGBM adapter | BLOCKED (≤2 folds < 4) | snapshot depth ≈ late 2026-08 |
| Migration 122 (themes/links) | design-gated on 121 usage | owner-usage evidence review |
| Replay campaign (2024-H2/2025 windows) | new-evidence decision | separate approval |
| Rebuilt historical_label + lab run rows | dev DB data | never merged; data, not code |
| Arena + promotion queue | premature (one adapter) | ≥2 adapters + non-INSUFFICIENT verdicts |

## Estimated integration risk: **LOW**

Zero conflicts, all-flag-off inert-by-design, additive schema, hotfix
contained, dependencies unchanged. Residual risk = review breadth (56k
lines) — addressed by the group map; and the G6/G7 proofs, which are the
only genuinely new evidence this plan demands.

## Overall: **READY FOR CONSOLIDATION BRANCH** — awaiting explicit approval to execute step 1.
