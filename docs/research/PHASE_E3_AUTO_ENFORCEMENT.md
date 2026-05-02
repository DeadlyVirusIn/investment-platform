# Phase E.3 — Auto enforcement + cooldown

**Date:** 2026-05-01
**Branch:** `phase-1/ledger`
**Built on:** Phase E.2 (`3ec55de`) + Phase F (`97403cd`)
**Scope:** Make manual-run enforcement self-managing. **No automatic
research runs. No scheduler. No worker entry. No UI run button.**

---

## 1. Files changed

| File | Type |
|---|---|
| `infra/alembic/versions/059_research_operator_cooldown_history.py` | NEW migration (cooldown columns + history table) |
| `apps/api/src/config/__init__.py` | edit (+10 settings) |
| `apps/api/src/research/manual_run_auto_enforcement.py` | NEW (rule evaluator + state-apply + dedupe + auto-resolve) |
| `apps/api/src/research/manual_run_safe.py` | edit (auto-evaluation step before existing enforcement check) |
| `apps/api/src/api/research.py` | edit (operators payload exposes cooldown fields; new GET `/operators/{id}`) |
| `scripts/research_admin.py` | edit (+commands: show-operator, evaluate-operator, evaluate-all, restrict, watch, clear, resolve-alert) |
| `apps/api/tests/integration/research/test_research_phase_e3_pg.py` | NEW (29 tests) |
| `docs/research/PHASE_E3_AUTO_ENFORCEMENT.md` | NEW |

NOT changed: `apps/worker/src/`, `apps/api/src/data/features/`,
`apps/api/src/domain/recommendations/`, `apps/api/src/domain/stock_engine/`,
`scripts/run_paper_daily.py`, all paper/options paths,
`apps/web/src/components/research/*` (Phase F UI surfaces remain
unchanged; only the operators payload they consume gets new fields).

## 2. Database changes (migration 059)

```
ALTER TABLE research_ro.research_operator_control
  ADD COLUMN restricted_until        timestamptz,
  ADD COLUMN cooldown_reason         text,
  ADD COLUMN cooldown_source         text,         CHECK ∈ {auto, manual}
  ADD COLUMN last_auto_evaluation_at timestamptz,
  ADD COLUMN previous_state          text,
  ADD COLUMN state_changed_at        timestamptz;

CREATE TABLE research_ro.research_operator_control_history (
  id              uuid PK
  created_at      timestamptz
  operator_id     text NOT NULL
  previous_state  text
  new_state       text NOT NULL
  reason          text NOT NULL
  source          text NOT NULL  CHECK ∈ {auto, manual, override}
  cooldown_until  timestamptz
  alert_id        uuid → research_alert.id
  metadata        jsonb (sanitized at writer)
  CHECK new_state ∈ {clear, watch, restricted, blocked}
);
```

History table is append-only by design (no UPDATE path). Grants:
research_writer = INSERT/SELECT, research_reader = SELECT.

## 3. Config additions (defaults all safe)

```
RESEARCH_AUTO_ENFORCEMENT_ENABLED            = False
RESEARCH_ENFORCEMENT_LOOKBACK_HOURS          = 24
RESEARCH_WATCH_COOLDOWN_HOURS                = 24
RESEARCH_RESTRICTED_COOLDOWN_HOURS           = 24
RESEARCH_TOKEN_RESTRICTED_COOLDOWN_HOURS     = 72
RESEARCH_BLOCKED_COOLDOWN_HOURS              = 24
RESEARCH_ADMIN_OVERRIDE_WATCH_THRESHOLD      = 2
RESEARCH_ADMIN_OVERRIDE_RESTRICT_THRESHOLD   = 5
RESEARCH_ALERT_DEDUP_WINDOW_MIN              = 30
RESEARCH_ALERT_AUTO_RESOLVE_HOURS            = 24
```

When `RESEARCH_AUTO_ENFORCEMENT_ENABLED=False`:
- manual controls still work
- `evaluate_operator_state(dry_run=True)` returns the suggestion
- `apply_operator_state_transition` is NOT invoked from the manual run path
- Phase E.1 anomaly transitions remain independently active

## 4. Rule mapping (deterministic, rule-based)

### Escalation
| Signal in lookback window | → state | severity | cooldown |
|---|---|---|---|
| token_violation_count ≥ K | restricted | high | 72h |
| duplicate_count ≥ K | restricted | warning | 24h |
| rejected_count ≥ K | watch | warning | 24h |
| blocked_attempt_count ≥ 1 | blocked | critical | 24h |
| override_count ≥ RESTRICT_THRESHOLD | restricted | high | 24h |
| override_count ≥ WATCH_THRESHOLD | watch | warning | 24h |
| cost_spike_count ≥ 1 | watch | warning | 24h |

