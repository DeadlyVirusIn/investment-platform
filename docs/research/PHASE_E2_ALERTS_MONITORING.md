# Phase E.2 — Alerts + Monitoring + Anomaly Enforcement

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase F (`97403cd`) + Phase E.1
**Scope:** Operational monitoring + enforcement on top of Phase E.1.
**No UI run button. No POST. No scheduler. No worker entry.**

---

## 1. Files changed

| File | Type |
|------|------|
| `infra/alembic/versions/058_research_alerts_operator_control.py` | NEW migration (2 tables, CHECK + grants) |
| `apps/api/src/research/manual_run_enforcement.py` | NEW (operator state + alert helpers + anomaly→state mapping) |
| `apps/api/src/research/manual_run_safe.py` | edit (enforcement check before provider; alert on rejection; admin_override; anomaly→state escalation) |
| `apps/api/src/api/research.py` | edit (+3 GET endpoints: `/alerts`, `/operators`, `/usage/summary`) |
| `scripts/research_admin.py` | NEW CLI (`block`/`unblock`/`set-state`/`list-alerts`/`list-operators`) |
| `apps/web/src/components/research/ResearchJobHealthCard.tsx` | edit (read `/usage/summary` instead of `/usage`; render alerts + operator counts; FreshnessBadge for last alert) |
| `apps/api/tests/integration/research/test_research_phase_e2_pg.py` | NEW (18 integration tests covering all 18 spec requirements) |
| `docs/research/PHASE_E2_ALERTS_MONITORING.md` | NEW |

NOT changed: `apps/worker/src/`, `apps/api/src/data/features/`,
`apps/api/src/domain/recommendations/`, `apps/api/src/domain/stock_engine/`,
`scripts/run_paper_daily.py`, Phase E orchestrator,
the existing GET endpoints from Phase F.

## 2. Tables added

```
research_ro.research_operator_control
  operator_id     text PK
  state           text CHECK ∈ {clear, watch, restricted, blocked}
  reason          text
  first_seen_at   timestamptz
  last_seen_at    timestamptz
  blocked_until   timestamptz
  updated_by      text
  updated_at      timestamptz
  notes           text
  Index: ix_operator_control_state

research_ro.research_alert
  id              uuid PK
  created_at      timestamptz
  severity        text CHECK ∈ {info, warning, high, critical}
  alert_type      text
  operator_id     text
  symbol          text
  message         text  ck_alert_message_no_action_tokens (forbidden-token regex)
  status          text CHECK ∈ {open, acknowledged, resolved}
  metadata        jsonb (default '{}')
  acknowledged_by text
  acknowledged_at timestamptz
  Indexes: by created, severity+status, operator+created

  Grants: research_writer = INSERT/SELECT/UPDATE
          research_reader = SELECT
```

## 3. New API endpoints (GET-only)

| Method | Path |
|---|---|
| GET | `/api/research/alerts` (filter: severity, status, operator_id, limit) |
| GET | `/api/research/operators` |
| GET | `/api/research/usage/summary` (audit_today + alerts + operators rollup) |

All other Phase F GET endpoints unchanged. **Zero new POST/PUT/PATCH/DELETE.** Verified by `test_alerts_api_get_only`, `test_operators_api_get_only`, `test_usage_summary_api_get_only`.

## 4. CLI admin

```
python -m scripts.research_admin --admin-id <id> block <op> --reason TEXT [--blocked-until ISO]
python -m scripts.research_admin --admin-id <id> unblock <op>
python -m scripts.research_admin --admin-id <id> set-state <op> <clear|watch|restricted|blocked> --reason TEXT
python -m scripts.research_admin --admin-id <id> list-alerts [--severity ...] [--limit N]
python -m scripts.research_admin --admin-id <id> list-operators
```

Refuses unless `RESEARCH_MANUAL_RUN_ENABLED=true`. Every admin
action emits an `info`-severity alert tagged `admin.<command>` for
audit trail.

