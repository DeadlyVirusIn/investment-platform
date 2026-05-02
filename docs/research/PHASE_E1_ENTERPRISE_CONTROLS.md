# Phase E.1 — Enterprise-safe controls for Research Manual Runs

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase E + commits `9a25ff8`, `b83c0e5`
**Scope:** Add operator allowlist, rate limiting, append-only audit
log, usage tracking, and rule-based anomaly detection on top of
Phase E. **No UI. No scheduler. No execution wiring.**

---

## 1. Files changed

| File | Type | Purpose |
|------|------|---------|
| `infra/alembic/versions/057_research_manual_run_audit.py` | NEW | append-only `research_ro.research_manual_run_audit` |
| `apps/api/src/config/__init__.py` | edit | + 9 settings (allowlist + rate caps + anomaly thresholds) |
| `apps/api/src/research/manual_run_controls.py` | NEW | allowlist + rate limits + audit + usage + anomaly |
| `apps/api/src/research/manual_run_safe.py` | edit | wires controls + audit-on-rejection + sanitized provenance lookup |
| `apps/api/src/api/research_manual.py` | edit | passes `request_source='http'` to wrapper |
| `scripts/run_research_manual.py` | edit | passes `request_source='cli'` to wrapper |
| `apps/api/tests/unit/research/test_research_phase_e1_unit.py` | NEW | 12 pure-unit guards |
| `apps/api/tests/integration/research/test_research_phase_e1_pg.py` | NEW | 11 integration tests |
| `apps/api/tests/integration/research/test_research_phase_e_pg.py` | edit | per-test truncate of audit table; default-enable LOCAL_TEST_MODE for legacy operator IDs |
| `docs/research/PHASE_E1_ENTERPRISE_CONTROLS.md` | NEW | this doc |

NOT changed: `apps/worker/src/`, `apps/api/src/data/features/`,
`apps/api/src/domain/recommendations/`, `apps/api/src/domain/stock_engine/`,
`scripts/run_paper_daily.py`, `apps/api/src/research/manual_run.py`
(Phase E orchestrator unchanged), no UI files.

## 2. Tables added

```
research_ro.research_manual_run_audit
  id                  uuid PK
  created_at          timestamptz default now()
  operator_id         text NOT NULL
  symbol              text NOT NULL
  as_of               date NOT NULL
  provider            text NOT NULL
  model_id            text NULL
  request_source      text NOT NULL  -- CHECK ('cli','http')
  prompt_hash         text NULL
  estimated_cost_usd  numeric(12,6) NULL
  actual_cost_usd     numeric(12,6) NULL
  status              text NOT NULL  -- CHECK ('in_flight','accepted','rejected','duplicate','error')
  rejection_reason    text NULL
  anomaly_flags       jsonb default '[]'
  research_run_id     uuid NULL
  request_id          text NULL  -- UNIQUE WHERE NOT NULL

  Indexes:
    ix_audit_created          (created_at DESC)
    ix_audit_operator_created (operator_id, created_at DESC)
    ix_audit_symbol_created   (symbol, created_at DESC)
    ix_audit_status_created   (status, created_at DESC)
    ux_audit_request_id       UNIQUE (request_id) WHERE request_id IS NOT NULL

  Grants:
    research_writer : INSERT, SELECT, UPDATE
    research_reader : SELECT
```

