# Unrealized PnL + Exit Tracking (read-only)

Extension of the personal-analytics phase. Surfaces open-position
unrealized P&L and diagnostic exit-tracking visibility while trades
are still open. **Read-only. No execution. No DB writes. No closing
of positions.**

---

## Goals

1. Show unrealized P&L per open position derived from the latest
   `price_bar` row, with explicit `unavailable` when no price exists.
2. Aggregate live + replay split unrealized stats so the operator
   sees `live=0 / replay=18` honestly when applicable.
3. Provide a diagnostic-only Exit Tracking panel — labels, freshness,
   and rule availability — without any action wording.

---

## Hard policy

| Rule | Enforcement |
| --- | --- |
| GET-only routers | `test_perf_router_get_only` rejects `@router.{post,put,patch,delete}`. |
| No DB writes | `test_perf_router_no_db_writes` regex-rejects `INSERT INTO / UPDATE … SET / DELETE FROM` outside docstrings. |
| No action verbs in exit tracking | `test_exit_tracking_has_no_action_language` greps the `exit_tracking` function body and rejects `"sell"`, `"close"`, `"exit now"`, `"take profit"`, `"stop loss"`, `"buy now"`, `"trade now"`, `"execute"`. |
| Exit-rule data is `null` until persisted | endpoint always returns `exit_rule_status="unavailable"` (rule persistence is a follow-up; this prevents fabricating output). |
| Replay rows never silently mixed | always-on live + replay buckets in `/unrealized`; per-row `is_replay` flag in `/open-positions` and `/exit-tracking`. |
| ML_CAN_AFFECT_TRADES stays false | static-grep tests reject `=true` literal in changed files. |
| No scheduler/worker entries | no edits to `apps/worker/src/scheduler/*` or `infra/docker/worker.crontab`. |

---

## Endpoints

### `GET /api/performance/paper/open-positions`

Returns per-open-position rows joined with the latest `price_bar`
when available.

Per-row contract (every row carries every key):

| Field | Notes |
| --- | --- |
| `position_id`, `portfolio_id`, `symbol`, `sector` | identity |
| `source`, `replay_run_id`, `is_replay` | provenance |
| `entry_date`, `fill_ts`, `entry_price`, `quantity`, `notional_at_entry_usd` | entry |
| `latest_price`, `latest_price_date` | from `price_bar`; `null` when missing |
| `unrealized_pnl_usd`, `unrealized_return_pct`, `unrealized_status` | `unavailable` when no price; never `0.0` as fallback |
| `days_open` | floats with 2-decimal precision |
| `outcome_status` | always `"open_pending"` here |
| `data_quality.{latest_price_available, stale_price, missing_price, stale_threshold_days}` | freshness |

### `GET /api/performance/paper/unrealized`

Aggregate stats with three buckets:

```
{
  headline: { ... },     # respects include_replay flag
  live:     { ... },     # always live-only
  replay:   { ... },     # always replay-only
  all_positions_are_replay: bool,
}
```

Each bucket carries `n_positions`, `n_with_price`, `n_unavailable`,
`total_unrealized_pnl_usd`, `avg_unrealized_return_pct`, and
`best`/`worst` references with symbol + amounts. When a bucket has
no priced rows, totals are `null` — never `0.0`.

### `GET /api/performance/paper/exit-tracking`

Diagnostic-only. Returns:

```
{
  vocabulary: ["Monitoring", "Open pending",
               "Price data current", "Price data stale",
               "Missing price", "Exit rule unavailable",
               "Recovered replay"],
  notice: "Diagnostic labels only. NO action recommendation, NO execution. ...",
  positions: [
    { symbol, source, is_replay, entry_date, days_open,
      outcome_status: "open_pending",
      exit_rule: null, exit_rule_status: "unavailable",
      diagnostic_labels: [...]
    }
  ]
}
```

Per-row labels are subset of `vocabulary`. The frontend is enforced
to render only labels from this set.

---

## Frontend cards

| Card | Page | Endpoints | `data-test` |
| --- | --- | --- | --- |
| `OpenPositionsPnLCard` | `/legacy/performance` | `/performance/paper/unrealized` | `open-positions-pnl-card`, `all-replay-note` |
| `OpenPositionsTable` | `/legacy/performance` | `/performance/paper/open-positions[?include_replay=true]` | `open-positions-table`, `replay-row-chip` |
| `ExitTrackingPanel` | `/legacy/performance` | `/performance/paper/exit-tracking` | `exit-tracking-panel`, `exit-tracking-disclaimer` |

All three are pure render — no `<button>`, no `onClick`, no
`useMutation`, no trading verbs.

---

## API examples (verified 2026-05-04)

```
GET /api/performance/paper/open-positions
→ count=0, live_count=0, replay_count=0   (default include_replay=false)

GET /api/performance/paper/open-positions?include_replay=true
→ count=18, replay_count=18, live_count=0
   sample row: is_replay=true, source="replay",
               unrealized_status="ok", days_open≈4.x,
               outcome_status="open_pending"

GET /api/performance/paper/unrealized
→ live: { n_positions: 0, total_unrealized_pnl_usd: null, best: null, worst: null }
   replay: { n_positions: 18, total_unrealized_pnl_usd: ~2323.70 }
   all_positions_are_replay: true

GET /api/performance/paper/exit-tracking?include_replay=true
→ count=18; every row exit_rule=null, exit_rule_status="unavailable",
   labels ⊂ vocabulary
```

---

## Definitions

| Term | Definition |
| --- | --- |
| open position | `paper_position.is_open=true`. |
| live position | open position with **no** matching `replay_recovery_manifest` row tagged `replay`/`test`. |
| replay position | open position with such a manifest row. |
| latest price | most recent `price_bar.close` for the asset (per-asset DISTINCT ON). |
| stale price | `now - latest_price_ts > STALE_PRICE_DAYS` (= 7). |
| unrealized P&L (per row) | `qty × (latest_price − avg_cost)` only when `latest_price` exists; otherwise `null` with `unrealized_status="unavailable"`. |
| unrealized return % | `(latest_price − avg_cost) / avg_cost` only when `avg_cost > 0`. |
| outcome status | `open_pending` for any row in `/open-positions` and `/exit-tracking`; never silently flipped to `closed`. |

---

## Rollback

- Delete the three new functions in
  `apps/api/src/api/performance_paper.py` (everything below the
  `Unrealized-PnL + exit tracking` divider).
- Remove imports + JSX usage in `apps/web/src/pages/Performance.tsx`
  (`OpenPositionsPnLCard`, `OpenPositionsTable`, `ExitTrackingPanel`).
- Delete the three card components under
  `apps/web/src/components/personal/`.
- Remove `apps/api/tests/unit/test_unrealized_exit_tracking.py`.
- No DB migrations, no scheduler entries, no fixtures to clean up.

---

## Tests added

- `apps/api/tests/unit/test_unrealized_exit_tracking.py` — 22 tests.

Combined backend safety pass on this stack:

| Suite | Result |
| --- | --- |
| `test_unrealized_exit_tracking.py` | 22/22 ✓ |
| `test_personal_analytics_phase.py` | 17/17 ✓ |
| `test_personal_analytics_frontend.py` | 16/16 ✓ |
| `test_paper_executed_api.py` | 10/10 ✓ |
| **Total relevant** | **65/65 passed** |