## 5. Enforcement state machine

```
clear ──anomaly→ watch ──anomaly→ restricted ──anomaly→ blocked
                                                       (ttl=blocked_until)

clear      : allow
watch      : allow + audit warning
restricted : reject UNLESS admin_override=True (which itself emits an alert)
blocked    : reject (auto-expires when blocked_until passes; transitions to watch)
```

State escalates only — never downgrades automatically. Operator
admin must explicitly `unblock` / `set-state clear` to clear.

## 6. Anomaly → state mapping (deterministic, rule-based)

| Anomaly flag | Target state | Severity | Alert type |
|---|---|---|---|
| `operator_repeated_token_violations:N>=K` | restricted | high | `forbidden_token_threshold_exceeded` |
| `operator_repeated_rejections:N>=K` | watch | warning | `repeated_rejections` |
| `operator_symbol_duplicate_spam:N>=K` | restricted | warning | `duplicate_spam` |
| `cost_spike:est=$X>=Yx_run_cap` | watch | warning | `cost_spike` |

Multiple flags trip → highest target state wins; one alert per flag.

## 7. Order of gates (Phase E.2 update)

```
1.  RESEARCH_RO_ENABLED         (Phase B)
2.  RESEARCH_MANUAL_RUN_ENABLED (Phase E)
3.  Input validation             (Phase E)
4.  Provider/symbol allowlists   (Phase E)
5.  Operator allowlist           (Phase E.1)
6.  ★ Operator enforcement state (Phase E.2) — touch_last_seen + evaluate
    - clear/watch  → allow (watch logs warning)
    - restricted   → reject unless admin_override=True
    - blocked      → reject (alert emitted)
7.  Asset row exists             (Phase E)
8.  Cost cap                     (Phase E)
9.  Per-operator + per-symbol + concurrency limits (Phase E.1)
10. ★ detect_anomalies + apply_anomaly_transitions (Phase E.2)
    - escalates state, emits alerts
11. write_audit_in_flight
12. Provider call
13. write_audit_terminal
```

Steps 6 + 10 are new. Both run BEFORE the provider call.

## 8. Tests

| Suite | Count | Result |
|-------|-------|--------|
| `test_research_phase_e2_pg.py` | 18 | 18 passed |
| **Combined regression** (E + E.1 + F + E.2) | **83** | **83 passed** |

### Spec → test mapping (18 required)

| # | Spec | Implementation |
|---|------|----------------|
| 1 | repeated_rejections_create_alert | ✓ |
| 2 | forbidden_token_threshold_creates_high_alert | ✓ |
| 3 | duplicate_spam_creates_alert | ✓ |
| 4 | cost_spike_creates_warning | ✓ |
| 5 | blocked_operator_rejected_before_provider_call | ✓ |
| 6 | restricted_operator_rejected_without_override | ✓ |
| 7 | watch_operator_allowed_with_warning_audit | ✓ |
| 8 | operator_control_manual_override_logged | ✓ |
| 9 | alert_metadata_contains_no_raw_output | ✓ |
| 10 | alerts_api_get_only | ✓ |
| 11 | operators_api_get_only | ✓ |
| 12 | usage_summary_api_get_only | ✓ |
| 13 | job_health_reads_alerts_get_only | ✓ |
| 14 | no_post_from_ui_phase_e2 | ✓ |
| 15 | no_scheduler_entry_phase_e2 | ✓ |
| 16 | no_worker_registry_entry_phase_e2 | ✓ |
| 17 | no_execution_imports_phase_e2 | ✓ |
| 18 | no_reflection_feedback_phase_e2 | ✓ |

## 9. Commands run

