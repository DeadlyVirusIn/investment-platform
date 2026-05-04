# WebUI Endpoint → Data-Source Audit

Last verified: 2026-05-03 (after Phase 11Z replay-visibility + options chain ingest pass).

This is a living matrix mapping every major WebUI page to the endpoint(s) it consumes, the underlying DB tables those endpoints read, the current row counts, and the operator-facing UI state that should render given those counts.

`scripts/audit_webui_endpoints.py` automates the GET-only checks below; this doc documents intent so the script's pass/fail reads correctly.

## Snapshot of source-table row counts (2026-05-03)

| Table | Rows |
| --- | ---: |
| `paper_trade` | 18 (all replay-tagged) |
| `paper_trade_log` | 0 |
| `paper_position` | 18 (all replay-tagged) |
| `paper_run_log` | 6 |
| `recommendation` | 63 |
| `options_chain_snapshot` | 10 |
| `options_shadow_decision_log` | 10 |
| `options_paper_trade` | 0 |
| `replay_recovery_manifest` | 109 |
| `context_daily` | 50 |
| `asset` | 63 |
| `price_bar` | 63 252 |

## Per-page audit

### Overview / Dashboard

| Field | Value |
| --- | --- |
| Page | `apps/web/src/pages/Overview.tsx` |
| Endpoints | `GET /dashboard/summary`, `GET /paper/summary`, `GET /briefing/narrative` |
| Source tables | `paper_run_log`, `recommendation`, `paper_position`, `context_daily` |
| Expected UI state | Strip with NAV, return, drawdown; "live paper portfolio" copy. Replay banner suppressed at this level (PortfolioTerminal owns it). |
| Current API response | `paper/summary` reads from positions/run logs; with `paper_position=18 (all replay)` the equity strip shows derived NAV. |
| Mismatch | None observed; numbers reflect replay state. |

### PortfolioTerminal — paper trading

| Field | Value |
| --- | --- |
| Page | `apps/web/src/pages/PortfolioTerminal.tsx` |
| Endpoints | `GET /paper/summary`, `GET /paper/state`, `GET /paper/equity`, `GET /paper/trades` (selector log), `GET /paper/executed/summary?include_replay=...`, `GET /paper/executed/trades?include_replay=...`, `GET /paper/executed/positions?include_replay=...&is_open=true`, `GET /paper/performance` |
| Source tables | `paper_trade` + `paper_position` (account path), `paper_trade_log` (selector path), `paper_run_log`, `replay_recovery_manifest` |
| Expected UI state | Header always shows live counts (`live_trades_count`, `live_open_positions_count`). When `has_replay_recovered_rows=true` the warning banner shows explicit recovered counts (`replay_trades_count`, `replay_open_positions_count`) AND the operator toggle "Show recovered replay data" (default OFF). |
| Current API response | `live_trades_count=0`, `replay_trades_count=18`, `live_open_positions_count=0`, `replay_open_positions_count=18`, `has_replay_recovered_rows=true`. |
| Mismatch | Pre-Phase 11Z header rendered `trades_total` filtered by toggle, hiding the live=0 truth. Fixed: header now renders the always-on split counts, banner spells out recovered counts, and rows show a `replay` chip for `source='replay'`. |

### Paper portfolio (legacy page)

| Field | Value |
| --- | --- |
| Page | `apps/web/src/pages/Portfolio.tsx` (`/legacy/...` and other deep links) |
| Endpoints | `GET /paper/portfolios`, `GET /paper/portfolios/:id`, `GET /paper/portfolios/:id/trades`, `GET /paper/portfolios/:id/equity` |
| Source tables | `paper_portfolio`, `paper_trade`, `paper_position` |
| Expected UI state | Lists paper portfolios; per-portfolio trades + equity. Reads same `paper_trade` rows as PortfolioTerminal but does NOT split live vs replay. |
| Current API response | Returns 1 portfolio with 18 trades, all replay-tagged. |
| Mismatch | Legacy view does not show provenance. Acceptable: page is reachable only via `/legacy/...` routes; PortfolioTerminal is the canonical surface. Future cleanup. |

### Decisions

| Field | Value |
| --- | --- |
| Page | `apps/web/src/pages/Decisions.tsx` |
| Endpoints | `GET /decision-log/{date}`, `GET /paper/runs/latest`, `GET /paper/runs/latest/events` |
| Source tables | `decision_log`, `paper_run_log` |
| Expected UI state | Most-recent run-day decisions with engine attribution. |
| Current API response | `paper_run_log=6` so a recent run renders; `decision_log=6` matches. |
| Mismatch | None. |

### Recommendations

| Field | Value |
| --- | --- |
| Page | `apps/web/src/pages/Recommendations.tsx` |
| Endpoints | `GET /recommendations` |
| Source tables | `recommendation`, `recommendation_evidence` |
| Expected UI state | List of recent recommendations with evidence chips. |
| Current API response | 63 rows present — page renders. |
| Mismatch | None. |

