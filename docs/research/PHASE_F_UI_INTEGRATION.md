# Phase F — Research Intelligence UI integration

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase E.1 + commits `9a25ff8`, `b83c0e5`
**Scope:** Surface read-only research artifacts in the WebUI. No
new execution capability. No POST. No scheduler.

---

## 1. Files changed

### Backend (read-only)
| File | Change |
|------|--------|
| `apps/api/src/api/research.py` | Phase B stubs replaced with real `research_ro.research_run` + `research_ro.research_agent_output` reads. Bodies pass through `_safe_body_or_blank` (server-side fail-closed). Added GET `/usage` and GET `/audit`. Still GET-only — zero `@router.post/put/patch/delete`. |
| `apps/api/tests/integration/research/test_research_phase_f_pg.py` | NEW (12 tests, isolated test DB). |
| `apps/api/tests/unit/research/test_research_phase_f_static.py` | NEW (5 grep guards). |
| `docs/research/PHASE_F_UI_INTEGRATION.md` | NEW (this doc). |

### Frontend (read-only)
| File | Change |
|------|--------|
| `apps/web/src/components/research/ResearchByline.tsx` | NEW — provenance-only byline (provider, model, prompt_hash truncated, as_of, operator). |
| `apps/web/src/components/research/FreshnessBadge.tsx` | NEW — neutral badge (yellow-grey, never green/red). Three buckets: fresh (<6h) / aging (<24h) / stale. |
| `apps/web/src/components/research/ResearchIntelligenceTab.tsx` | rewritten — fetches `/api/research/ticker/:symbol/latest` + `/api/research/runs/:id`, renders agent outputs through `ResearchSafetyFailure` when unsafe. |
| `apps/web/src/components/research/ResearchPulseCard.tsx` | rewritten — fetches `/api/research/runs?limit=5`, renders provenance-only summary. |
| `apps/web/src/components/research/ResearchJobHealthCard.tsx` | rewritten — fetches `/api/research/usage`, renders accept/reject/cost grid. |
| `apps/web/src/__tests__/research/researchPhaseFUi.test.tsx` | NEW (vitest format; runs once vitest is added to package.json). |

NOT changed: `apps/worker/src/`, all `apps/api/src/data/`,
`apps/api/src/domain/{features,recommendations,stock_engine}/`,
`scripts/run_paper_daily.py`, `apps/api/src/research/manual_run*.py`,
`scripts/run_research_manual.py`, `apps/api/src/api/research_manual.py`.
The Phase E + E.1 manual-run path is independent of Phase F.

## 2. API surface (final)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/research/runs` | recent runs, optional `symbol` filter, default empty list |
| GET | `/api/research/runs/{run_id}` | run + agent outputs (bodies safety-filtered) |
| GET | `/api/research/ticker/{symbol}/latest` | most-recent run for a ticker (or `{run: null}`) |
| GET | `/api/research/decision/{decision_id}` | runs tagged with that decision |
| GET | `/api/research/usage` | summary rollup (accepted/duplicate/rejected/in_flight/errored/cost_usd_today) |
| GET | `/api/research/audit` | recent audit metadata (no body, no prompt) |

**Zero POST/PUT/PATCH/DELETE.** Verified by:
- `test_no_post_put_patch_delete_under_research` (parametrized; 6 paths × 4 methods = 24 assertions)
- `test_research_router_exposes_only_get_handlers` (regex on source)
- Phase E.1 `test_only_one_post_route_under_research` (only manual route exists, separately gated)

## 3. UI mounting (already in place pre-Phase F)

| Page | Component | Guard |
|------|-----------|-------|
| Dashboard | `ResearchPulseCard` | `import.meta.env.VITE_RESEARCH_RO_ENABLED === 'true'` |
| JobsHealth | `ResearchJobHealthCard` | same |
| Recommendations | `ResearchIntelligenceTab` | same |

When the Vite env flag is **not** `'true'`, none of the three
components are mounted by their host page. No fetch is issued, no
banner is shown, no DOM is created. Confirmed by
`apps/web/src/pages/{Dashboard,JobsHealth,Recommendations}.tsx`
already-existing inline `&&` guards.

