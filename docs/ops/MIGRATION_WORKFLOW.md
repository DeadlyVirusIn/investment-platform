# Migration Workflow (post Phase 15i.R hardening)

This document defines the canonical workflow for applying Alembic
migrations against each of the three database targets.

**Background:** prior to Phase 15i.R the Makefile recipe `db-clean-test`
silently mis-routed migrations from the test DB to the dev DB
(`docs/ops/INCIDENT_2026_05_11_dev_db_unintended_migration.md`).
The routing layer is now hardened with three independent guards.

---

## Database targets

| Target | Container | DSN | Read by env.py via |
|---|---|---|---|
| **dev** | `compose-db-1` | `postgresql+psycopg://invest:dev_only_password@db:5432/investment_platform` | container's default `DATABASE_URL` env var |
| **test** (isolated) | `pg-11v-test` | `postgresql+psycopg://test:test@pg-11v-test:5432/test` | `-e DATABASE_URL=...` override (Makefile) AND `-x url=...` (defense in depth) |
| **prod** | (cloud) | (see deploy secrets) | injected at deploy time; never set from a developer shell |

---

## URL resolution precedence (env.py)

1. **`-x url=...`** CLI arg (highest priority)
2. **`DATABASE_URL`** env var
3. **`alembic.ini`** placeholder (refuses to connect)

Every alembic invocation logs the resolved target to stderr:

```
[alembic] resolved target (DATABASE_URL env): postgresql+psycopg://test:***@pg-11v-test:5432/test
```

If the resolved target is wrong, the operator sees it BEFORE any DDL runs.

---

## Safety guard — `ALEMBIC_REQUIRE_TEST_TARGET=1`

When this env var is set, env.py refuses to run if the resolved
hostname matches a known dev/prod DB host (`db`, `compose-db-1`,
`investment_platform`). This is the second layer of defense; it
catches the case where the URL routing layer silently misfires
(the exact failure mode of the 2026-05-11 incident).

The Makefile `db-clean-test` target sets this var automatically.
For ad-hoc test-DB invocations, set it manually:

```bash
docker exec \
  -e DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  -e ALEMBIC_REQUIRE_TEST_TARGET=1 \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
    alembic -c infra/alembic/alembic.ini upgrade head"
```

---

## Workflows

### A. Test-DB migration (canonical)

Use the Makefile recipe. Three layers of routing safety + safety guard:

```bash
make db-clean-test
```

What this does:
- Sets `DATABASE_URL` to the test DB
- Sets `ALEMBIC_REQUIRE_TEST_TARGET=1` so env.py refuses to write to dev
- Passes `-x url=...` as a redundant URL-routing channel
- Runs `alembic upgrade head` inside `compose-api-1` against `pg-11v-test`

Verification after run:
```bash
docker exec pg-11v-test psql -U test -d test -c "SELECT version_num FROM alembic_version;"
```

### B. Dev-DB migration (deliberate)

Only when intentionally migrating dev. **Do NOT set
`ALEMBIC_REQUIRE_TEST_TARGET=1`** (the guard would refuse).

```bash
docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini upgrade head"
```

This uses the container's default `DATABASE_URL` which already
points at dev. env.py logs the resolved target before any DDL.

### C. Production migration (out of scope here)

Production migrations are coordinated through the deploy pipeline,
not run from a developer shell. See deploy runbook.

---

## Rollback workflows

### Test DB rollback by N revisions

```bash
docker exec \
  -e DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  -e ALEMBIC_REQUIRE_TEST_TARGET=1 \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
    alembic -c infra/alembic/alembic.ini downgrade -N"
```

### Dev DB rollback by N revisions

```bash
docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app \
  alembic -c infra/alembic/alembic.ini downgrade -N"
```

(Confirm rollback safety per migration's `downgrade()` body before running.)

---

## Common failure modes (and what env.py does)

| Symptom | Likely cause | env.py response |
|---|---|---|
| `RuntimeError: ALEMBIC_REQUIRE_TEST_TARGET=1 is set but ... resolved alembic target hostname '<host>' is a known dev/prod DB` | Test workflow somehow still routing to dev DB (env var override missing) | Refuses to run before any DDL |
| `RuntimeError: ALEMBIC_REQUIRE_TEST_TARGET=1 is set but no DATABASE_URL was resolved` | Test workflow without any URL source | Refuses to run before any DDL |
| Resolved target log line shows the wrong DB hostname | Mis-set env var or wrong `-x url=...` | Operator sees BEFORE running; can Ctrl+C |
| `alembic_version` does not exist on the expected DB | Alembic actually ran against a different DB | Now visible in the resolved-target log line; the safety guard would have caught dev/prod |

---

## Phase 15i.R verification checklist

After this hardening lands:
- [ ] `make db-clean-test` upgrades `pg-11v-test` to head
- [ ] `make db-clean-test` writes `alembic_version` table on pg-11v-test
- [ ] `make db-clean-test` does NOT touch `compose-db-1` (dev DB)
- [ ] `make db-clean-test` STDOUT/STDERR shows `[alembic] resolved target (...): ...@pg-11v-test:...`
- [ ] Deliberate misuse — running with `ALEMBIC_REQUIRE_TEST_TARGET=1` AND a dev DB URL — fails loudly with the safety guard error and zero DDL
- [ ] dev DB unchanged across all of the above

---

## Why three layers

Each layer alone fixes the original bug. All three together provide
defense in depth so a future regression in any one layer is caught
by the next:

1. **Routing — `-x url=...`** — Alembic's documented mechanism for
   DB-URL override.
2. **Routing — `-e DATABASE_URL=...`** — env.py's already-supported
   override; always works regardless of `-x` support.
3. **Guard — `ALEMBIC_REQUIRE_TEST_TARGET=1`** — refuses to run
   even if both routing layers somehow misfire.

Plus the always-on **resolved-target log line** so silent misroute
is no longer possible.

---

*Document originated: 2026-05-11 ~22:00 ET, immediately after the
incident response in Phase 15i.R. Update when DB targets, env var
names, or guards change.*
