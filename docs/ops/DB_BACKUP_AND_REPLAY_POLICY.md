# DB backup + replay policy — Phase 11Z hardening

**Status:** mandatory operational rule. Two destructive incidents
(2026-05-01 + 2026-05-02) wiped `compose_pgdata`. After a partial
recovery via `replay_paper_history` and a full
execution-chain rebuild via `replay_paper_execution_chain`, this
document is the durable policy preventing a third recurrence.

Companion docs:
- `docs/ops/DB_VOLUME_SAFETY.md` — what NEVER to run
- `docs/ops/PAPER_REPLAY_2026_05_02.md` — incident #2 timeline

---

## Hard rules

1. **Before any migration or deploy verification, run `make db-backup`.**
   Use `make verify-deploy-safe` instead of `make verify-deploy` —
   it refuses to run when the newest backup is >24 h old.

2. **Migration tests use `pg-11v-test` only.** Never apply unverified
   migrations against `compose_pgdata`. Use `make db-clean-test`.

3. **`compose_pgdata` is never wiped for verification.** All
   destructive volume operations are gated behind
   `scripts/safe_compose_down.sh` (env confirmation +
   `--force-dev-wipe`).

4. **Replay-generated data must be tagged.** Any script that fills
   gap rows after a wipe MUST insert into
   `replay_recovery_manifest` with `source='replay'` (or `'test'`)
   and a unique `replay_run_id`. Live-only API queries must filter
   replay rows out unless `include_replay=true` is explicit.

5. **ML datasets must include source/provenance.** The
   `paper_observation_label` + dataset-build pipeline emit
   `source` and `replay_run_id` columns. Models trained on replay
   rows must mark themselves replay-tainted in their model card.

6. **Production paper-trading totals must be filterable** to live-only
   for the WebUI Mock Portfolio page so users do not confuse
   recovery rows with active paper trades.

---

## Approved commands

| Goal | Command |
|---|---|
| Stop services, keep data | `make down` |
| Backup dev DB now | `make db-backup` |
| Preview newest backup | `make db-restore-preview` |
| Apply migrations to dev DB | `docker exec compose-api-1 sh -c "cd /app && PYTHONPATH=/app alembic -c infra/alembic/alembic.ini upgrade head"` |
| Apply migrations to test DB | `make db-clean-test` |
| Run integration regression | `make verify-deploy-safe` |
| Wipe dev DB (intentional) | `REQUIRE_VOLUME_DELETE_CONFIRMATION=I_UNDERSTAND_THIS_DELETES_DATABASE bash scripts/safe_compose_down.sh -v --force-dev-wipe` |
| Replay paper-trading history (selector path) | `PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY python -m scripts.replay_paper_history --start-date YYYY-MM-DD --end-date YYYY-MM-DD --commit` |
| Replay paper execution chain (account path) | `PAPER_EXEC_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_EXECUTION_HISTORY python -m scripts.replay_paper_execution_chain --start-date YYYY-MM-DD --end-date YYYY-MM-DD --account-name "<name>" --initial-cash <usd> --commit` |
| Build ML dataset (excludes replay by default) | `python -m scripts.build_ml_dataset --start-date YYYY-MM-DD --end-date YYYY-MM-DD --train-end YYYY-MM-DD --eval-start YYYY-MM-DD --out artifacts/ml/dataset.jsonl` |
| Build ML dataset audit (include replay) | as above plus `--include-replay` |

---

## Backup script behavior

`scripts/backup_dev_db.sh`:
- Creates `${BACKUP_DIR:-.backups}/devdb_<mode>_<TS>.sql`
- Modes: full (default), `--data-only`, `--schema-only`
- Refuses to overwrite an existing file
- Prints row counts for the high-value tables before dump
- Retains newest `${BACKUP_KEEP:-10}` files; never deletes the newest
- Read-only — never runs `docker compose down -v`, never touches
  `compose_pgdata`

Recommended cadence for a developer working with paper-trading data:
- Before running any `alembic upgrade` on dev: `make db-backup`
- Before running `make verify-deploy-safe`: `make db-backup`
- Daily, if you have unrecoverable rows you care about

---

## Replay tagging contract

Migration `061_replay_recovery_manifest` adds the table:

```
replay_recovery_manifest (
  id, created_at, replay_run_id, replay_generated_at,
  entity_type, entity_id,
  source CHECK IN ('live','dev','replay','test'),
  notes,
  UNIQUE (entity_type, entity_id)
)
```

Allowed `entity_type` values are pinned by CHECK constraint:
`account, paper_portfolio, paper_trade, paper_position,
recommendation, recommendation_evidence, paper_equity_snapshot`.

Any future replay tool MUST tag every row it creates. The helper at
`apps/api/src/provenance/manifest.py` provides:

- `is_replay_entity(session, entity_type, entity_id) -> bool`
- `list_replay_ids(session, entity_type) -> set[str]`
- `replay_exclusion_clause(entity_type, alias) -> str` (NOT EXISTS
  fragment for SQL composition)
- `ProvenanceFilter(include_replay)` for endpoint args

Live API endpoints that should default to `include_replay=False`:
- `/paper/summary`
- `/paper/trades`
- `/paper/equity`
- Anything that drives the Mock Portfolio + Overview pages

Audit endpoints that should default to `include_replay=True`:
- Internal health/diagnostic dashboards
- Replay-management tooling

---

## ML dataset rules

`scripts/build_ml_dataset.py`:
- Refuses to run if `ML_CAN_AFFECT_TRADES=true` (tripwire — this
  script is advisory-only, but a bad env should not slip past).
- Default excludes `source='replay'` rows; pass `--include-replay`
  to opt in (audit only).
- Marks open positions as `outcome_status='open_pending'`. Never
  fabricates a label.
- Train/eval split by `fill_date`; refuses if `train_end >=
  eval_start` (no leakage allowed).
- Emits per-row: `trade_id, symbol, side, quantity, fill_price,
  notional_usd, fill_ts, return_*, outcome_class, outcome_status,
  source, replay_run_id, split`.

ML promotion governance (`ML_PROMOTION_*` env vars in compose) is
unchanged; ML_CAN_AFFECT_TRADES default remains `false`.

---

## CI guard

The build refuses to land any source file that introduces
`docker compose down -v` outside `scripts/safe_compose_down.sh` or
the documentation files. See
`apps/api/tests/unit/test_db_volume_safety_guard.py`.

Additional Phase 11Z hardening tests (this commit):
- `test_backup_dev_db.sh` — backup script creates timestamped file,
  refuses overwrite, no `down -v` token in source
- `test_build_ml_dataset.py` — provenance + leakage + ML safety
- `test_provenance_manifest.py` — exclusion clause builder, replay
  ID listing, manifest table presence

---

## Incident history

| Date | Cause | Lost | Recovery |
|---|---|---|---|
| 2026-05-01 | pytest with dev `TEST_DATABASE_URL` → `Base.metadata.drop_all` | paper_position(29), candidate_idea history, regime, factor, asset, price_bar | re-seed + re-fetch |
| 2026-05-02 | `docker volume rm compose_pgdata` during deploy verification | paper_trade(5), paper_run_log(6), decision_log(16), paper_shadow_log(660), paper_trade_log(301) | partial: replay tools + manifest tagging |

Both incidents driven by treating the dev DB volume as expendable.
This document + `safe_compose_down.sh` + `verify-deploy-safe` +
`replay_recovery_manifest` exist so the next attempt fails closed.
