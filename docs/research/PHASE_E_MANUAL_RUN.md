# Phase E — Manual research run activation

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase 11Z (`9a25ff8`) + Phase 11X.2 (`b83c0e5`)
**Scope:** Add a *manual-only* trigger for the research-artifact
pipeline. Default OFF. Single CLI entry + single admin-only HTTP
route, both gated by **two** environment flags. NEVER schedules
itself. NEVER touches execution / scoring / candidate / paper /
options paths.

---

## 1. Files changed

| File | Type | Purpose |
|------|------|---------|
| `apps/api/src/config/__init__.py` | edit | + 7 settings (flag + caps + allowlists + admin token) |
| `apps/api/src/research/manual_run_safe.py` | NEW | Phase E gate enforcement; sanitized payload; never returns raw body |
| `apps/api/src/api/research_manual.py` | NEW | Admin-token-protected POST `/api/research/runs/manual` |
| `apps/api/src/main.py` | edit | Conditional router mount (3-flag check) |
| `scripts/run_research_manual.py` | NEW | CLI runner (operator-only) |
| `apps/api/tests/unit/research/test_research_phase_e_unit.py` | NEW | 15 pure-unit gate tests |
| `apps/api/tests/integration/research/test_research_phase_e_pg.py` | NEW | 10 integration tests against `pg-11v-test` |
| `docs/research/PHASE_E_MANUAL_RUN.md` | NEW | this doc |

NOT changed:
- `apps/api/src/research/manual_run.py` — the existing orchestrator,
  unchanged. Phase E wraps it.
- `apps/worker/src/` — zero diff. Confirmed by CI grep
  (`test_no_scheduler_entry_phase_e`, `test_no_worker_registry_entry_phase_e`).
- `apps/api/src/data/features/`, `apps/api/src/domain/recommendations/`,
  `apps/api/src/domain/stock_engine/` — zero diff. Confirmed by CI
  grep (`test_no_execution_imports`, `test_research_outputs_not_consumed_by_engines`).
- `infra/alembic/versions/` — zero new migrations. Phase E ships no
  schema changes.

## 2. Feature flags + config (defaults)

```python
RESEARCH_RO_ENABLED:               bool  = False    # Phase B flag, unchanged
RESEARCH_MANUAL_RUN_ENABLED:       bool  = False    # NEW Phase E flag
RESEARCH_MAX_RUN_COST_USD:         float = 0.05
RESEARCH_MAX_DAILY_COST_USD:       float = 1.00
RESEARCH_MAX_TICKER_DAILY_RUNS:    int   = 3
RESEARCH_ALLOWED_PROVIDERS:        str   = "mock"   # CSV
RESEARCH_ALLOWED_SYMBOLS:          str   = ""       # CSV; empty = no allowlist
RESEARCH_ADMIN_TOKEN:              str   = ""       # required for HTTP route
```

The HTTP route is mounted only when **all three** of `RESEARCH_RO_ENABLED`,
`RESEARCH_MANUAL_RUN_ENABLED`, and `bool(RESEARCH_ADMIN_TOKEN.strip())`
are true at process boot. Any false value → router not registered →
`POST /api/research/runs/manual` returns 404 (default FastAPI handler).

## 3. Execution conditions enforced (in order)

```
1. RESEARCH_RO_ENABLED == True
2. RESEARCH_MANUAL_RUN_ENABLED == True
3. operator_id non-empty
4. triggered_by ∈ {'manual', 'operator'}
5. symbol matches strict regex ^[A-Z][A-Z0-9.\-]{0,9}$
6. as_of ≤ today
7. provider ∈ RESEARCH_ALLOWED_PROVIDERS (CSV; default {'mock'})
8. symbol ∈ RESEARCH_ALLOWED_SYMBOLS (when CSV non-empty)
9. asset row exists with is_active=true
10. SUM(cost_usd) for today < RESEARCH_MAX_DAILY_COST_USD
11. count(research_run today, symbol=X) < RESEARCH_MAX_TICKER_DAILY_RUNS
12. (Delegate to existing orchestrator — applies prompt_hash, per-provider
    cost cap, body safety filter, DB CHECK forbidden-token guard,
    schema validation, structured-output validation)
13. Idempotency: orchestrator UNIQUE on (symbol, as_of, provider,
    prompt_bundle_hash, input_snapshot_hash, schema_version) — duplicate
    INSERT raises IntegrityError, wrapper detects and returns the prior
    row's payload as 'duplicate'.
14. Sanitized payload constructed (run_id, status, counts, cost,
    safety_status). Raw provider body NEVER returned.
```