Highest priority wins; ties broken by `reason` lex order.

### Demotion (when cooldown expired)
| Current | Recent signals → next |
|---|---|
| blocked + expired | restricted (if token/cost spikes) else clear |
| restricted + expired | watch (if token/rejected/cost spikes) else clear |
| watch + no signals | clear |
| watch + signals | stays on watch |
| clear | stays clear |

`Recent` window = `RESEARCH_ENFORCEMENT_LOOKBACK_HOURS` (default 24h).

## 5. Order of gates (E.3 update)

```
1.  RESEARCH_RO_ENABLED
2.  RESEARCH_MANUAL_RUN_ENABLED
3.  Input validation
4.  Provider/symbol allowlists
5.  Operator allowlist
6.  touch_operator_last_seen
7.  ★ Phase E.3 auto-evaluation (if RESEARCH_AUTO_ENFORCEMENT_ENABLED)
    - evaluate_operator_state(dry_run=False)
    - apply_operator_state_transition if would_change
    - auto_resolve_stale_alerts
8.  Phase E.2 enforcement state check (reads UPDATED state)
    - clear/watch  → allow (watch logs)
    - restricted   → reject unless admin_override
    - blocked      → reject + alert
9.  Asset row exists / cost cap
10. Per-operator + per-symbol + concurrency limits
11. Phase E.1 anomaly detection + transitions (independent of E.3 flag)
12. write_audit_in_flight
13. Provider call
14. write_audit_terminal
```

The new step 7 runs BEFORE the provider import. Verified by 4 test
classes that snapshot `research_run` count before/after.

## 6. New API surface (still GET-only)

| Method | Path |
|---|---|
| GET | `/api/research/operators` (extended payload: cooldown_reason, cooldown_source, restricted_until, last_auto_evaluation_at, previous_state, state_changed_at) |
| GET | `/api/research/operators/{operator_id}` (NEW — single operator + last alert + open alert count) |

All other GET endpoints unchanged. **Zero new POST/PUT/PATCH/DELETE.**

## 7. CLI extensions

```
python -m scripts.research_admin --admin-id <id> show-operator --operator-id X
python -m scripts.research_admin --admin-id <id> evaluate-operator --operator-id X --dry-run
python -m scripts.research_admin --admin-id <id> evaluate-operator --operator-id X --apply
python -m scripts.research_admin --admin-id <id> evaluate-all --dry-run
python -m scripts.research_admin --admin-id <id> evaluate-all --apply
python -m scripts.research_admin --admin-id <id> restrict --operator-id X --hours 24 --reason ...
python -m scripts.research_admin --admin-id <id> watch    --operator-id X --hours 24 --reason ...
python -m scripts.research_admin --admin-id <id> clear    --operator-id X
python -m scripts.research_admin --admin-id <id> resolve-alert --alert-id UUID --reason ...
```

CLI rules (unchanged from E.2):
- `RESEARCH_MANUAL_RUN_ENABLED=true` required (else exit 3)
- admin-id required
- Manual changes write history (`source='manual'`)
- Auto evaluation writes history (`source='auto'`)
- No provider call
- No research run created

## 8. Tests

| Suite | Count | Result |
|-------|-------|--------|
| `test_research_phase_e3_pg.py` | 29 | 29 passed |
| **Combined regression** (E + E.1 + E.2 + F + E.3) | **112** | **112 passed** |

### Spec → test mapping (28 required + 1 extra)

