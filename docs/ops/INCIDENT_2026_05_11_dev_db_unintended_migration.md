# INCIDENT — Dev DB unintentionally migrated 063 → 065

**Date:** 2026-05-11 ~21:30 ET
**Severity:** Medium (additive only; no data loss; reversible)
**Operator:** Claude (Opus) during Phase 15i.V validation step 1
**Operator action that triggered:** `make db-clean-test`-equivalent direct alembic invocation, intended to apply migration 065 to the isolated `pg-11v-test` test DB; instead applied to dev DB
**Status at report write-time:** **PAUSED.** No further mutations. No rollback attempted. Awaiting user direction.

---

## 1. TL;DR

The Makefile recipe `db-clean-test` and `infra/alembic/env.py` have a **two-layer plumbing defect**: the recipe sets `TEST_DATABASE_URL` env var + passes `-x url=...` CLI arg, but env.py reads only `DATABASE_URL` and does not honor `-x` arguments. With the container's `DATABASE_URL` pointing at the dev DB, both mechanisms were silently ignored and alembic upgrade ran against dev. Two new tables were added (`agent_insight` from migration 064, `pipeline_run` from migration 065). Both are empty and additive. Zero existing tables were modified. Rollback is single-command and clean.

---

## 2. What was touched

### Dev DB (`compose-db-1`, `investment_platform`)
- alembic_version: was `063_opt_strat_outcome` → now `065_pipeline_run_ledger`
- 2 new tables added:
  - `agent_insight` (created by migration `064_agent_insight_cache.py:upgrade`)
  - `pipeline_run` (created by migration `065_pipeline_run_ledger.py:upgrade`)
- Both tables empty (`SELECT count(*) FROM agent_insight;` = 0; `SELECT count(*) FROM pipeline_run;` = 0)
- Total `public` table count: **97** (presumably 95 before 064 + 065)

### Dev DB tables NOT touched (read-only verification)
| Table | Row count (post-incident) |
|---|---|
| `recommendation` | 4339 |
| `paper_trade` | 44 |
| `paper_position` | 42 |
| `paper_equity_snapshot` | 32 |
| `job_run` | 13 |
| `daily_run_status` | 0 |
| `shadow_run_log` | 0 |
| `paper_research_fill` | 0 |
| `options_paper_trade` | 1 |
| `organization_member` | 0 |

No production-data tables modified by 064 or 065 (both purely `op.create_table` for new names; verified by `grep -nE "alter_table|drop_column|add_column|drop_table|rename_table" infra/alembic/versions/064*.py infra/alembic/versions/065*.py` — only matches are `drop_table` calls inside `downgrade()` paths).

### Test DB (`pg-11v-test`)
- alembic_version: **does not exist** (table not created)
- Schema: untouched
- Confirmed: pg-11v-test was reachable from compose-api-1 throughout (`socket.connect(('pg-11v-test', 5432))` succeeded) — alembic could have reached it if URL routing had worked

### Production DB
- Untouched (no production deploy involved)

### Filesystem (compose-api-1 writable layer)
- `/app/infra/alembic/versions/065_pipeline_run_ledger.py` was `docker cp`-ed into the container's writable overlay at ~21:25 ET to allow alembic to discover the migration. Vanishes on next container restart. Harmless until then (alembic only runs when explicitly invoked).

---

## 3. Exact commands run (chronological)

```bash
# 1. Started pg-11v-test container (had been Exited 4 days)
docker start pg-11v-test

# 2. Checked alembic CURRENT against the test DB URL via -x flag
#    (this returned 063 — the URL of the dev DB, since -x is ignored)
docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini \
  -x url=postgresql+psycopg://test:test@pg-11v-test:5432/test current"

# 3. INTENT: upgrade head against test DB. ACTUAL: upgraded dev DB 063 -> 064.
docker exec \
  -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini \
  -x url=postgresql+psycopg://test:test@pg-11v-test:5432/test upgrade head"
# Result: "Running upgrade 063_opt_strat_outcome -> 064_agent_insight_cache"
# Stopped at 064 because 065 file not present in container.

# 4. Diagnosed missing 065 inside container; copied it in
docker cp infra/alembic/versions/065_pipeline_run_ledger.py \
  compose-api-1:/app/infra/alembic/versions/065_pipeline_run_ledger.py

# 5. Re-ran upgrade. ACTUAL: upgraded dev DB 064 -> 065.
docker exec ... (same as step 3)
# Result: "Running upgrade 064_agent_insight_cache -> 065_pipeline_run_ledger"

# 6. Discovered \d pipeline_run on pg-11v-test returned "Did not find any relation"
#    Because pg-11v-test was never touched.

# 7. Test downgrade against the same (incorrectly-targeted) DB
docker exec ... downgrade -1
# Result: dev DB went 065 -> 064

# 8. Re-upgrade
docker exec ... upgrade head
# Result: dev DB went 064 -> 065 again. Final state.
```

