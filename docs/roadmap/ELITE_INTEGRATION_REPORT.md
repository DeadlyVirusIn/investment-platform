# Elite Integration Report — integration/elite-arthos-consolidation (2026-07-14)

Executed per `ELITE_MERGE_BACK_PLAN.md` with the corrected tag naming.
**PR pending; nothing merged into `phase-1/ledger`; nothing deployed;
production untouched (migration 109 / `1fb6e28`, prior read-only
verification 2026-07-13 — not re-read for ceremony).**

## Topology (reverified immediately before mutation)

- `phase-1/ledger` local == origin == `d4286e7` (0 ahead — unchanged)
- `feature/elite-arthos-provable-ideas` local == origin == `a055c63`,
  strict descendant of ledger (+196 commits)
- Working tree clean (one owned untracked scratch file in the elite
  worktree); 5 pre-existing worktrees + 3 stashes present before and
  after; no pre-existing `pre-elite-consolidation*` tags or integration
  branch anywhere.

## Artifacts created

| Artifact | Value |
|---|---|
| Tag `pre-elite-consolidation-ledger` | annotated at `d4286e7`, pushed |
| Tag `pre-elite-consolidation-elite` | annotated at `a055c63`, pushed |
| Branch `integration/elite-arthos-consolidation` | from `d4286e7` (temp worktree; `phase-1/ledger` itself untouched) |
| Merge commit | `acb6eb6` (`--no-ff`, **zero conflicts**) |
| **Tree-identity proof** | merge tree OID `2b79347a9fd433a483433e9ae8b4858defbd8da7` == elite `a055c63` tree OID — gate results on identical content transfer exactly |
| Release-line doc commit | `4d26523` — `docs/security/POLYGON_CREDENTIAL_INCIDENT.md` copied verbatim from `release/stage-b1-redaction @ 08ed935`; inspected: documentation only, placeholder tokens (`SHOULD_NOT_APPEAR`), no credentials/hostnames/PII |

## G1 — repository & schema: **PASS**

Ephemeral `postgres:16-alpine` (never the dev DB):
`alembic upgrade 109_research_run` → plant a `research_run` probe row →
`upgrade head` (= `121_research_exec_provenance`; all 110–121 tables,
both `trg_arthos_*` triggers, `agent_job.research_task_id`,
`paper_trade.execution_cost_json` verified present) → `downgrade
109_research_run` (probe row SURVIVED; zero Elite tables/triggers/
functions remain) → `upgrade head` again (probe still present).
`alembic heads` = exactly one; duplicate-revision scan clean (an initial
grep hit was the pattern matching `down_revision` lines — refuted);
no `branch_labels`. `Base.metadata.create_all` on a clean DB: ORM tables
(68) ⊆ migrated tables (150); **zero ORM-only tables**; migration-only
extras are the documented raw-SQL-managed subsystems (agent gateway,
alpha, options).

## G2 — backend: **PASS with 4 pre-existing failures (paired-run proven)**

Env: local venv (`../investment-platform/.venv`), testcontainers
postgres:17; commands recorded verbatim in session.

- Combined Wave-1 + research-ops + gateway + authz + lab selection
  (22 files, one command): **480 passed, 1 failed, 41.67s**.
  Failure `test_agent_gateway_http_pg.py::test_route_scan_no_trade_
  mutation_endpoints`: file does not exist on target (gateway is new);
  proven failing on clean elite HEAD via stash-run during Wave 2C —
  pre-existing source-branch collection-order issue, not a merge
  regression. Ticket-worthy, non-blocking.
- **Paper-safety trio (mandatory)**: `test_user_book_guard.py` +
  `test_exit_cycle_scoped_pg.py` + `test_paper_user_portfolio_pg.py` →
  **12 passed, 4.41s**. No engine workflow selects `user:%` books.
- Lease/engine selection (`test_execution_lease_pg.py`,
  `test_paper_trading_pg.py`, `test_paper_exit_cycle_pg.py`,
  `test_rebalance_engine_pg.py`, `test_run_paper_daily_gate_alignment_
  pg.py`, `test_paper_cost_audit_pg.py`): **63 passed, 3 failed**.
  The same three tests (`test_api_portfolio_create_and_trade`,
  `test_api_snapshot_and_equity_curve`,
  `test_weekly_rebalance_job_runs_for_all_active_portfolios`) were
  re-run with the SAME command on a clean `d4286e7` worktree
  (`../ip-g2-baseline`): **same 3 fail there** (29 pass — fewer tests
  exist on target). Classification: pre-existing on target,
  environment-dependent. Evidence rule satisfied (paired outputs).

## G3 — frontend: **PASS**

From `apps/web` (tree-identical content): `npx tsc --noEmit` → no
errors · `npm run lint` → no issues · `npm run lint:portfolio` → gate
passed · `npm run build` → OK · `npx vitest run` → **287 passed, 0
failed**. Flag-off route absence is structural
(`researchInboxEnabled()` / `experimentLabEnabled()` guard route
REGISTRATION) and pinned by the suites' feature-off tests; no Elite nav
links render with `VITE_*` unset (existing tests + G6 route diff).
390px and zoom smokes were exercised per-wave with committed
screenshots; no always-on surface changed in this merge.

