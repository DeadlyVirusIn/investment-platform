# Personal-Analytics Phase

Personal paper-trading + ML-research instrumentation. Read-only
dashboards over existing data. **No live trading. No ML→execution
coupling. No new scheduler entries. No model training from these
endpoints.**

---

## Goals

1. Visibility into paper-trading performance with honest live-vs-replay
   separation.
2. ML-readiness diagnostics that report `ready=false` until labels
   actually accumulate.
3. Options shadow diagnostics surfaced as a read-only card with a hard
   disclaimer that no execution path exists.

---

## Hard policy

| Rule | Enforcement |
| --- | --- |
| `ML_CAN_AFFECT_TRADES` stays `false` | Compose default; static-grep tests reject any literal `ML_CAN_AFFECT_TRADES=true` in cards/pages. |
| No live trading toggled by these endpoints | All four new endpoints are GET-only; `test_personal_analytics_phase.py::test_only_get_router_decorators` pins it. |
| No POST handlers added | Same test rejects any `@router.{post,put,patch,delete}`. |
| No DB writes from these endpoints | `test_no_db_writes_in_source` regex-rejects `INSERT INTO`, `UPDATE … SET`, `DELETE FROM` in `performance_paper.py` and `ml_insights.py`. |
| No scheduler/worker entry | No edits to `apps/worker/src/scheduler/*` or `infra/docker/worker.crontab`. |
| Replay rows never silently inflate live counts | `replay_recovery_manifest` is honored: split counts always-on, exclusion default. |

---

## Endpoints

### `/api/performance/paper/*`

| Path | Returns |
| --- | --- |
| `GET /summary` | live + replay split counts, realized P&L total, win/loss/breakeven, win rate (`null` until decided trades exist), best/worst trade, source breakdown, outcome bucket counts. |
| `GET /trades?include_replay=…&closed_only=…&limit=…` | trade rows with `source`, `replay_run_id`, `outcome_status` ∈ {closed, open_pending}. |
| `GET /equity?include_replay=…` | open-position exposure by symbol + sector aggregate; per-row `unrealized_status` ∈ {ok, unavailable} when no recent `price_bar` exists. |
| `GET /attribution?include_replay=…` | realized-P&L attribution by symbol and by source; pending vs closed reported separately, never merged. |

### `/api/ml/insights/*`

| Path | Returns |
| --- | --- |
| `GET /summary` | counts (recommendations, outcomes, labeled, open_pending, replay-tagged decisions/outcomes/snapshots), `ready: bool`, `reason`, `min_labeled_outcomes_required`, `ml_can_affect_trades: false`. |
| `GET /dataset` | decision/replay row totals; `recommendations.{live, replay, total}` invariant `live + replay = total`; advisory notes about leakage and splitter ownership. |
| `GET /features` | static feature column list, identity columns, leakage-check declaration. Pure metadata — no DB scan. |
| `GET /labels` | barrier-label distribution + `barrier_label_open_pending` separately, realized-return labeled/pending counts, `note: "ML evaluation not ready — outcomes still pending."` when zero labels. |

---

## Metrics definitions

| Metric | Definition |
| --- | --- |
| live trade | row in `paper_trade` with **no** matching `replay_recovery_manifest` row tagged `replay`/`test`. |
| replay-recovered trade | row in `paper_trade` with a manifest row tagged `replay`/`test`. |
| closed trade | `paper_trade.realized_pnl IS NOT NULL`. |
| open trade | `paper_trade.realized_pnl IS NULL`. |
| open position | `paper_position.is_open = true`. |
| realized P&L total | `sum(realized_pnl)` across closed trades, scoped by `include_replay`. |
| win rate | `wins / (wins + losses)` only when denominator > 0; otherwise `null` with `note="no_closed_outcomes_yet"`. **Never fabricated.** |
| unrealized P&L (per row) | `qty × (last_price − avg_cost)` only when a `price_bar` row exists for the asset; otherwise `unrealized_status="unavailable"`. |
| labeled outcome | `recommendation_outcome.barrier_label IS NOT NULL OR realized_30d_return IS NOT NULL`. |
| open_pending outcome | row exists but both `barrier_label` and `realized_30d_return` are `NULL`. |
| missing outcome | recommendation with no `recommendation_outcome` row. |
| ML readiness | `labeled_outcomes >= MIN_LABELED_OUTCOMES (=20)`. Never auto-promotes. |