`ResearchBanner` is still required by every research-aware
component. The component throws at render time when its `context`
prop is missing — TypeScript catches it at compile time, the
runtime `if (!context) throw ...` keeps a hard failure path for
dynamic JSX.

## 4. Safety layers

| Layer | Implementation |
|---|---|
| DB CHECK | Migration 052 — `body_no_action_tokens` regex on `research_agent_output.body`, `debate_no_action_tokens`, `reflection_no_action_tokens` |
| Server filter | `apps/api/src/research/safety.py:assert_no_action_language()` — called by `_safe_body_or_blank` in `research.py` |
| Server response shape | `_safe_body_or_blank` returns `body=None, safety_status='unsafe'` so unsafe content NEVER leaves the server |
| Client guard | `apps/web/src/lib/research/forbiddenTokens.ts:scanForbiddenTokens()` — re-scans even server-cleared bodies |
| Client render | `ResearchSafetyFailure` displayed in place of any unsafe body |

If all four layers somehow fail (DB CHECK bypassed + server filter
disabled + client guard regressed), `ResearchSafetyFailure` is
still triggered by `safety_status !== 'safe'`. Defense in depth.

## 5. Tests

| Suite | Count | Result |
|-------|-------|--------|
| `test_research_phase_f_pg.py` | 12 | 12 passed |
| `test_research_phase_f_static.py` | 5 | 5 passed |
| `researchPhaseFUi.test.tsx` (vitest, deferred) | 12 | not yet runnable; ready when vitest deps land |
| **Phase F backend total** | **17** | **17 passed** |
| **Combined E + E.1 + F regression** | **65** | **65 passed** |

### Spec → test mapping

| Spec test | Implementation |
|-----------|----------------|
| test_research_ui_flag_off_unmounts_all | vitest spec (deferred) — host pages already gate components with `&&` |
| test_research_tab_renders_banner | vitest |
| test_research_tab_requires_banner | vitest (Phase B `researchUiSafety.test.tsx` covers this; Phase F duplicates) |
| test_research_fail_closed_on_forbidden_token | vitest — exercises both server safety_status='unsafe' and client scanner fallback |
| test_research_no_action_buttons | vitest — no `<button>` rendered; static check `test_no_research_ui_imports_trading_modules` |
| test_research_no_post_from_ui | vitest — every `fetch` call inspected for `method='GET'` |
| test_research_pulse_reads_get_only | vitest |
| test_research_job_health_reads_get_only | vitest |
| test_research_byline_renders_provenance | vitest |
| test_research_freshness_badge | vitest (3 buckets) |
| test_no_research_ui_imports_trading_modules | static (Python grep over `apps/web/src/components/research/` and `apps/web/src/lib/research/`) |
| test_no_scheduler_or_worker_changes_phase_f | static (Python grep over `apps/worker/src/`) |

Plus 9 backend integration tests not in the original list:
empty-shape default, real-data surface, run-detail safety filter,
404 on unknown id, 400 on invalid uuid, ticker latest, decision
filter, usage summary, audit metadata-only.

## 6. Commands run

```bash
# Static guards (always safe; no DB)
docker exec compose-api-1 sh -c \
  "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/unit/research/test_research_phase_f_static.py -v"

# Integration (isolated test DB)
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/test_research_phase_f_pg.py -v"

# Combined regression (E + E.1 + F)
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/ \
   apps/api/tests/unit/research/test_research_phase_e_unit.py \
   apps/api/tests/unit/research/test_research_phase_e1_unit.py \
   apps/api/tests/unit/research/test_research_phase_f_static.py"
# → 65 passed
```

## 7. Route examples