## G4 — security: **PASS (zero findings)**

Full integration diff (`d4286e7..HEAD`) credential-pattern scan: 0 hits.
Repo-wide scan: 0 credential patterns; single `POSTGRES_PASSWORD=`
string is the `<STRONG_RANDOM_PASSWORD>` placeholder in
`docs/ops/PROD_ENV_TEMPLATE.md`. Suites already green in G2: authz
matrix (owner 404 posture), gateway scope boundaries, payload redaction,
replay user isolation, Lab no-arbitrary-code pins, migration-121 trigger
integrity. Incident doc inspected (above).

## G5 — performance: **PASS (parity)**

Same dev DB, both APIs booted side-by-side, 5 samples each,
`/api/recommendations?limit=50` warm: integration 66–87ms vs target
65–70ms (first integration hit 360ms = cold pool). Startup logs clean on
both. Preflight-on path previously measured (1.18s cold / 0.7s warm
Discover bulk, Wave 1B) — unchanged code. Board 7ms / replay 157ms cold /
delta 127ms cold / lab 0.5s (wave evidence; unchanged code).
Method noted: dev-machine, small-N — parity claim only, not precision.

## G6 — feature-off parity: **PASS WITH EXPLAINED BASELINE DIFFERENCES**

Canonical env: all 12 server flags off + `MARKET_TAPE_ENABLED=false`,
dummy/off `VITE_*`.

- **Route diff** (normalized `METHOD path` sets, integration 354 vs
  target 336): 18 additions, ALL inherited always-on post-ledger work —
  accounts M1 (`/api/signup|login|logout|session|profile`,
  `/api/feedback/signal`), model portfolios (…`/model-portfolios*`),
  admin console (`/api/admin/{overview,jobs,system,feedback,
  trust-center}` — owner-404-guarded), `/api/paper/
  closed-recommendations`. **Zero flag-gated Elite routes** (no
  `/admin/inbox*`, `/admin/experiments*`, `/agent*`, `/theses*`,
  `/admin/lessons*`, delta/timeline routes). Nothing only-in-target.
- **Scheduler registry diff**: +`refresh_company_names` (inherited
  always-on era, migration 103) and +`evaluate_system_posture` —
  registry entry only: the handler no-ops when `SYSTEM_POSTURE_ENABLED`
  is off and **no migration inserts its schedule row** (runbook-gated).
  No label job, no Lab job, no inbox auto-execution; lease path is
  legacy while its flag is off (pinned by test).
- **Write invariance** (dev DB): row counts for
  thesis/research_task/research_report/lesson/agent_token/agent_job/
  recommendation_preflight/system_posture_event/execution_lease/
  research_run snapshotted before and after an always-on smoke
  (health/recommendations/canonical paper/model-portfolios/session):
  **diff empty — zero Elite writes**.
- **Recommendation parity** (same dev DB, target vs integration,
  limit 50): identical (id, symbol, action, conviction) sets; two added
  response fields `name`, `sector` traced to always-on beginner-UX
  commits (`3b87add` company names, `9d4646f` sector chips) — inherited
  approved product work, not Elite-flag behavior. Preflight-off
  filtering identical.
- **Paper safety**: trio suites green (G2); user books excluded from
  every engine path; hotfix protections active independent of flags.

## G7 — new code on migration 109: **PASS**

Ephemeral postgres:16 pinned at `109_research_run` (never upgraded).
Integration API booted with all flags off: health 200,
`/api/recommendations` 200, `/api/session` 200 (anon), signup 200 +
authenticated session 200 (104–106 tables ≤ 109), canonical paper 200,
model-portfolios 200, closed-recommendations 200. Elite routes all 404.
Server log: **zero errors/tracebacks/missing-table failures**; and at
109 the Elite tables do not exist, so silent writes are impossible —
`research_run` remained at 0 rows after the smoke.

## Dev-only inventory (unchanged from the plan)

Migrations 110–121 in prod (Stage-B), all Elite flags, Experiment Lab,
LightGBM adapter (blocked on fold depth), migration 122, replay
campaign, plus dev-DB data (1,601 rebuilt `historical_label` rows, 7 lab
`research_run` evidence rows, posture/audit ledgers) — data never
travels with this merge.

## Rollback

- Integration branch pre-PR: delete branch (tags preserve both heads).
- Post-merge (future): `git revert -m 1 <merge-commit>` on
  `phase-1/ledger`; per-flag disable (Preflight+Posture coupled);
  leave additive schema in place (verified safe both directions in G1).
- Dev DB restore point: `.backups/devdb_full_20260714_pre3a1.dump`.

## Residual risks

1. `test_route_scan_no_trade_mutation_endpoints` pre-existing failure
   (source-branch collection-order) — fix in a follow-up commit.
2. Three environment-dependent paper/rebalance test failures exist on
   BOTH branches (paired-run proven) — green in containers per prior CI
   evidence; track separately.
3. Review breadth (56k lines) — use the ten review groups in the PR
   body.

## Recommendation

**INTEGRATION PR READY FOR REVIEW** — merge into `phase-1/ledger` only
after human review of the draft PR; keep every Elite flag off; Stage-B
production promotion remains a separate gated plan.