The audit table is append-only by convention (the only UPDATE path
goes through `write_audit_terminal` which only mutates the
in-flight row's terminal status / metadata). No DELETE path.

## 3. Flags added (defaults)

```python
RESEARCH_ALLOWED_OPERATORS                = ""        # CSV; empty = no operator allowed
RESEARCH_LOCAL_TEST_MODE                  = False     # local-dev opt-out from allowlist
RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY      = 5
RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY        = 3
RESEARCH_MAX_CONCURRENT_MANUAL_RUNS       = 1
RESEARCH_ANOMALY_REJECTED_WINDOW_MIN      = 30
RESEARCH_ANOMALY_REJECTED_THRESHOLD       = 5
RESEARCH_ANOMALY_TOKEN_VIOLATION_THRESHOLD = 3
RESEARCH_ANOMALY_DUPLICATE_THRESHOLD       = 5
RESEARCH_ANOMALY_COST_SPIKE_MULTIPLIER     = 5.0
```

## 4. Order of gates (every gate runs **before** the provider call)

```
1.  RESEARCH_RO_ENABLED         (Phase B)
2.  RESEARCH_MANUAL_RUN_ENABLED (Phase E)
3.  operator_id non-empty
4.  triggered_by ∈ {manual, operator}
5.  request_source ∈ {cli, http}
6.  symbol regex                (Phase E)
7.  as_of ≤ today               (Phase E)
8.  provider ∈ RESEARCH_ALLOWED_PROVIDERS (Phase E)
9.  symbol allowlist if non-empty (Phase E)

—— Audit row written for every rejection from this point on ——

10. operator ∈ RESEARCH_ALLOWED_OPERATORS  (E.1)
11. asset row exists                       (Phase E)
12. SUM(cost_usd) today < RESEARCH_MAX_DAILY_COST_USD   (Phase E)
13. count(research_run today, sym) < RESEARCH_MAX_TICKER_DAILY_RUNS  (Phase E)
14. operator_runs_today  < RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY  (E.1)
15. symbol_runs_today    < RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY    (E.1)
16. concurrent_in_flight < RESEARCH_MAX_CONCURRENT_MANUAL_RUNS   (E.1)
17. detect_anomalies → flags attached to in-flight audit row
18. write_audit_in_flight (status='in_flight')

—— Provider call ——

19. orchestrator → research_run row + agent_output row + DB CHECK
20. write_audit_terminal: 'accepted' | 'rejected' | 'duplicate' | 'error'
```

Phase E.1 NEVER blocks based on anomaly flags. Flags are **visibility
only**. Real blocking happens via rate limits and cost caps.

## 5. Tests run safely

Test DB: `postgresql+psycopg://test:test@pg-11v-test:5432/test`
(safety guard refuses dev DB).

| Suite | Count | Result |
|-------|-------|--------|
| `test_research_phase_e_unit.py` (Phase E) | 15 | 15 passed |
| `test_research_phase_e_pg.py` (Phase E) | 10 | 10 passed |
| `test_research_phase_e1_unit.py` (E.1) | 12 | 12 passed |
| `test_research_phase_e1_pg.py` (E.1) | 11 | 11 passed |
| **Total** | **48** | **48 passed** |

### Spec → test mapping (E.1 required tests)

| Spec test | Implementation |
|-----------|----------------|
| test_operator_not_allowlisted_rejected_before_provider_call | integration ✓ |
| test_operator_allowlisted_can_run | integration ✓ |
| test_daily_operator_limit_blocks_provider_call | integration ✓ |
| test_symbol_daily_limit_blocks_provider_call | integration ✓ |
| test_concurrency_limit_blocks_second_run | integration ✓ |
| test_audit_log_written_for_success | integration ✓ |
| test_audit_log_written_for_rejection | integration ✓ |
| test_cli_uses_same_guard_path_as_http | integration ✓ |
| test_http_never_returns_raw_unsafe_output | integration ✓ |
| test_usage_summary_counts_runs_and_rejections | integration ✓ |
| test_anomaly_flags_repeated_rejections | integration ✓ |
| test_no_scheduler_entry_phase_e1 | unit ✓ |
| test_no_worker_registry_entry_phase_e1 | unit ✓ |
| test_no_execution_imports_phase_e1 | unit ✓ |
| test_no_reflection_feedback_phase_e1 | unit ✓ |

## 6. Commands run

```bash
# Files in test container
Get-Content <each phase-e1 file> -Raw | docker exec -i compose-api-1 sh -c 'cat > /app/<dest>'

# Unit
docker exec compose-api-1 sh -c \
  "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/unit/research/test_research_phase_e1_unit.py -v"

# Integration (isolated DB)
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c \
  "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/test_research_phase_e1_pg.py -v -m integration"

# Combined regression (E + E.1)
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c \
  "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/test_research_phase_e1_pg.py \
   apps/api/tests/integration/research/test_research_phase_e_pg.py \
   apps/api/tests/unit/research/test_research_phase_e_unit.py \
   apps/api/tests/unit/research/test_research_phase_e1_unit.py"
# → 48 passed
```

## 7. Proof: provider calls blocked before guard failures

`test_operator_not_allowlisted_rejected_before_provider_call` snapshots
`SELECT count(*) FROM research_ro.research_run` before and after a
rejected attempt. Delta is **0**. The audit table records the
rejection with `status='rejected'` and `rejection_reason` mentioning
'allowlist'.

Same pattern for:
- `test_daily_operator_limit_blocks_provider_call` — research_run
  count delta = 0 after second attempt.
- `test_symbol_daily_limit_blocks_provider_call` — research_run
  count delta = 0.
- `test_concurrency_limit_blocks_second_run` — research_run count
  delta = 0.

## 8. Proof: no scheduler/worker/execution path

| Verification | Result |
|---|---|
| `grep -rn "manual_run_controls\|manual_run_safe\|research_manual_run_audit" apps/worker/src/` | 0 hits |
| Worker registry has no Phase E.1 entry | confirmed by `test_no_worker_registry_entry_phase_e1` |
| Phase E.1 modules import no `domain.features.feature_engine`, `domain.recommendations.recommendation_engine`, `data.evaluation`, `domain.stock_engine.decision_engine`, `options.paper`, `domain.execution`, `langchain`, `langgraph` | confirmed by parametrized `test_no_execution_imports_phase_e1` (4 files × 8 forbidden tokens) |
| Reflection feedback edge | `test_no_reflection_feedback_phase_e1` greps every `.py` under `domain/features/`, `domain/recommendations/`, `data/evaluation/`, `worker/src/` for `research_reflection` and `research_manual_run_audit` — 0 hits |
| Sanitized payload (no raw provider body) | `test_http_never_returns_raw_unsafe_output` confirms no body/raw_*/structured_output/agent_output/evidence_refs/reflection field |

## 9. Rollback plan

Step | Effect
-----|-------
`RESEARCH_MANUAL_RUN_ENABLED=false` and restart api+worker | HTTP 404; CLI exits 2; gates short-circuit before any audit row is written
`RESEARCH_ALLOWED_OPERATORS=""` and restart | All operators rejected unless `RESEARCH_LOCAL_TEST_MODE=True` (local dev only)
Drop the audit table | `alembic downgrade 057_research_manual_audit` — runs `DROP TABLE`. No execution-table side effect.
Remove Phase E.1 modules | Delete `apps/api/src/research/manual_run_controls.py` + revert Phase E.1 edits in `manual_run_safe.py`. Phase E remains functional.
**No trading impact at any step. No scheduler impact at any step.** | —

After rollback verify:
```
curl -fsS -o /dev/null -w "%{http_code}\n" \
  -X POST http://127.0.0.1:8000/api/research/runs/manual
# expected: 404
```

## 10. Final safety verdict

| Property | Status |
|----------|--------|
| Operator allowlist enforced | ✅ |
| Rate limits enforced before provider call | ✅ (operator daily / symbol daily / concurrency) |
| Audit table written for accepted **and** rejected attempts | ✅ |
| Idempotency via `request_id` UNIQUE | ✅ |
| Usage tracking surface | ✅ (`usage_summary` helper) |
| Anomaly detection | ✅ (rule-based; no ML; no LLM) |
| HTTP rejection returns sanitized reason only | ✅ |
| HTTP/CLI share the same guard path | ✅ (both call `run_manual_safely`) |
| Default flags safe (everything OFF / empty allowlists) | ✅ |
| No scheduler entry / worker registry entry | ✅ |
| No execution-module imports | ✅ |
| No reflection feedback path | ✅ |
| No LangChain / LangGraph | ✅ |
| No filesystem memory | ✅ |
| No UI changes | ✅ |
| Trading / candidate / paper / options paths untouched | ✅ |
| **Verdict** | **SAFE** |

Phase E.1 ready. **48/48** tests pass. Default flags refuse every
manual run unless an operator is explicitly added to
`RESEARCH_ALLOWED_OPERATORS` (or `RESEARCH_LOCAL_TEST_MODE=True` for
local dev).