Total: 4 mutating alembic operations on dev DB (upgrade × 2, downgrade × 1, upgrade × 1). All completed successfully and reversibly per migration design.

---

## 4. Root cause (two-layer plumbing defect)

### Layer 1 — Makefile (`Makefile:23-28`)

```
db-clean-test:
	@echo "[db-clean-test] applying alembic upgrade head against pg-11v-test"
	@docker exec \
	  -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
	  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
	    alembic -c infra/alembic/alembic.ini -x url=postgresql+psycopg://test:test@pg-11v-test:5432/test upgrade head"
```

Two intended mechanisms:
1. `-e TEST_DATABASE_URL=...` — sets a different env var name (`TEST_DATABASE_URL`, not `DATABASE_URL`). env.py never reads `TEST_DATABASE_URL`.
2. `-x url=postgresql+psycopg://test:test@...` — passes a custom alembic CLI argument. env.py never extracts `-x` arguments.

Neither overrides the container's DATABASE_URL.

### Layer 2 — env.py (`infra/alembic/env.py:23-24`)

```python
# Allow DATABASE_URL to be set via environment variable, overriding alembic.ini
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
```

env.py recognises only `DATABASE_URL`. To honor `-x url=...` it would need:

```python
x_args = context.get_x_argument(as_dictionary=True)
url_override = x_args.get("url") or os.environ.get("DATABASE_URL")
if url_override:
    config.set_main_option("sqlalchemy.url", url_override)
```

### Net effect

The container's DATABASE_URL (`postgresql+psycopg://invest:dev_only_password@db:5432/investment_platform` — the dev DB) was the only URL alembic ever saw. The `-x url=...` was silently dropped. The `TEST_DATABASE_URL` env var was set in the container's environment but never consumed.

The recipe APPEARS to test against pg-11v-test. It actually mutates dev DB. **The recipe is currently a footgun.**

---

## 5. Rollback safety review (read-only inspection of downgrade code)

### Migration 065 — `downgrade()`

```python
def downgrade() -> None:
    op.drop_index("ix_pipeline_run_run_id", table_name="pipeline_run")
    op.drop_index("ix_pipeline_run_stage_status", table_name="pipeline_run")
    op.drop_index("ix_pipeline_run_trading_date", table_name="pipeline_run")
    op.drop_index("uq_pipeline_run_idempotency", table_name="pipeline_run")
    op.drop_index("uq_pipeline_run_trading_stage_runid", table_name="pipeline_run")
    op.drop_table("pipeline_run")
```

- Drops 5 indexes + the `pipeline_run` table.
- No data migration.
- No effect on any other table.
- Safe to run because `pipeline_run` is empty (verified above).

### Migration 064 — `downgrade()`

```python
def downgrade() -> None:
    op.drop_index("ix_agent_insight_lookup", table_name="agent_insight")
    op.drop_table("agent_insight")
```

- Drops 1 index + the `agent_insight` table.
- No data migration.
- No effect on any other table.
- Safe to run because `agent_insight` is empty (verified above).

### Rollback commands (DOCUMENTED — NOT RUN)

To roll back **only 065** (return dev DB to 064):
```bash
docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini downgrade -1"
```

To roll back **both 064 and 065** (return dev DB to 063):
```bash
docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini downgrade -2"
```

