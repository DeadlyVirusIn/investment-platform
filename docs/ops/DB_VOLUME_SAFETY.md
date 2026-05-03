# DB volume safety — Phase 11Z incident response

**Status:** mandatory operational rule. Two destructive incidents
have happened against `compose_pgdata` (2026-05-01 + 2026-05-02).
This document plus the safe-compose-down wrapper exist to make a
third recurrence structurally impossible.

---

## The protected volume

```
volume name: compose_pgdata
mounted at:  /var/lib/postgresql/data inside compose-db-1
contents:    dev-environment working data (assets, price_bar,
             paper_trade, decision_log, paper_run_log,
             paper_shadow_log, paper_trade_log, candidate_idea
             history, research_ro tables, ...)
```

This volume is **stateful working data**. Some rows in it are
**not recoverable from any external source**:

| Table | Source after wipe |
|---|---|
| asset, universe_membership | re-seedable from `seed_universe_membership.py` |
| price_bar | re-fetchable from Tiingo |
| context_daily, features_daily | re-fetchable from FRED |
| regime_snapshot, factor_snapshot | recomputable from price_bar |
| candidate_idea (current) | regenerable for current dates only |
| **paper_trade** | **NOT recoverable** — local-only history |
| **paper_run_log** | **NOT recoverable** |
| **decision_log** | **NOT recoverable** |
| **paper_shadow_log** | **NOT recoverable** |
| **paper_trade_log** | **NOT recoverable** |
| **candidate_idea (historical)** | recomputable only when full upstream is restored |

Anything in the bottom block is permanently lost on a `compose_pgdata`
wipe.

---

## The rules

1. **`docker compose down -v` is forbidden against the dev compose
   stack.** The `-v` flag deletes the volume.

2. **`docker volume rm compose_pgdata` is forbidden.** Same effect.

3. **Migration verification MUST use an isolated test database.**
   The project ships `pg-11v-test` (postgres:17-alpine, db=`test`,
   user=`test`, port `55432`). Use that.

4. **Integration tests MUST point `TEST_DATABASE_URL` at the
   test DB.** Phase 11Z installed a Python-side guard
   (`apps/api/tests/integration/conftest.py:_assert_test_database_url`)
   that refuses to run pytest against any URL whose host is `db`/
   `compose-db-1` or whose database name doesn't contain `test`/
   `integration`. Do not bypass.

5. **Deploy-readiness verification MUST NOT wipe `compose_pgdata`.**
   Use `make verify-deploy` (which calls `make db-clean-test` for
   the alembic step against `pg-11v-test`).

---

## Approved commands

| Goal | Command |
|---|---|
| Stop services, keep data | `make down` |
| Apply migrations to dev DB | `docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app alembic -c infra/alembic/alembic.ini upgrade head"` |
| Apply migrations to test DB | `make db-clean-test` |
| Run integration regression | `make verify-deploy` |
| Wipe dev DB (intentional) | `REQUIRE_VOLUME_DELETE_CONFIRMATION=I_UNDERSTAND_THIS_DELETES_DATABASE bash scripts/safe_compose_down.sh -v --force-dev-wipe` |

The wipe wrapper:
- prints current row counts before deleting
- requires the literal env value `I_UNDERSTAND_THIS_DELETES_DATABASE`
- requires `--force-dev-wipe` argument
- enforces a 5-second cancel window after printing counts

---

## Recovery if the wipe still happens

1. Recover assets + universe:
   ```
   docker exec compose-api-1 sh -c "PYTHONPATH=/app python -m scripts.seed_universe_membership"
   docker exec compose-api-1 sh -c "PYTHONPATH=/app python -m scripts.seed_symbols"
   docker exec compose-db-1 psql -U invest -d investment_platform -c \
     "UPDATE universe_membership SET start_date='2024-01-01' WHERE universe_name='stock_swing_v1';"
   ```

2. Recover price_bar (Tiingo + Yahoo fallback):
   ```
   FRED=$(grep "^FRED_API_KEY" .env | cut -d= -f2)
   TIINGO=$(grep "^TIINGO_API_KEY" .env | cut -d= -f2)
   docker exec -e TIINGO_API_KEY=$TIINGO compose-api-1 \
     sh -c "PYTHONPATH=/app python -c '
import asyncio
from apps.worker.src.jobs.backfill_prices import backfill_prices
asyncio.run(backfill_prices(years=4))
'"
   ```

3. Recover macro context (FRED):
   ```
   docker exec -e FRED_API_KEY=$FRED compose-api-1 \
     sh -c "PYTHONPATH=/app python -m scripts.backfill_macro_features \
       --start 2026-04-22 --end 2026-05-01 --lookback-days 120 \
       --commit --confirm-commit YES"
   ```

4. Recompute regime + factor:
   ```
   docker exec compose-api-1 sh -c "PYTHONPATH=/app python -m scripts.backfill_regime --from 2026-01-01 --to 2026-05-01"
   docker exec compose-api-1 sh -c "PYTHONPATH=/app python -m scripts.backfill_factors --from 2026-04-22 --to 2026-05-01"
   ```

5. Re-generate candidate_idea (current dates only):
   ```
   docker exec compose-api-1 sh -c "PYTHONPATH=/app python -c '
import asyncio, datetime as dt
from apps.worker.src.jobs.generate_stock_candidates import generate_stock_candidates
async def main():
    for d in [dt.date(2026,4,22),...,dt.date(2026,5,1)]:
        await generate_stock_candidates(as_of=d)
asyncio.run(main())'"
   ```

6. **Do NOT fabricate** paper_trade / paper_run_log / decision_log /
   paper_shadow_log / paper_trade_log rows. Lost is lost.

---

## CI guard

The build refuses to land any source file that introduces
`docker compose down -v` outside `scripts/safe_compose_down.sh` or
this doc.

Test: `apps/api/tests/unit/test_db_volume_safety_guard.py`

```
grep -rn "docker compose down -v" \
  Makefile scripts docs apps/api apps/worker apps/web infra
```

Allowed locations: `scripts/safe_compose_down.sh`, this file
(`docs/ops/DB_VOLUME_SAFETY.md`), `docs/ops/`.

---

## Incident history

| Date | Cause | Lost |
|---|---|---|
| 2026-05-01 | pytest with `TEST_DATABASE_URL=...investment_platform` (dev DB) → `Base.metadata.drop_all` | paper_position (29 rows), candidate_idea history, regime_snapshot, factor_snapshot, asset, price_bar |
| 2026-05-02 | `docker volume rm compose_pgdata` during deploy-readiness verification | paper_trade (5), paper_run_log (6), decision_log (16), paper_shadow_log (660), paper_trade_log (301) |

Both incidents driven by the same engineer (me, Claude) and both
caused by treating the dev DB volume as expendable. Wrapper +
Makefile + CI guard land here so the next attempt fails closed.
