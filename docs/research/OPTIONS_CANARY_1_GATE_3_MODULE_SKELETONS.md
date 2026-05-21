# Canary-1 — Gate 3: Module Skeletons (Interface-Contract Review)

**Date**: 2026-05-19
**Status**: REVIEW ONLY — no code authored, no logic, no DB writes, no
flag flips, no migration apply
**Predecessor**: `OPTIONS_CANARY_1_EXECUTION_PLAN.md` (rev 1) + migration
`090_options_canary_lifecycle_run.py` (approved, not applied)

This document specifies the interface contracts of the three new modules
before any business logic exists. The goal is to harden module boundaries,
return shapes, telemetry semantics, and append-only guarantees while the
cost of changing them is still zero.

---

## 1. Module boundary diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                       apps/worker/src/jobs/                        │
│                                                                    │
│   options_canary_proposal.py        options_canary_lifecycle.py    │
│   ─────────────────────────────     ─────────────────────────────  │
│   scheduler entrypoint              scheduler entrypoint           │
│   run_options_canary_proposal_job   run_options_canary_lifecycle_  │
│                                       job                          │
│           │                                  │                     │
│           └──────────────┬───────────────────┘                     │
│                          │ depends on                              │
└──────────────────────────┼─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│                  apps/api/src/options/canary/                      │
│                                                                    │
│   engine.py                                                        │
│   ───────────────────────────────────────────────────────────────  │
│   - preflight()                                                    │
│   - run_proposal_cycle()                                           │
│   - run_lifecycle_cycle()                                          │
│   - _select_candidate_contract()         [LOGIC STUB]              │
│   - _execute_fill()                      [LOGIC STUB]              │
│   - _evaluate_exit_triggers()            [LOGIC STUB]              │
│   - _reconcile_close_accounting()        [LOGIC STUB]              │
│   - _append_lifecycle_event()            [WRITE GATEWAY]           │
│   - _write_canary_telemetry()            [WRITE GATEWAY]           │
│                                                                    │
│   operator_event.py        [OUT OF GATE 3 — referenced only]       │
│   ───────────────────────────────────────────────────────────────  │
│   - record_operator_pause()                                        │
│   - record_operator_close()                                        │
│   NOT IMPORTABLE FROM apps/worker/src/jobs/*                       │
│   (CI lint enforces; see §11)                                      │
└────────────────────────────────────────────────────────────────────┘
                           ▲
                           │ reads-only
┌──────────────────────────┴─────────────────────────────────────────┐
│   read-only dependencies of engine.py                              │
│   - apps/api/src/config (settings)                                 │
│   - apps/api/src/db (SessionLocal)                                 │
│   - apps/api/src/options/data/chain_ingest (snapshot reader only)  │
│   - apps/api/src/options/data_provider (NO: never re-fetches;      │
│                                          uses persisted snapshots) │
└────────────────────────────────────────────────────────────────────┘
```

**Direction rule**: `apps/worker/` may import from `apps/api/`. The reverse
is forbidden (existing CI lint already enforces). The two worker job
modules MUST NOT import each other.

---

## 2. Dependency graph

```
tick_loop ──► options_canary_proposal.run_options_canary_proposal_job()
              └──► engine.preflight(now)
              └──► engine.run_proposal_cycle(now)
                   ├──► engine._select_candidate_contract()   [stub]
                   ├──► engine._append_lifecycle_event(PROPOSED)
                   └──► engine._write_canary_telemetry(...)

tick_loop ──► options_canary_lifecycle.run_options_canary_lifecycle_job()
              └──► engine.preflight(now)
              └──► engine.run_lifecycle_cycle(now)
                   ├──► engine._execute_fill()                [stub]
                   │    ├──► engine._append_lifecycle_event(OPENED)
                   │    └──► (writes options_paper_position, portfolio
                   │           ledger — explicit list in §10)
                   ├──► engine._evaluate_exit_triggers()      [stub]
                   │    └──► engine._append_lifecycle_event(MONITORED)
                   ├──► (on trigger) engine._reconcile_close_accounting()
                   │    └──► engine._append_lifecycle_event(CLOSED)
                   └──► engine._write_canary_telemetry(...)
```

Two and only two scheduler entrypoints. Both must register in
`apps/worker/src/jobs/registry.py` (registration itself is a Gate-4
concern, not authored here).

---

## 3. Pre-flight contract

`engine.preflight(now: datetime) -> PreflightResult`

Returns a structured dataclass. Caller maps to wrapper-RC.

```python
@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    kind: Literal[
        "ok",
        "drift",                  # md5 mismatch
        "schema_drift",           # alembic head mismatch
        "chain_stale",            # last chain ingest too old
        "portfolio_paused",       # canary portfolio.active == False
        "exception",              # preflight itself crashed
    ]
    failed_check: str | None      # e.g. "md5:options_chain_snapshot.py:tickloop"
    details: dict                 # structured, JSONB-safe
```

Check order (fail-fast):

| Step | Check | Result on fail |
|---|---|---|
| 1 | md5 parity (8 files × 2 worker containers)   | `kind="drift"`, maps to F6_deployment_drift |
| 2 | Alembic head matches host                    | `kind="schema_drift"`, maps to F6_deployment_drift |
| 3 | Canary portfolio `active == True`            | `kind="portfolio_paused"`, maps to classification="paused" (no F-code) |
| 4 | Latest `options_chain_ingest_run.classification == 'success'` AND `started_at > now - 90 min` | `kind="chain_stale"`, maps to F1_stale_chain |

Telemetry: preflight does **not** write its own telemetry row. The caller
writes one telemetry row at the end of the cycle, embedding the preflight
result in `error_summary` when relevant. One row per invocation, always.

Idempotency: preflight is pure read-only. Safe to call any number of times.

---

## 4. Wrapper-RC return contract (shared)

All scheduler entrypoints return a single dict matching D2.3:

```python
WrapperResult = TypedDict("WrapperResult", {
    "return_code":    NotRequired[int],     # 0 success, !=0 error
    "skipped":        NotRequired[bool],    # True = no substantive work
    "reason":         NotRequired[str],     # closed enum, see §6 / §7
    "classification": NotRequired[str],     # echo of telemetry classification
    "detail":         NotRequired[dict],    # structured payload
}, total=False)
```

Tick_loop classification (already verified in D2.3):

```
{skipped: True}        → job_run.status = "skipped"
{return_code: !=0}     → job_run.status = "error"
otherwise              → job_run.status = "success"
```

Cross-cutting invariant: **every** scheduler entrypoint writes exactly one
telemetry row to `options_canary_lifecycle_run` before returning, via
`engine._write_canary_telemetry()`. No early return may skip the write.
Implementation pattern: outer `try/finally` in the cycle function.

---

## 5. `apps/api/src/options/canary/engine.py`

### 5.1 `preflight(now)`

Defined in §3.

### 5.2 `run_proposal_cycle(now)`

```python
def run_proposal_cycle(now: datetime) -> WrapperResult:
```

**Inputs**: `now` (UTC). All time-derived decisions use this single anchor.

**Outputs**: `WrapperResult` per §4.

**Failure enums it can return** (closed):

| reason | classification | failure_code |
|---|---|---|
| `preflight_failed:drift`             | error             | F6_deployment_drift |
| `preflight_failed:schema_drift`      | error             | F6_deployment_drift |
| `preflight_failed:chain_stale`       | error             | F1_stale_chain |
| `canary_paused`                      | paused            | NULL |
| `canary_at_capacity`                 | no_op             | NULL |
| `canary_complete`                    | no_op             | NULL |
| `proposal_exists_today`              | no_op             | NULL |
| `no_signal_today`                    | no_op             | NULL |
| `pricing_invalid:<sub>`              | error             | F3_pricing_invalid |
| `exception:<ExcType>`                | error             | F1_stale_chain (if anchor-related) / mapped per type |
| (success path)                       | success           | NULL |

**Telemetry behavior**: exactly one row to `options_canary_lifecycle_run`
on EVERY path (success / skip / error). `job_name='canary_proposal'`,
`portfolio_id='canary-spy-v1'`.

**Lifecycle-event writes**:
- On success: exactly one `PROPOSED` event via `_append_lifecycle_event()`
- On any non-success path: zero lifecycle events

**Idempotency**:
- Same-day re-invocation: returns `proposal_exists_today` if a PROPOSED
  event exists for today.
- One-shot guarantee: returns `canary_complete` if any CLOSED event exists
  for canary portfolio.

**Append-only guarantee**: this function NEVER updates or deletes any
table. Only INSERTs: `options_paper_trade` (PROPOSED row),
`options_trade_lifecycle_event`, `options_canary_lifecycle_run`.

### 5.3 `run_lifecycle_cycle(now)`

```python
def run_lifecycle_cycle(now: datetime) -> WrapperResult:
```

**Inputs**: `now` (UTC).

**Outputs**: `WrapperResult` per §4.

**Failure enums it can return** (closed):

| reason | classification | failure_code |
|---|---|---|
| `preflight_failed:drift`            | error    | F6_deployment_drift |
| `preflight_failed:schema_drift`     | error    | F6_deployment_drift |
| `preflight_failed:chain_stale`      | error    | F1_stale_chain |
| `canary_paused`                     | paused   | NULL |
| `no_open_position`                  | no_op    | NULL |
| `no_fill_yet`                       | no_op    | NULL    (proposal exists, awaiting fill window) |
| `proposal_expired`                  | no_op    | NULL    (writes PROPOSAL_EXPIRED event before returning) |
| `stale_chain`                       | error    | F1_stale_chain |
| `pricing_invalid:<sub>`             | error    | F3_pricing_invalid |
| `lifecycle_stall`                   | error    | F4_lifecycle_stall |
| `expiry_edge`                       | error    | F5_expiry_edge |
| `exception:<ExcType>`               | error    | per-type mapping |
| `monitored`                         | success  | NULL    (wrote MONITORED event) |
| `filled`                            | success  | NULL    (wrote OPENED event) |
| `closed:<exit_reason>`              | success  | NULL    (wrote CLOSED event) |

**Telemetry behavior**: exactly one row per invocation, always.
`job_name='canary_lifecycle'`.

**Lifecycle-event writes per cycle** (at most one of each per call):
- `OPENED` (on fill execution)
- `MONITORED` (on monitor tick when min-interval satisfied; see idempotency)
- `CLOSED` (on exit trigger)
- `PROPOSAL_EXPIRED` (on proposal aging out without fill)

**Idempotency**:
- Fill: at-most-once. Skipped if any `OPENED` event exists for the trade.
- Monitor: rate-limited. Skipped if last `MONITORED` event for the trade
  was within `MONITOR_MIN_INTERVAL_SECONDS = 60`. (Avoids double-writes
  on tight scheduler firing.)
- Close: at-most-once. Skipped if any `CLOSED` event exists for the trade.

**Append-only guarantee for events**: yes. State mutation on
`options_paper_position` and `options_paper_trade` is NOT append-only
(see §10).

### 5.4 `_select_candidate_contract()` — LOGIC STUB

```python
def _select_candidate_contract(
    now: datetime,
    underlying_spot: Decimal,
) -> ContractCandidate | None:
```

**Gate 3 contract**: signature only. Returns `None` for now (no
candidates). When implemented at Gate 4+, will pick the SPY ATM call per
the strategy rule. Failure to select returns `None` (caller maps to
`no_signal_today` or `pricing_invalid:<sub>`).

**No DB writes**.

### 5.5 `_execute_fill()` — LOGIC STUB

```python
def _execute_fill(
    trade_id: int,
    chain_row: ChainSnapshotRow,
    now: datetime,
) -> FillResult:
```

**Gate 3 contract**: signature only. Will validate quote gates,
compute fill price, write `OPENED` event, insert `options_paper_position`,
append portfolio ledger entry.

**Failure surface**: returns `FillResult.ok=False` with one of
{`stale_chain`, `pricing_invalid:<sub>`, `no_fill`}. Caller maps to
wrapper-RC.

**Append-only events**: yes. **Position INSERT**: yes (one row).
**Portfolio ledger INSERT**: yes (one row).

### 5.6 `_evaluate_exit_triggers()` — LOGIC STUB

```python
def _evaluate_exit_triggers(
    position: PaperPosition,
    chain_row: ChainSnapshotRow,
    now: datetime,
) -> ExitDecision:
```

**Gate 3 contract**: signature only. Returns one of:
- `ExitDecision(hold=True)`
- `ExitDecision(hold=False, reason: Literal["tp_hit","sl_hit","max_hold","expiry_guard"])`

**No DB writes**. Pure function.

### 5.7 `_reconcile_close_accounting()` — LOGIC STUB

```python
def _reconcile_close_accounting(
    position: PaperPosition,
    exit_chain_row: ChainSnapshotRow,
    exit_reason: str,
    now: datetime,
) -> CloseResult:
```

**Gate 3 contract**: signature only. Will compute exit credit, commission,
realized P&L, write CLOSED event, update position status, append ledger
entry. Asserts cash invariant `final_cash == initial_cash + realized_pnl`
to 4 decimal places before returning.

**Append-only events**: yes. **Position UPDATE**: yes (status, exit fields
— see §10). **Portfolio ledger INSERT**: yes.

### 5.8 `_append_lifecycle_event()` — WRITE GATEWAY

```python
def _append_lifecycle_event(
    session: Session,
    *,
    trade_id: int,
    event: Literal[
        "PROPOSED","PROPOSAL_EXPIRED","OPENED","MONITORED","CLOSED",
        "MANUAL_OPERATOR_PAUSE","MANUAL_OPERATOR_CLOSE",
    ],
    event_ts: datetime,
    payload: dict,
) -> int:                                  # returns new event_id
```

**Sole legal surface for writing `options_trade_lifecycle_event` rows.**
Direct SQL INSERTs into this table elsewhere are a CI lint violation
(see §11).

**Append-only guarantee**: this function only INSERTs. There is no
sibling `_update_lifecycle_event` or `_delete_lifecycle_event` in this
module or anywhere else.

**No telemetry write**. Telemetry is written by the cycle function, not
by event writes.

### 5.9 `_write_canary_telemetry()` — WRITE GATEWAY

```python
def _write_canary_telemetry(
    *,
    started_at: datetime,
    finished_at: datetime,
    job_name: Literal["canary_proposal","canary_lifecycle"],
    classification: Literal["success","no_op","paused","error","operator_action"],
    failure_code: str | None = None,
    counts: dict,                          # n_proposals_generated, n_fills_executed, ...
    error_summary: dict | None = None,
    operator_fields: dict | None = None,   # only when classification=='operator_action'
) -> None:
```

**Sole legal surface for writing `options_canary_lifecycle_run` rows.**
Direct SQL elsewhere is a CI lint violation.

**Never raises.** Telemetry write failure is logged at WARN; the calling
cycle still returns its real outcome. Mirror of the chain-ingest telemetry
writer pattern.

---

## 6. `apps/worker/src/jobs/options_canary_proposal.py`

```python
async def run_options_canary_proposal_job() -> dict[str, Any]:
    """Scheduler entrypoint. Wraps engine.run_proposal_cycle(now)."""
```

**Inputs**: none (`now` is computed inside).

**Outputs**: `WrapperResult` (see §4).

**Failure enums**: full set from §5.2.

**Telemetry behavior**: delegates to engine; one row per invocation
guaranteed.

**Idempotency**: same-day rerun returns `proposal_exists_today`.

**Append-only guarantee**: no direct DB writes in this module. All writes
go through engine. CI lint enforces (see §11).

**Master flag gate** (first executable line of the function):

```
if not settings.OPTIONS_ENABLED and not settings.OPTIONS_CANARY_ENABLED:
    write telemetry classification="paused", reason="master_flags_off"
    return {"skipped": True, "reason": "master_flags_off"}
```

This mirrors the chain-snapshot wrapper pattern and means the job is
safely registered at Gate 4 without firing until Gate 5+ flips the flags.

---

## 7. `apps/worker/src/jobs/options_canary_lifecycle.py`

```python
async def run_options_canary_lifecycle_job() -> dict[str, Any]:
    """Scheduler entrypoint. Wraps engine.run_lifecycle_cycle(now)."""
```

**Inputs**: none.

**Outputs**: `WrapperResult` (see §4).

**Failure enums**: full set from §5.3.

**Telemetry behavior**: delegates to engine; one row per invocation
guaranteed.

**Idempotency**: rate-limited per `MONITOR_MIN_INTERVAL_SECONDS=60`.
Re-invocations within 60s of the last MONITORED event for an open position
return `monitored` with `detail={"rate_limited": true}` but write no
event. Telemetry still records the invocation.

**Append-only guarantee for events**: yes. **Position/trade state
mutation**: through engine only (see §10 mutability matrix).

**Master flag gate**: identical pattern to §6.

---

## 8. Telemetry write points — exhaustive table

| Caller | Path | Telemetry rows |
|---|---|---|
| `options_canary_proposal` (scheduler)    | success: proposal generated      | 1 row, classification=success |
| `options_canary_proposal` (scheduler)    | preflight failed                 | 1 row, classification=error, failure_code set |
| `options_canary_proposal` (scheduler)    | flag off / paused / no-op        | 1 row, classification=paused or no_op |
| `options_canary_proposal` (scheduler)    | exception                        | 1 row, classification=error, failure_code mapped |
| `options_canary_lifecycle` (scheduler)   | fill executed                    | 1 row, classification=success, n_fills_executed=1 |
| `options_canary_lifecycle` (scheduler)   | monitor written                  | 1 row, classification=success, n_monitors_written=1 |
| `options_canary_lifecycle` (scheduler)   | exit executed                    | 1 row, classification=success, n_exits_executed=1 |
| `options_canary_lifecycle` (scheduler)   | preflight / stall / pricing fail | 1 row, classification=error, failure_code set |
| `options_canary_lifecycle` (scheduler)   | no open position                 | 1 row, classification=no_op |
| `operator_event.record_operator_*`       | operator action                  | 1 row, classification=operator_action |

**Invariant**: per scheduler invocation, exactly one row. Per operator
action, exactly one row. Never zero, never two.

---

## 9. Lifecycle-event write points — exhaustive table

| Event | Written by | Trigger | Sequence guarantee |
|---|---|---|---|
| `PROPOSED`              | engine.run_proposal_cycle    | candidate selected, gates passed                | first event for a trade_id |
| `PROPOSAL_EXPIRED`      | engine.run_lifecycle_cycle   | proposal aged out without OPENED                | terminal for that trade_id (no OPENED follows) |
| `OPENED`                | engine._execute_fill         | quote gates passed at T1                        | exactly one per trade_id; must follow PROPOSED |
| `MONITORED`             | engine._evaluate_exit_triggers | rate-limit satisfied, position OPEN           | many per trade_id; must follow OPENED, precede CLOSED |
| `CLOSED`                | engine._reconcile_close_accounting | exit trigger fired                        | exactly one per trade_id; terminal |
| `MANUAL_OPERATOR_PAUSE` | operator_event.record_operator_pause | operator CLI                           | any number; never terminal |
| `MANUAL_OPERATOR_CLOSE` | operator_event.record_operator_close | operator CLI                           | exactly one if used; terminal alternative to automated CLOSED |

**Append-only guarantee**: all events are INSERT-only. No code path in
this gate's scope updates or deletes a lifecycle event.

---

## 10. Mutability matrix

To prevent reviewer surprise: not every canary table is append-only. The
**audit trail** (lifecycle events + telemetry) is append-only. The
**state machine** rows (trade + position) mutate.

| Table | Append-only? | Allowed operations | Rationale |
|---|---|---|---|
| `options_trade_lifecycle_event`   | ✅ yes | INSERT only | audit trail; never rewrite history |
| `options_canary_lifecycle_run`    | ✅ yes | INSERT only | telemetry; never rewrite history |
| `options_paper_trade`             | ❌ no  | INSERT, UPDATE (status field: PROPOSED→OPEN→CLOSED) | state machine; events table is the audit trail |
| `options_paper_position`          | ❌ no  | INSERT, UPDATE (status, exit_*, realized_pnl) | state machine; events table is the audit trail |
| portfolio ledger                  | ✅ yes | INSERT only | balance = SUM(entries) |
| `options_chain_snapshot`          | ✅ yes | INSERT only (existing) | quote history |

The state-machine tables ARE allowed to mutate. The events table is the
authoritative history. Reconstructing position state from the event chain
must always be possible — that's the integrity invariant.

---

## 11. CI lint additions required at Gate 4

(Not authored here; specified for review.)

| Lint rule | Enforces | Mechanism |
|---|---|---|
| **No worker→worker imports**                  | jobs don't import each other        | grep AST: `apps/worker/src/jobs/options_canary_*` imports forbidden from peer |
| **No api→worker imports**                     | direction discipline                | existing lint extended |
| **No `INSERT INTO options_trade_lifecycle_event` outside `engine._append_lifecycle_event`** | single write gateway | grep + AST whitelist |
| **No `INSERT INTO options_canary_lifecycle_run` outside `engine._write_canary_telemetry`** | single write gateway | grep + AST whitelist |
| **`operator_event` not importable from `apps/worker/src/jobs/*`** | escape-hatch is operator-only | grep import statements |
| **No `UPDATE options_trade_lifecycle_event`** anywhere | append-only audit trail | grep |
| **No `DELETE FROM options_trade_lifecycle_event`** anywhere | append-only audit trail | grep |
| **No `UPDATE options_canary_lifecycle_run`** anywhere | append-only telemetry | grep |
| **No `DELETE FROM options_canary_lifecycle_run`** anywhere | append-only telemetry | grep |

---

## 12. Failure-enum cross-reference (closed sets)

**Wrapper-RC `reason` values** — proposal job:
```
master_flags_off
preflight_failed:drift
preflight_failed:schema_drift
preflight_failed:chain_stale
canary_paused
canary_at_capacity
canary_complete
proposal_exists_today
no_signal_today
pricing_invalid:bid_zero
pricing_invalid:ask_zero
pricing_invalid:crossed
pricing_invalid:spread_wide
pricing_invalid:oi_thin
pricing_invalid:vol_thin
pricing_invalid:spot_missing
exception:<ExcType>
```

**Wrapper-RC `reason` values** — lifecycle job:
```
master_flags_off
preflight_failed:drift
preflight_failed:schema_drift
preflight_failed:chain_stale
canary_paused
no_open_position
no_fill_yet
proposal_expired
stale_chain
pricing_invalid:<sub>     (full set as above)
lifecycle_stall
expiry_edge
exception:<ExcType>
monitored
filled
closed:tp_hit
closed:sl_hit
closed:max_hold
closed:expiry_guard
closed:manual_operator_close
```

**Telemetry `classification`** (already DB-CHECK'd at Gate 2):
```
success | no_op | paused | error | operator_action
```

**Telemetry `failure_code`** (already DB-CHECK'd at Gate 2):
```
F1_stale_chain | F2_no_fill | F3_pricing_invalid |
F4_lifecycle_stall | F5_expiry_edge | F6_deployment_drift |
F7_telemetry_mismatch
```

The wrapper-RC reasons compose into the DB-enforced enums; reviewer can
audit the mapping by reading §5.2 / §5.3 tables.

---

## 13. What this gate does NOT do

- No business logic. All `_select_candidate_contract`, `_execute_fill`,
  `_evaluate_exit_triggers`, `_reconcile_close_accounting` are stubs.
- No DB writes. No code authored.
- No `registry.py` registration. Scheduler doesn't know about the new
  jobs until Gate 4.
- No flag flips. `OPTIONS_ENABLED` and `OPTIONS_CANARY_ENABLED` stay
  false.
- No migration apply. `090_options_canary_lifecycle_run` remains unbuilt
  on dev/prod.
- No CI lint changes (those land at Gate 4 alongside skeletons).
- No operator CLI implementation (out of Canary-1 scope; deferred to
  post-canary).

---

## 14. Approval checklist

For the reviewer to confirm before approving Gate 3:

- [ ] Module boundaries match expectation (workers → api, never reverse).
- [ ] Two scheduler entrypoints only; no third surface.
- [ ] `_append_lifecycle_event` is the only event write surface.
- [ ] `_write_canary_telemetry` is the only telemetry write surface.
- [ ] Per-invocation telemetry guarantee acceptable (one row, always).
- [ ] Mutability matrix in §10 accurately scopes which tables can be
      UPDATE'd vs append-only.
- [ ] Closed reason enum in §12 covers all paths.
- [ ] Operator surface acknowledged as out-of-scope-for-Gate-3 but
      contractually separated.
- [ ] CI lint additions in §11 are acceptable as Gate-4 deliverables.

On approval: proceed to Gate 4 (pre-flight script + skeleton files
authored as no-op stubs, then reviewed before any logic is added).