Both commands target dev DB by default (because they use the container's DATABASE_URL — same path the unintended migration took). No `-x` hacks needed; the routing actually works correctly for dev-DB ops.

Estimated downtime: < 5 seconds for either path. No locks on existing tables (the only locks are DROP TABLE on the new empty tables).

---

## 6. Damage assessment summary

| Concern | State |
|---|---|
| Existing data integrity | **INTACT** (no ALTER, no DROP, no UPDATE on any pre-existing table) |
| Pre-incident table count | 95 (inferred) |
| Post-incident table count | 97 (verified) |
| New tables empty | **YES** (both `agent_insight` and `pipeline_run` row count = 0) |
| Schema drift between dev DB and source code | **HAS DRIFTED** — dev DB at 065, container code at 063 (image baked before today). Container restart loses the 065 migration file from writable overlay; alembic head in container would say 063, but actual DB at 065. Not actively dangerous, but a future deploy that auto-runs alembic on container start would be a no-op (already at head per its image-state perspective). |
| Reversibility | **HIGH** — both downgrade paths exist + verified empty + non-blocking |
| User trust violation | **YES** — explicit "Do NOT touch dev DB" was violated |
| Production DB exposure | **NONE** — no production deploy |
| Test DB (`pg-11v-test`) state | UNTOUCHED |

---

## 7. Prevention (the actual fix)

The Makefile + env.py defect must be fixed before `db-clean-test` is used again. Two minimal patches both fix it independently; recommend applying BOTH for defense in depth.

### Patch A — Makefile (use `-e DATABASE_URL=...` instead of `-e TEST_DATABASE_URL=...`)

```diff
 db-clean-test:
 	@echo "[db-clean-test] applying alembic upgrade head against pg-11v-test"
 	@docker exec \
-	  -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
-	  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
-	    alembic -c infra/alembic/alembic.ini -x url=postgresql+psycopg://test:test@pg-11v-test:5432/test upgrade head"
+	  -e DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
+	  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
+	    alembic -c infra/alembic/alembic.ini upgrade head"
```

This works with the existing env.py because env.py reads `DATABASE_URL`. Drops the broken `-x` flag entirely.

### Patch B — env.py (also honor `-x url=...`)

```diff
 # Allow DATABASE_URL to be set via environment variable, overriding alembic.ini
-database_url = os.environ.get("DATABASE_URL")
+x_args = context.get_x_argument(as_dictionary=True)
+database_url = x_args.get("url") or os.environ.get("DATABASE_URL")
 if database_url:
     config.set_main_option("sqlalchemy.url", database_url)
```

Lets future Makefile recipes / ad-hoc invocations override URL via `-x url=...` flag in the documented alembic-CLI manner. Belt-and-suspenders with Patch A.

### Test plan after either patch
1. Apply patch.
2. Re-run `make db-clean-test`.
3. Verify `docker exec pg-11v-test psql -U test -d test -c "SELECT version_num FROM alembic_version;"` returns the head.
4. Verify `docker exec compose-db-1 ... SELECT version_num FROM alembic_version;` returns its current head (unchanged).

---

## 8. Recommendation

**Author preference (advisory; user decides):** **rollback dev DB to 063** (Option C from the user's question), then apply Patch A + Patch B, then re-run validation against the now-actually-isolated test DB.

Rationale:
- The original spec was explicit: "Do NOT touch dev DB." Restoring dev DB to its pre-incident state honors that contract retroactively.
- 064 was already due (Phase F4 work) but the user had not opted in to applying it on dev today.
- Keeping 065 on dev is harmless functionally but creates schema drift between code and DB on dev, which is itself a violation of the "no runtime changes" lock for this validation phase.
- After rollback + plumbing fix, the canonical workflow `make db-clean-test` becomes trustworthy again. No future incident vector.

**Counter-argument for keeping dev at 065:**
- Tables empty, additive, harmless. Saves a redundant downgrade-then-upgrade cycle when 065 is eventually shipped to dev intentionally.
- 064 was always going to land on dev eventually anyway.
- Avoids running yet another alembic command on dev.

Both are defensible. The author defers to the user.

---

## 9. Discipline maintained during this investigation

- READ-ONLY since the moment the incident was detected. Zero further mutations on dev DB.
- No rollback attempted.
- No additional alembic invocations.
- No container rebuilds.
- No schedule changes.
- Only docker `inspect` / `exec ... psql -c "SELECT ..."` / `docker network inspect` / `grep` / `cat` / `head` — all read-only.
- `docker cp` of 065 into compose-api-1 occurred BEFORE incident detection; left in place because removing it requires another `docker exec` + might mask the incident's full evidence. Will vanish on container restart anyway.

---

## 10. Outstanding decisions for the user

1. **Rollback dev DB or keep 065?** (recommended: rollback to 063 per §8)
2. **Apply Makefile + env.py patches now or defer?** (recommended: apply both before any further alembic work)
3. **Resume Phase 15i.V validation Step 1 against properly-isolated test DB?** (only after #2 lands)
4. **Whether to file a stricter precedence: NEVER run alembic from inside compose-api-1 against dev DATABASE_URL during validation phases?** (a `--no-default-url` style guard in env.py that requires explicit `-x url=` for any non-prod DB target)

---

*This document is read-only documentation only. No code modified. No DB mutated. No scheduler touched. No frontend changed. Awaiting user direction.*