## 4. Tests run safely

Test DB: `postgresql+psycopg://test:test@pg-11v-test:5432/test`
(isolated; safety guard rejects any URL whose host is the dev/compose
DB).

| Suite | Count | Result |
|-------|-------|--------|
| `apps/api/tests/unit/research/test_research_phase_e_unit.py` | 15 | 15 passed |
| `apps/api/tests/integration/research/test_research_phase_e_pg.py` | 10 | 10 passed |
| **Total** | **25** | **25 passed** |

### Spec → test mapping

| # | Spec test name | Implemented as |
|---|----------------|----------------|
| 1 | test_manual_run_endpoint_not_mounted_when_flag_off | integration `test_manual_run_endpoint_not_mounted_when_flag_off` |
| 2 | test_manual_run_endpoint_requires_admin | integration `test_manual_run_endpoint_requires_admin` |
| 3 | test_manual_run_rejects_provider_not_allowlisted | integration `test_manual_run_rejects_provider_not_allowlisted` |
| 4 | test_manual_run_rejects_symbol_not_allowlisted | integration `test_manual_run_rejects_symbol_not_allowlisted` |
| 5 | test_manual_run_enforces_cost_cap_before_provider_call | integration `test_manual_run_enforces_daily_cost_cap_before_provider` |
| 6 | test_manual_run_writes_only_research_ro | integration `test_manual_run_writes_only_research_ro_and_never_execution` |
| 7 | test_manual_run_never_writes_execution_tables | integration (same as #6) |
| 8 | test_manual_run_rejects_forbidden_tokens | integration `test_manual_run_rejects_forbidden_tokens` |
| 9 | test_manual_run_records_provenance | integration `test_manual_run_records_provenance` |
| 10 | test_manual_run_idempotency | integration `test_manual_run_idempotency` |
| 11 | test_no_scheduler_entry_phase_e | unit `test_no_scheduler_entry_phase_e` |
| 12 | test_no_worker_registry_entry_phase_e | unit `test_no_worker_registry_entry_phase_e` |
| 13 | test_no_execution_imports_from_research | unit `test_no_execution_imports` (parametrized over 3 files) |
| 14 | test_no_reflection_feedback_path | unit `test_no_reflection_feedback_path` |
| 15 | test_research_outputs_not_consumed_by_feature_engine_or_recommendation_engine | unit `test_research_outputs_not_consumed_by_engines` |
| 16 | test_api_response_never_contains_unsafe_raw_output | unit `test_response_payload_has_no_body_field` |

Plus 9 additional unit-level guards: route scan (only one POST), no
LangChain/LangGraph at module load, no filesystem memory, migration
scan (Phase E adds no public→research_ro FK), CSV allowlist parsing,
strict symbol regex, future-date rejection, and a per-ticker quota
test.

## 5. Commands to run

### Unit tests (no DB; always safe)
```bash
docker exec compose-api-1 sh -c \
  "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/unit/research/test_research_phase_e_unit.py -v"
```

### Integration tests (isolated test DB)
```bash
docker exec -e \
  TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c \
  "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/test_research_phase_e_pg.py \
   -v -m integration"
```

### CLI runner (manual operator invocation)
```bash
RESEARCH_RO_ENABLED=true RESEARCH_MANUAL_RUN_ENABLED=true \
  python -m scripts.run_research_manual \
  --symbol UNH --as-of 2026-04-29 --provider mock \
  --operator-id ops@me
```

### HTTP endpoint (admin token required)
```bash
# Set in compose env or .env, then restart:
RESEARCH_RO_ENABLED=true
RESEARCH_MANUAL_RUN_ENABLED=true
RESEARCH_ADMIN_TOKEN=<some-strong-secret>
```
```bash
curl -X POST http://127.0.0.1:8000/api/research/runs/manual \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <some-strong-secret>" \
  -d '{"symbol":"UNH","as_of":"2026-04-29","provider":"mock","operator_id":"ops@me"}'
```

## 6. Proof Phase E remains manual-only and research-only

### A. No scheduler / worker entry (CI gate)
```
$ grep -rn "manual_run_safe\|research_manual" apps/worker/src/
(no output)
```
Test: `test_no_scheduler_entry_phase_e`, `test_no_worker_registry_entry_phase_e` → both PASS.

### B. No execution-path imports (CI gate)
Phase E modules never import from `domain.features.feature_engine`,
`domain.recommendations.recommendation_engine`, `data.evaluation`,
`domain.stock_engine.decision_engine`, `options.paper`,
`domain.execution`. Confirmed by parametrized
`test_no_execution_imports` (3 files × 6 forbidden modules = 18 grep
checks).

### C. Reflection has no feedback edge
`test_no_reflection_feedback_path` greps every `.py` file in
`apps/api/src/domain/features/`, `apps/api/src/domain/recommendations/`,
`apps/api/src/data/evaluation/`, and `apps/worker/src/` for the
string `research_reflection`. Zero hits. Reflection rows (when
written by future phases) remain labeled history only.

### D. API response payload has no raw body
`ManualRunPayload` dataclass exposes only:
`run_id, status, symbol, as_of, provider, model_id, model_version,
 tokens_in, tokens_out, cost_usd, operator_id, triggered_by,
 idempotency_key, safety_status`.
No `body`, `raw_body`, `raw_response`, `structured_output`,
`agent_output`, `evidence_refs`, or `reflection` field.
Confirmed by `test_response_payload_has_no_body_field`.

### E. Forbidden tokens fail closed at DB
DB CHECK regex on `research_agent_output.body`,
`research_debate_summary.bullish_summary/bearish_summary/tension_note`,
and `research_reflection.body` rejects every word in the synthesis
forbidden list at INSERT time. Verified live by
`test_manual_run_rejects_forbidden_tokens` (insert "we recommend buy
AAPL" → IntegrityError caught).

### F. Costs enforced before provider call
`_assert_caps()` runs BEFORE `run_single_asset_context_note()` is
imported and called. Daily-cost-cap test pre-seeds a $100 row on
today's date, sets cap to $1, then calls the manual entry — no new
research_run row is created (no provider call attempted).

### G. Per-ticker quota enforced
Pre-seeded one run for `UNH` today, set cap to 1, second call
raises `PhaseEQuotaExceededError` BEFORE provider invocation.

### H. Sanitized "duplicate" outcome on idempotency collision
Second call with identical inputs returns the prior `research_run`
id with sanitized metadata; never invokes the provider; never
creates a duplicate row.

### I. Two-flag mount of HTTP route
Live test: with `RESEARCH_RO_ENABLED=False, RESEARCH_MANUAL_RUN_ENABLED=False, RESEARCH_ADMIN_TOKEN=""`
the route is not registered. With all three set, the route exists
but every request without `X-Admin-Token` returns 422; wrong token →
403. Tests: `test_manual_run_endpoint_not_mounted_when_flag_off`,
`test_manual_run_endpoint_requires_admin`.

### J. Sanitized result payload only
Both CLI runner and HTTP route serialize `ManualRunPayload.as_dict()`
verbatim. The dataclass has no `body` field; even if a future caller
JSON-encoded the entire envelope, no provider body would leak.

## 7. Rollback plan

Step | Effect
-----|-------
`RESEARCH_MANUAL_RUN_ENABLED=false` and restart api/worker | HTTP route 404; CLI rejects with `[disabled]` exit 2
`RESEARCH_RO_ENABLED=false` and restart | All `/api/research/*` routes 404; UI components don't mount
Remove `apps/api/src/api/research_manual.py` import block in main.py | Hardcodes "no Phase E HTTP route"
Delete `apps/api/src/research/manual_run_safe.py` and `scripts/run_research_manual.py` | Removes Phase E entirely; underlying Phase D orchestrator unaffected and remains callable only via Python imports
Delete tests: `apps/api/tests/unit/research/test_research_phase_e_unit.py` and `apps/api/tests/integration/research/test_research_phase_e_pg.py` | Removes test surface
**No DB rollback required.** Phase E adds no migrations. | —

After rollback, verify:
```
curl -fsS -o /dev/null -w "%{http_code}\n" \
  http://127.0.0.1:8000/api/research/runs/manual
# expected: 404
```

## 8. Bottom line

* Phase E adds **5** new code files + **2** test files + **1** doc.
* Adds **7** config knobs, all defaulting to safe values.
* HTTP route is **triple-gated**: RESEARCH_RO_ENABLED **AND**
  RESEARCH_MANUAL_RUN_ENABLED **AND** RESEARCH_ADMIN_TOKEN non-empty.
* CLI is **double-gated**: RESEARCH_RO_ENABLED **AND**
  RESEARCH_MANUAL_RUN_ENABLED.
* **25/25** tests pass on isolated test DB.
* Strategy thresholds, candidate scoring, Engine A/B, paper
  execution, options execution, ML inference — **zero diff**.
* No scheduler entry. No worker registry entry. No reflection
  feedback path. No execution-table writes. No raw model body in
  any API response.
* Rollback = single env flag; no schema change.