```bash
# Phase E.2 only
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/test_research_phase_e2_pg.py -v"
# → 18 passed

# Full regression (E + E.1 + F + E.2)
docker exec -e TEST_DATABASE_URL="postgresql+psycopg://test:test@pg-11v-test:5432/test" \
  compose-api-1 sh -c "cd /app && PYTHONPATH=/app python -m pytest \
   apps/api/tests/integration/research/ \
   apps/api/tests/unit/research/test_research_phase_e_unit.py \
   apps/api/tests/unit/research/test_research_phase_e1_unit.py \
   apps/api/tests/unit/research/test_research_phase_f_static.py"
# → 83 passed
```

## 10. Proof: enforcement happens before provider call

| Test | research_run delta | alert recorded | research_run absent |
|---|---|---|---|
| Blocked operator | 0 | enforcement_rejection | ✓ |
| Restricted (no override) | 0 | enforcement_rejection | ✓ |
| Restricted + override=True | 1 | admin_override_used | run completed |
| Watch state | 1 | (no rejection) | run completed; logger.warning emitted |

Implementation: `evaluate_enforcement` runs BEFORE the in-flight
audit row is written and BEFORE the provider import. Live trace
shows `apps.api.src.research.manual_run.run_single_asset_context_note`
is never imported on the rejection path.

## 11. Proof: no scheduler/worker/execution path

| Verification | Result |
|---|---|
| `grep -r "manual_run_enforcement\|research_alert\|research_operator_control\|research_admin" apps/worker/src/` | 0 hits (test 15) |
| Worker registry has no Phase E.2 entry | test 16 |
| Phase E.2 modules import nothing from execution/scoring/ML | test 17 |
| `domain/features/`, `domain/recommendations/`, `data/evaluation/`, `worker/src/` reference no `research_alert` / `research_operator_control` / `research_reflection` | test 18 |
| No `method: 'POST'` in `apps/web/src/components/research/` | test 14 |
| Alert metadata stripped of `body`/`raw_body`/`structured_output`/`evidence_refs`/`reflection` keys | test 9 (live insertion + read-back) |

## 12. Rollback

| Step | Effect |
|---|---|
| `RESEARCH_MANUAL_RUN_ENABLED=false` + restart | CLI refuses (exit 3); HTTP route returns 404; existing audit/alert rows preserved |
| Keep `RESEARCH_RO_ENABLED=true` | Phase F read-only UI remains; alerts + operators endpoints still respond |
| `alembic downgrade 058_research_alerts` | drops alert + operator_control tables; Phase E.1 audit table unchanged |
| Remove Phase E.2 modules | revert `manual_run_safe.py` enforcement-check insertion + delete `manual_run_enforcement.py` + delete `research_admin.py` |
| **No trading impact at any step.** | — |
| **No scheduler impact at any step.** | — |

## 13. Final safety verdict

| Property | Status |
|----------|--------|
| Operator state checked BEFORE provider call | ✅ |
| Blocked operator → reject + alert | ✅ |
| Restricted operator → reject unless admin_override (and override emits its own alert) | ✅ |
| Watch operator → allow + log + audit warning | ✅ |
| Anomaly flags escalate state (rule-based, deterministic) | ✅ |
| Alerts emitted for: repeated rejections / token threshold / duplicate spam / cost spike / enforcement rejection / admin override | ✅ |
| Alert message DB CHECK rejects forbidden tokens | ✅ |
| Alert metadata sanitized in writer (`emit_alert` strips body/raw/structured/evidence/reflection keys) | ✅ |
| GET-only API surface (no POST anywhere under `/api/research/`) | ✅ |
| CLI admin gated by `RESEARCH_MANUAL_RUN_ENABLED` + admin id required | ✅ |
| JobHealth UI extension is read-only; no action buttons; uses neutral coloring | ✅ |
| No scheduler / no worker registry / no execution imports / no reflection feedback | ✅ |
| Trading / candidate / paper / options / ML paths untouched | ✅ |
| **Verdict** | **SAFE** |

Phase E.2 ready. **18/18** new + **83/83** combined regression
tests pass. Default flags keep enforcement quiet until an operator
explicitly enables manual runs and at least one anomaly fires or
admin issues a state-change command.