| Spec | Implementation |
|---|---|
| repeated_rejections_auto_watch_24h | ✓ |
| duplicate_spam_auto_restricts_24h | ✓ |
| forbidden_tokens_auto_restricts_72h | ✓ (asserts cooldown_until ≈ 72h) |
| blocked_attempt_while_restricted_auto_blocks_24h | ✓ |
| repeated_admin_override_usage_watch | ✓ |
| repeated_admin_override_usage_restrict | ✓ |
| watch_expiry_returns_clear_without_recent_violations | ✓ |
| restricted_expiry_returns_watch_with_recent_warning | ✓ |
| restricted_expiry_returns_clear_without_recent_violations | ✓ |
| blocked_expiry_returns_restricted_with_recent_high | ✓ |
| blocked_expiry_returns_clear_without_recent_violations | ✓ |
| no_demotion_when_cooldown_not_expired | ✓ |
| alert_deduplication_window | ✓ |
| alert_auto_resolves_when_operator_clear | ✓ |
| alert_metadata_sanitizes_raw_output_keys | ✓ |
| alert_message_forbidden_tokens_blocked | ✓ |
| auto_enforcement_runs_before_provider_call | ✓ |
| blocked_operator_provider_call_count_zero | ✓ |
| restricted_operator_provider_call_count_zero | ✓ |
| watch_operator_allowed_and_audited | ✓ |
| auto_enforcement_disabled_dry_run_only | ✓ |
| cli_evaluate_all_no_provider_call | ✓ |
| cli_manual_state_change_writes_history | ✓ |
| no_scheduler_entry_phase_e3 | ✓ |
| no_worker_registry_entry_phase_e3 | ✓ |
| no_execution_imports_phase_e3 | ✓ |
| no_reflection_feedback_phase_e3 | ✓ |
| no_post_routes_added_phase_e3 | ✓ |
| no_post_from_ui_phase_e3 | ✓ |

## 9. Provider-call-before-enforcement proof

| Test | research_run delta |
|---|---|
| auto_enforcement_runs_before_provider_call | 0 (token_violation history → restricted → reject) |
| blocked_operator_provider_call_count_zero | 0 |
| restricted_operator_provider_call_count_zero | 0 |
| cli_evaluate_all_no_provider_call | 0 |

Implementation: the auto-evaluation step (`evaluate_operator_state`
+ `apply_operator_state_transition`) runs before the existing E.2
enforcement check, which itself runs before the provider import in
`run_single_asset_context_note`.

## 10. Proof: no scheduler/worker/execution

| Verification | Result |
|---|---|
| `grep -r "manual_run_auto_enforcement\|research_operator_control_history" apps/worker/src/` | 0 hits |
| Worker registry has no Phase E.3 entry | test passes |
| Phase E.3 modules import nothing from execution/scoring/ML/LangChain | test passes |
| `domain/features/`, `domain/recommendations/`, `data/evaluation/`, `worker/src/` reference no Phase E.3 symbols | test passes |
| No POST routes in `apps/api/src/api/research.py` | test passes |
| No `method: 'POST'` in research components | test passes |

## 11. Rollback

| Step | Effect |
|---|---|
| `RESEARCH_AUTO_ENFORCEMENT_ENABLED=false` + restart | auto-evaluation step skipped; manual + Phase E.1/E.2 paths unchanged |
| `RESEARCH_MANUAL_RUN_ENABLED=false` (emergency) | CLI exits 3; HTTP route 404; no manual runs at all |
| `alembic downgrade 058_research_alerts` | drops cooldown columns + history table; preserves alerts/operator_control |
| **No trading impact at any step.** | — |
| **No scheduler impact at any step.** | — |

After rollback verify:
```
docker exec compose-api-1 python -c \
 "from apps.api.src.config import settings; \
  print('auto:', settings.RESEARCH_AUTO_ENFORCEMENT_ENABLED, \
        'manual:', settings.RESEARCH_MANUAL_RUN_ENABLED)"
# auto: False  manual: False
```

## 12. Final safety verdict

| Property | Status |
|----------|--------|
| Auto-evaluation runs BEFORE provider call | ✅ |
| Cooldown durations enforced per transition target | ✅ |
| Demotion only when cooldown expired | ✅ |
| Alert dedup window honored | ✅ |
| Auto-resolve only when operator state = clear | ✅ |
| Alert metadata sanitized recursively | ✅ |
| Alert `message` DB CHECK rejects forbidden tokens | ✅ |
| GET-only API surface (no new POST/PUT/PATCH/DELETE) | ✅ |
| CLI gated by `RESEARCH_MANUAL_RUN_ENABLED` + admin-id | ✅ |
| History table append-only (no UPDATE path in writer) | ✅ |
| Default `RESEARCH_AUTO_ENFORCEMENT_ENABLED=false` | ✅ |
| No scheduler entry / worker entry / execution imports | ✅ |
| No reflection feedback (history doesn't feed back into prompts) | ✅ |
| Trading / candidate / paper / options / ML paths untouched | ✅ |
| **Verdict** | **SAFE** |

Phase E.3 ready. **29/29** new + **112/112** combined regression
tests pass. Default flag keeps auto-enforcement quiet until an
operator explicitly enables it. Rollback = single env flag.