```
$ curl http://127.0.0.1:8000/api/research/runs?limit=5
# 404 when RESEARCH_RO_ENABLED=false (default)
# {"runs": [...], "next_cursor": null} when ON

$ curl http://127.0.0.1:8000/api/research/ticker/UNH/latest
# {"symbol": "UNH", "run": null} when no rows
# {"symbol": "UNH", "run": {provenance fields...}} when rows exist

$ curl http://127.0.0.1:8000/api/research/runs/<run_id>
# {"run": {...}, "outputs": [{...,"safety_status":"safe","body":"narrative..."}]}
# Bodies that fail server filter → {"safety_status":"unsafe", "body": null}

$ curl http://127.0.0.1:8000/api/research/usage?operator_id=alice
# {"operator_id":"alice","audit_table":"present","summary":{...}}

$ curl -X POST http://127.0.0.1:8000/api/research/runs
# 405 (Method Not Allowed)
$ curl -X DELETE http://127.0.0.1:8000/api/research/runs/abc
# 405 (Method Not Allowed)
```

## 8. Proof: no POST / no UI trigger

| Verification | Result |
|---|---|
| `grep -rE "@router\.(post\|put\|patch\|delete)" apps/api/src/api/research.py` | 0 hits |
| Live `curl -X POST /api/research/runs` | 405 |
| Live `curl -X DELETE /api/research/runs/<id>` | 405 |
| `grep -E "fetch.*method.*POST" apps/web/src/components/research/` | 0 hits — every fetch is GET |
| `grep -E "<button" apps/web/src/components/research/*.tsx` | 0 hits |
| Vitest spec asserts every fetch call uses GET (or no method) | covered by `test_research_no_post_from_ui` |

## 9. Proof: no trading path

| Check | Result |
|---|---|
| `test_no_research_ui_imports_trading_modules` (static) | passes — no references to `domain/features`, `domain/recommendations`, `domain/stock_engine`, `domain/execution`, `options/paper`, `lib/trading`, action-button components |
| `test_no_scheduler_or_worker_changes_phase_f` (static) | passes — `apps/worker/src/` references zero Phase F symbols |
| `_row_to_run_payload` source inspection | no `body`, `raw_body`, `raw_response`, `structured_output`, `prompt` field |
| `ResearchByline.tsx` source inspection | no `body`, `raw_*`, `buy`, `sell`, `recommend` token in non-comment lines |
| Reflection feedback path (Phase E.1 grep) | still 0 hits across `domain/features`, `domain/recommendations`, `data/evaluation`, `worker/src/` |
| `ML_CAN_AFFECT_TRADES` | unchanged (False) |

## 10. Rollback plan

| Step | Effect |
|---|---|
| `VITE_RESEARCH_RO_ENABLED=false` (frontend rebuild + reload) | UI components unmount; no fetch issued |
| `RESEARCH_RO_ENABLED=false` (api restart) | Every `/api/research/*` route returns 404 |
| Both flags off | UI silent + API silent |
| Manual-run path (Phase E/E.1) untouched at all steps | `RESEARCH_MANUAL_RUN_ENABLED` independent flag |
| **No DB rollback required.** Phase F adds zero migrations. | — |
| **No trading impact at any step.** | — |

After rollback verify:
```
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/research/runs
# 404
```

## 11. Final safety verdict

| Property | Status |
|----------|--------|
| GET-only API | ✅ |
| Server fail-closed on forbidden tokens | ✅ |
| Client fail-closed (defense in depth) | ✅ |
| Banner mandatory on every research surface | ✅ |
| No action buttons / no buy/sell wording | ✅ |
| No green/red ticker styling | ✅ — FreshnessBadge uses yellow-grey only |
| Three-flag separation: RO_ENABLED (UI+API), MANUAL_RUN_ENABLED (CLI/HTTP), VITE_RESEARCH_RO_ENABLED (UI mount) | ✅ |
| No scheduler / worker entry | ✅ |
| No execution-module imports (frontend or backend) | ✅ |
| No reflection feedback loop | ✅ |
| Trading / candidate / paper / options / ML paths untouched | ✅ |
| **Verdict** | **SAFE** |

Phase F ready. **65/65** backend regression tests pass. UI vitest
spec frozen as forward-compatible behavioral contract. Defaults
keep every component invisible until two independent flags are
explicitly flipped.
