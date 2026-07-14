# Elite ArthOS — Staged Production Promotion Plan (PREPARED, NOT EXECUTED)

Production state: release `1fb6e28` (Stage B1 ingest-contract code), migration
**109**, `INGEST_CONTRACTS_ENABLED` unset, Trust Center not deployed, disk ~84%.
**This plan is not authorized to run.** Each stage is independently
releasable; the full Elite branch is **never** shipped in one release.

Global rules for every stage: `make db-backup` (off-VM copy) → apply migration
in exact order → deploy code → keep flag OFF → canary read-only → observe →
only then flip flag (if any). Hard stop on any failed evidence gate. Never
force-push; never skip a migration number.

---

## Stage B2 — complete ingest-contract enablement
- **Isolation:** `release/stage-b1-ingest-contracts` (existing) → cut
  `release/stage-b2` tag. No Elite branch code.
- **Migration:** none (109 already prod). **Backup:** yes (pre-flag).
- **Canary:** enable `INGEST_CONTRACTS_ENABLED=True` for ONE symbol ingest,
  read-only comparison against the un-contracted path.
- **Evidence:** contract-validated ingest matches baseline row-for-row; no
  rejected-symbol regression; report boundedness pins green.
- **Monitoring:** ingest job success rate, contract-violation counter, freshness.
- **Rollback:** unset flag (code path dormant). **Disk:** negligible.
- **Hard stop:** any contract false-positive on a real symbol. **Observe:** 48h.

## Stage 2 — Trust Center owner route
- **Isolation:** cherry-pick the Trust Center route commit onto a release tag;
  owner-only (`require_owner`, 404 posture).
- **Migration:** none. **Backup:** yes. **Canary:** owner loads `/admin/trust-center`
  on prod; read-only feeds only.
- **Evidence:** page renders real read-only data; anonymous → 404; no engine
  vocabulary leak. **Monitoring:** admin route error rate.
- **Rollback:** remove route (no schema). **Disk:** none. **Observe:** 24h.

## Stage 3 — "Meets the buy bar" copy
- **Isolation:** web-only release; no API/migration.
- **Migration:** none. **Backup:** n/a (static). **Canary:** owner visual check
  desktop+mobile. **Evidence:** copy matches the recorded owner decision (High/
  Medium → "Meets the buy bar"); no confidence-number change.
- **Rollback:** revert web bundle. **Disk:** none. **Observe:** 24h.

## Stage 4 — migrations 110/111 + Thesis Ledger
- **Isolation:** `release/thesis-ledger` from Elite, containing ONLY 110/111 +
  thesis files + `THESIS_LEDGER_ENABLED`.
- **Migration:** 110 → 111 (after 109). **Backup:** mandatory + off-VM.
- **Canary:** apply migrations, keep flag OFF (routes 404), verify tables/CHECKs;
  then flip flag for owner-only, create one thesis + catalyst/risk via console.
- **Evidence:** ephemeral up/down clean (already proven); prod tables match dev
  schema; public read shape carries no engine vocabulary; forming theses never
  serialized. **Monitoring:** thesis route errors, DB size delta.
- **Rollback:** flag off → 404; `downgrade 109` drops tables (additive).
- **Disk:** small (empty tables). **Hard stop:** any FK/CHECK mismatch vs dev.
  **Observe:** 72h before public read exposure.

## Stage 5 — migration 115 + paper-cost audit
- **Isolation:** `release/paper-cost` — ONLY 115 + cost files +
  `PAPER_COST_MODEL_ENABLED`.
- **Migration:** 115 (requires 114 first if gateway not yet shipped — see
  ordering note). **Backup:** mandatory. **Canary:** apply column, keep cost
  model OFF (all NULL, legacy fills byte-identical), run `paper-daily-dry`.
- **Evidence:** existing rows unchanged (md5), NULL stamps; then enable on the
  canonical practice book only, verify exact cash==net_notional reconciliation
  on the next fill. **Monitoring:** paper cash drift, stamp completeness.
- **Rollback:** flag off → NULL; downgrade drops column (clone-proven safe).
- **Disk:** small. **Observe:** one full daily cycle.
- **Ordering note:** 115 depends on 114 in the linear chain. If gateway (114)
  is not yet in prod, Stage 5 must carry 114 as a **no-op schema-only** apply
  (tables stay empty, gateway flag OFF) OR be sequenced after Stage 7. Prefer
  the latter to keep each stage's migration set minimal.

## Stage 6 — migrations 112/113 + Inbox/Learning
- **Isolation:** `release/inbox-learning` — 112/113 + inbox/learning files +
  `RESEARCH_INBOX_ENABLED`, `LEARNING_LOOP_ENABLED` (independent flags).
- **Migration:** 112 → 113. **Backup:** mandatory. **Canary:** apply, flags OFF
  (404), then owner-only: create task→report (forced pending), propose lesson
  (forced draft, hindsight guard). **Evidence:** ephemeral up/down clean; forced
  pending/draft proven; approve carries reviewer identity; approving a lesson
  never mutates thesis status. **Monitoring:** inbox/lesson route errors.
- **Rollback:** flags off; downgrade drops tables. **Disk:** small.
  **Observe:** 72h.

## Stage 7 — migrations 114/116/117 + Agent Gateway
- **Isolation:** `release/agent-gateway` — 114/116/117 + gateway files +
  `AGENT_GATEWAY_ENABLED`. **Highest-risk stage; ship last.**
- **Migration:** 114 → 116 → 117 (117 needs 112's research_report in prod →
  Stage 6 must precede Stage 7). **Backup:** mandatory + off-VM.
- **PRECONDITIONS (hard gates, all required before flag flip):**
  1. **Rate limiter moved to a shared store** — the single-replica in-memory
     limiter is a promotion blocker (SEC ACCEPTED-RISK). No enable without it,
     unless prod is provably single-replica AND that is documented as permanent.
  2. Named-user beta NOT enabled (owner-only); disabled-user gate present (done).
  3. 30 days of clean dev audit history.
  4. Fresh security sign-off against `ELITE_ARTHOS_SECURITY_REVIEW.md`.
- **Canary:** apply migrations, flag OFF (all `/agent/*` + console 404). Then
  owner mints ONE token via console, runs whoami + one read + one offline job
  (dev-lane runner NOT scheduled in prod — jobs stay queued unless a manual
  operator runs them) + one draft (lands pending). **Evidence:** authz matrix
  green on prod; audit rows bounded + secret-free; SSE bounds hold.
- **Monitoring:** per-token audit panel, error-rate, rate-limit hits, DB size.
- **Rollback:** flag off → entire surface + console vanish; revoke-all-tokens =
  one UPDATE; downgrade 117→116→114 drops tables (additive, clone-proven).
- **Disk:** small (empty tables) + audit growth (180-day retention, then
  archived). **Hard stop:** any authz-matrix failure or audit gap on prod.
  **Observe:** 30 days owner-only before considering named-user beta.

---

## Cross-cutting
- **Disk:** prod ~84% — Stage 4–7 add near-empty tables; audit growth is the
  only ongoing consumer (bounded by retention). Run the targeted cleanup +
  confirm <85% before Stage 7.
- **Migration ordering constraint:** the chain is strictly linear 109→117.
  Any stage applying a higher migration implicitly requires all lower ones.
  The minimal-set staging above sequences 4(110/111) → 6(112/113) → 5(115) →
  7(114/116/117) so dependencies hold; if disk/priority forces a different
  order, re-derive the dependency set — never skip.
- **No stage ships the whole branch.** Each is its own release tag, backup,
  canary, and observation window.
