# Options Canary Lifecycle Replay Harness

`test_options_canary_lifecycle_replay_pg.py` + `_canary_replay.py`

## What it proves

Deterministic proof of every options-canary lifecycle transition for the
QQQ `SHORT_PUT_CREDIT_SPREAD` shape — **without waiting for daily market
data** and **without touching the production ledger or the live canary
(trade 3)**. Scenarios:

| Test | Proves |
|------|--------|
| `test_hold_far_dte_low_capture` | DTE > 7 & captured < 50% → stays OPEN, MTM event, reconcile clean |
| `test_take_profit_close` | captured ≥ 50% → closes, reserve + realized credited, reconcile clean |
| `test_dte_management_close` | DTE ≤ 7 → closes, reserve released, realized recorded, clean |
| `test_expiry_settlement` | DTE ≤ 0 → expiry settlement, released, realized, clean |
| `test_stale_unpriced_hold` / `_null_mid_hold` | missing / null mid → HOLD, not closed, clean |
| `test_adverse_near_max_loss_holds` | close-cost ≈ width → HOLD (defined risk, no hard stop) |
| `test_safety_guards` | the four isolation guards below |

It reuses the **real** engine — `promote_one` → `run_lifecycle_cycle`
(`manage_one` MTM + `decide_exit` + `release_one`) → `reconcile.run` — and the
real thresholds (`settings.OPTIONS_CANARY_TP_PCT` = 0.50, `OPTIONS_CANARY_DTE_CLOSE`
= 7). No lifecycle math or thresholds are duplicated. Each scenario is driven
purely by the seeded `options_chain_snapshot` mids / expiry that `manage_one`
marks against.

## Isolation — never touches production

- Runs against an **ephemeral Postgres testcontainer**, schema built by
  `alembic upgrade head` (the canary tables are alembic-only, not ORM).
- The container URL is injected to Alembic via `-x url=...` and to SQLAlchemy
  directly, so `DATABASE_URL` is **never** consulted.
- Four asserted guards (`test_safety_guards`): engine host is
  `localhost`/`127.0.0.1` on a container-assigned (non-5432) port; the
  container URL ≠ `DATABASE_URL`; the portfolio name starts `replay-sim-`;
  the portfolio is never `canary-spy-v1`.
- The container is disposed at teardown. The production DB, `canary-spy-v1`,
  and trade 3 are never opened.

## How to run

Requires Docker (for testcontainers):

```bash
uv run pytest apps/api/tests/integration/test_options_canary_lifecycle_replay_pg.py -v -m integration
```

Without Docker the integration fixtures **skip intentionally** (they do not
error) — see the `pg_url` fixture in `conftest.py`.

## CI

`pytest -q` (CI `backend.yml`) does not exclude the `integration` marker, so
these run on Docker-equipped runners and skip gracefully elsewhere.

## A real-behavior note

`decide_exit`'s `priced` flag means "a mid is present for every leg" — quote
**age** / staleness is enforced at the fill gate, not in `decide_exit`. So the
unpriced-HOLD path is exercised via missing / null mids, which is the real path
to `HOLD_STALE`.