---

## Replay / live data policy

- Default response excludes replay rows (`include_replay=false`).
- Split counts (`live_trades_count`, `replay_trades_count`,
  `live_open_positions_count`, `replay_open_positions_count`,
  `has_replay_recovered_rows`) are always returned regardless of the
  flag.
- UI cards must label replay rows as **"Recovered replay — not live
  trading activity"**.
- Replay rows are always excluded from the headline metrics on the
  Performance page; the existing `/portfolio` Paper Trading Terminal is
  the canonical surface for inspecting them.

---

## ML read-only policy

- These endpoints **do not** import from `recommendation_engine`,
  `auto_trader`, `paper_service`, `execution.*`, or any scheduler
  module. Test `test_ml_insights_no_strategy_or_execution_imports`
  enforces.
- Cards have **no buttons** that would suggest training or scoring
  (`<button>`, `onClick=`, `<input>`, `Train model`, `Promote`,
  `Score now`, `Enable ML` are all rejected by the frontend test).
- Readiness flips to `true` only when labels reach the floor; the
  reason string is exposed verbatim so an operator never has to guess
  why ML is gated.

---

## API examples (verified 2026-05-04)

```
GET /api/performance/paper/summary
→ { include_replay: false, total_trades: 0, win_rate: null,
    note: "no_closed_outcomes_yet",
    live_trades_count: 0, replay_trades_count: 18,
    has_replay_recovered_rows: true,
    source_breakdown: { "replay": 18 } }

GET /api/performance/paper/attribution
→ { by_source: [
      { source: "replay", total_trades: 18, closed_trades: 0,
        open_pending_trades: 18, realized_pnl_usd: 0 } ] }

GET /api/ml/insights/summary
→ { ml_can_affect_trades: false, ready: false,
    reason: "no_labeled_outcomes",
    min_labeled_outcomes_required: 20,
    counts: { recommendations_total: 63,
              recommendation_outcome_rows: 63,
              labeled_outcomes: 0,
              open_pending_outcomes: 63,
              missing_outcome_rows: 0,
              ml_replay_decision: 0, ml_replay_outcome: 0 } }

GET /api/ml/insights/labels
→ { labeled_outcomes_total: 0,
    barrier_label_open_pending: 63,
    realized_returns: { labeled_30d: 0, pending_30d: 63,
                        labeled_90d: 0, pending_90d: 63 },
    note: "ML evaluation not ready — outcomes still pending." }
```

---

## Frontend cards

| Card | Page | `data-test` | Endpoints |
| --- | --- | --- | --- |
| `PerformanceVisibilityCard` | `/legacy/performance` | `perf-visibility-card`, `perf-replay-banner`, `perf-no-closed-outcomes`, `perf-by-source-table` | `/performance/paper/summary`, `/performance/paper/attribution` |
| `MLInsightsCard` | `/ml-lab` | `ml-insights-card`, `ml-insights-no-execute-banner`, `ml-insights-readiness-checklist`, `ml-insights-pending-note` | `/ml/insights/summary`, `/ml/insights/labels`, `/ml/insights/features` |
| `OptionsShadowVisibilityCard` | `/options/*` (mounted in `OptionsLayout`) | `options-shadow-visibility-card`, `options-shadow-blocked-table` | `/options/shadow/summary`, `/options/pipeline-status` |

Each card is a pure render; none have buttons, mutations, or any
control surface. The "no execution" banner is rendered every time the
ML insights card is shown.

---

## Rollback

- Remove the two new routers from `apps/api/src/main.py` (the import +
  the router-tuple entry). The endpoints disappear cleanly.
- Delete `apps/api/src/api/performance_paper.py` and
  `apps/api/src/api/ml_insights.py`.
- Delete the three card components under
  `apps/web/src/components/personal/`.
- Remove the `import` and JSX usage from `Performance.tsx`,
  `MLLab.tsx`, and `OptionsLayout.tsx`.
- Tests delete: `test_personal_analytics_phase.py`,
  `test_personal_analytics_frontend.py`.

No DB migrations, no scheduler entries, no fixtures to clean up.

---

## Tests added

- `apps/api/tests/unit/test_personal_analytics_phase.py` (17 tests)
- `apps/api/tests/unit/test_personal_analytics_frontend.py` (16 tests)