### Options page

| Field | Value |
| --- | --- |
| Pages | `apps/web/src/pages/options/OptionsLayout.tsx` + sub-pages |
| Banner | `apps/web/src/components/options/OptionsDataAvailabilityBanner.tsx` (3-state) |
| Endpoints | `GET /options/health`, `GET /options/pipeline-status`, `GET /options/symbols`, `GET /options/expiries`, `GET /options/chain`, `GET /options/features`, `GET /options/paper-trades`, `GET /options/risk-summary`, `GET /options/shadow/summary`, `GET /options/shadow/runs`, `GET /options/shadow/runs/{date}` |
| Source tables | `options_chain_snapshot`, `options_feature_daily`, `options_paper_trade`, `options_shadow_decision_log` |
| Expected UI state — STATE 1 | `options_chain_snapshot_count=0` → banner: "No options chain data ingested" with `data-test="options-banner-no-chain"`. Operator must run `scripts.ingest_options_chain`. |
| Expected UI state — STATE 2 | Chain count > 0 AND `shadow.total_runs=0` → banner: "Options chain ingested · shadow evaluator has not run yet" with `data-test="options-banner-chain-no-evals"`. Operator must run `scripts.run_options_shadow_eval`. |
| Expected UI state — STATE 3 | `shadow.total_runs > 0` → banner silent; sub-pages render their own data. |
| Current API response | `options_chain_snapshot=10`, `options_shadow_decision_log=10` (`total_runs=1`), `options_paper_trade=0` → STATE 3 (silent banner). |
| Mismatch | Pre-pass STATE 1 was the only state served, even after chain data appeared. Fixed: banner reads `pipeline-status` for the chain count and `shadow/summary` for run count and renders the correct state. `options_paper_trade` remains 0 — no live execution possible. |

### Jobs / Health

| Field | Value |
| --- | --- |
| Page | `apps/web/src/pages/JobsHealth.tsx` |
| Endpoints | `GET /jobs/status`, `GET /scheduler/health`, `GET /system/health`, `GET /system/health-score` |
| Source tables | `daily_run_status`, `paper_run_log`, `replay_recovery_manifest`, env-derived markers |
| Expected UI state | Lists scheduled jobs, last-run timestamps, freshness, and overall system health. |
| Current API response | Returns the registered worker jobs and most-recent run timestamps. |
| Mismatch | None. |

### Research / Research Lab

| Field | Value |
| --- | --- |
| Pages | `apps/web/src/pages/Research.tsx`, `apps/web/src/pages/ResearchLab.tsx` |
| Endpoints | `GET /research/runs`, `GET /research/manual/runs`, `GET /research/runs/:id`, `GET /alpha/...`, `GET /v2-promotion/state`, `GET /v2-promotion/snapshots`, `GET /b2-v2-comparison`, `GET /engine-b/...` |
| Source tables | `research_manual_run_audit`, `v2_promotion_state`, `v2_promotion_snapshot`, `system_alpha_*`, `engine_b_*` |
| Expected UI state | Tier-gated read-only research surface; surfaces evaluator output, validation runs, comparisons. |
| Current API response | Tier badge resolves; comparison endpoints return latest persisted snapshot. |
| Mismatch | None observed in this pass. |

### Account / Plan badge

| Field | Value |
| --- | --- |
| Component | `apps/web/src/components/research/AccountPlanBadge.tsx` |
| Endpoint | `GET /auth/me` |
| Source tables | `auth_user`, `subscription`, `org` |
| Expected UI state | Renders user email + plan/tier; gates premium content client-side (server still enforces). |
| Current API response | Local dev mode returns operator user. |
| Mismatch | None. |

## Static safety pins (verified in tests)

- `apps/api/src/api/paper_executed.py` — `test_paper_executed_api.py::test_no_writes_in_source` rejects any INSERT/UPDATE/DELETE.
- `apps/api/src/api/options_shadow.py` — GET-only via `test_options_shadow_get_only` (existing).
- `scripts/ingest_options_chain.py` — `test_ingest_options_chain.py::test_source_has_no_writes_to_forbidden_tables` rejects writes to `options_paper_trade`, `paper_trade`, `paper_trade_log`, `options_shadow_decision_log`.
- `scripts/run_options_shadow_eval.py` — eval persists only to `options_shadow_decision_log` and requires `OPTIONS_SHADOW_EVAL_ENABLED=true`.
- `OPTIONS_CHAIN_INGEST_CONFIRM=I_UNDERSTAND_THIS_WRITES_OPTIONS_CHAIN_DATA` required for any chain-ingest commit.
- `ML_CAN_AFFECT_TRADES=false` is the default in `infra/compose/docker-compose.yml`; not flipped this pass.
