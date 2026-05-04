# Pending Next-Bar Fills (read-only visibility)

Companion to the existing next-bar fill guard in
`apps/api/src/domain/paper_trading/paper_execution.py`. Surfaces
paper-trade decisions that are **valid but waiting** for the next
trading-day `price_bar` so an operator can confirm the system is
healthy and trades will fill organically.

**No new execution behavior. No same-bar fills. No DB schema change.
Pure read of the existing skip JSONL.**

---

## Why this exists

`run_paper_trading` writes per-day skip detail to
`artifacts/paper_trading_skips/<as_of>.jsonl`. When the auto-trader
generates a buy decision but cannot find a `price_bar` whose
`ts > submitted_at`, the row lands with:

```json
{
  "as_of_date": "...",
  "portfolio_id": "...",
  "asset_id": "...",
  "reason": "execution_failure",
  "detail": {"exec_reason":
             "no price bar available after submitted_at; cannot fill"}
}
```

That is **NOT a failure** — it is the next-bar guard correctly
refusing a same-bar fill. Trades land naturally on the following
weekday once `ingest_prices_daily` writes the next bar.

---

## Operator flow (Phase 1 — Option A validation)

When the next trading day's data is available, run, in order:

```bash
DATABASE_URL=postgresql+psycopg://invest:dev_only_password@localhost:54329/investment_platform \
  .venv/Scripts/python.exe -c "
import asyncio, datetime as dt
from apps.worker.src.jobs.ingest_prices_daily      import ingest_prices_daily
from apps.worker.src.jobs.compute_factor_snapshots import compute_factor_snapshots
from apps.worker.src.jobs.compute_regime_snapshot  import compute_regime_snapshot

async def go():
    target = dt.date(YYYY, M, D)        # the next trading day
    await ingest_prices_daily()         # full active universe
    await compute_factor_snapshots(as_of=target)
    await compute_regime_snapshot(as_of=target)

asyncio.run(go())
"

# Then re-run the safe one-shot.
DATABASE_URL=... .venv/Scripts/python.exe -m scripts.run_paper_daily_safe
```

After this, pending decisions from the prior `as_of` whose
`submitted_at` is now older than the freshly ingested bar will fill
through the standard auto-trader path. The fill timestamp comes from
the next bar's `ts`. **The same-bar guard remains in force** —
`paper_execution.find_next_open(...)` only matches bars strictly
later than `submitted_at`.

---

## Pending-fill API

`GET /api/performance/paper/pending-fills?as_of=YYYY-MM-DD`

| Field | Source |
| --- | --- |
| `as_of_date` | latest skip JSONL date when the query parameter is omitted |
| `next_expected_bar_date` | next weekday after `as_of_date` (no holiday calendar) |
| `count` | number of pending-fill rows |
| `items[].symbol` | `asset.symbol` joined on `asset_id` |
| `items[].asset_id` | from JSONL |
| `items[].action` | constant `"Buy"` (only buy decisions hit this guard) |
| `items[].submitted_at` | derived as `as_of_date 21:00 UTC` (US-close anchor used elsewhere; JSONL does not capture submitted_at directly) |
| `items[].as_of_date` | from JSONL |
| `items[].portfolio_id` / `portfolio_name` | from JSONL + DB join |
| `items[].expected_fill_rule` | constant `"next_bar"` |
| `items[].current_status` | constant `"pending_next_bar"` |
| `items[].reason` | constant `"waiting for price_bar after submitted_at"` |
| `items[].latest_price_bar_ts` | `max(price_bar.ts) WHERE asset_id = …` |
| `items[].next_expected_bar_date` | next weekday |
| `items[].raw_exec_reason` | underlying `detail.exec_reason` from JSONL |
| `notice` | "Pending next-bar fills. NOT executed trades. …" |

Filter logic (pinned in tests):
```python
row.get("reason") == "execution_failure"
and "no price bar available after submitted_at"
    in (row.get("detail") or {}).get("exec_reason", "").lower()
```

GET-only. No DB writes. No JSONL writes. No mutation, no model code,
no replay-row coupling.

---

## Discord formatter (pure helper, no auto-send)

`apps/api/src/api/performance_paper.py::format_pending_fill_discord`

```
🟡 Paper Trade Pending Fill
Symbol: AAPL
Action: Buy
Portfolio: <portfolio_id>
Submitted: 2026-05-04T21:00:00+00:00
Fill Rule: Next available price bar
Status: Waiting for next bar
Latest Bar: 2026-05-04T00:00:00+00:00
Expected Fill Window: 2026-05-05

No trade has been filled yet. This is pending next-bar execution.
```

Tests reject any token that could imply success (`Filled`, `Executed`,
`PnL`, `$`, `Profit`, `Loss`, `Success`, `Confirmed`). The formatter
returns a string; sending is the caller's responsibility — there is
no auto-dispatch path.

---

## Phase 5 — validation results

### Option A validation (today's run)

| Check | Value |
| --- | --- |
| Next trading-day price_bar exists | **no** (today is the latest bar) |
| Pending decisions detected | 2 (1 in each portfolio, both for asset MO) |
| Eligible next-bar fills found | 0 (next bar not yet ingested) |
| Paper trades inserted | 0 |
| Same-bar fills prevented | **yes** — `find_next_open()` returned None for both decisions; `PaperTradeRejected("no price bar available after submitted_at; cannot fill")` raised in `paper_execution.py:199` |

### Pending visibility

| Check | Value |
| --- | --- |
| Endpoint reachable | yes (`GET /api/performance/paper/pending-fills` 200) |
| Pending count | 2 |
| Sample row | `{symbol: "MO", action: "Buy", current_status: "pending_next_bar", expected_fill_rule: "next_bar", latest_price_bar_ts: "2026-05-04T00:00:00+00:00", next_expected_bar_date: "2026-05-05"}` |
| Discord formatter | renders correctly; tests pin title, footer, and forbidden-success vocabulary |

### Hard safety checks

| Check | Result |
| --- | --- |
| Replay rows touched | **no** — `paper_trade=18` (replay-tagged), `paper_position=18`, `replay_recovery_manifest=109` unchanged |
| ML behavior changed | **no** — `ML_CAN_AFFECT_TRADES=false`; ml_insights endpoints untouched |
| Options live execution touched | **no** — `options_paper_trade=0` |
| Strategy thresholds changed | **no** — `TOP_N=10`, `HIGH_VOL_TOP_N=3`, `MAX_POSITION_PCT=0.07`, `DEFAULT_MAX_OPEN_POSITIONS=10` unchanged |
| DB schema changed | **no** — pending-fill source is the existing JSONL artifact + read-only joins to `asset`, `paper_portfolio`, `price_bar` |
| Same-bar fills allowed | **no** — guard preserved; tests pin filter constants |
| New POST endpoints | **no** — `GET /pending-fills` only |

---

## Tests added

`apps/api/tests/unit/test_pending_fills.py` — **14 tests**, all
passing in 133s. Covers route pin, GET-only, write-statement reject,
status vocabulary pin, filter constants, JSONL read filter logic,
Discord formatter title/footer/forbidden-success vocabulary, weekday
math for `next_expected_bar_date`, bad-input handling.

---

## Rollback

- Delete `apps/api/tests/unit/test_pending_fills.py`.
- Remove the `/pending-fills` function and `format_pending_fill_discord`
  helper from `apps/api/src/api/performance_paper.py` (everything
  below the `# /performance/paper/pending-fills` divider).

No DB schema, scheduler entry, or notification path was added; rollback
is purely code deletion.
