# Research Safe Mode (Wave 1B)

Status: BUILT in dev, flag-off · Branch `feature/elite-arthos-provable-ideas`
· Migration **120_system_posture_event** (dev applied 2026-07-13 after backup
`.backups/devdb_full_20260713_pre120.dump`; ephemeral up/down/up validated;
**prod untouched at 109**). Companion:
`RECOMMENDATION_PUBLICATION_PREFLIGHT.md` (Wave 1A, consumes this posture).

## What it is

The system-level publication brake. A deterministic signal registry derives
one of three postures behind the interface Preflight already consumes
(`domain/publication/posture.py::current_posture[_event]`):

* **NORMAL** — all mandatory signals healthy; ideas publish per their own
  preflight verdicts.
* **RESTRICTED** — degraded-but-readable; any otherwise-READY idea is capped
  at READY_WITH_LIMITATIONS (posture check fails at limitation severity).
* **SAFE** — no NEW idea publishes (posture check fails at hold severity →
  every candidate verdict HOLD). Existing recommendations, portfolios, paper
  exits, outcome processing, account access, and history remain fully
  available — posture gates the publication read path ONLY (pinned by
  isolation tests).

No LLM anywhere. No owner route can manufacture a posture the signals don't
support: owner actions run the SAME evaluator; incidents are downgrade-only;
acknowledgment only unlocks the hysteresis path.

## Flag

`SYSTEM_POSTURE_ENABLED` (default **False**). Off = Wave-1A behavior exactly:
`SYSTEM_POSTURE_OVERRIDE` (dev/test lever) else NORMAL; no signals read, no
event rows written, no `/system/posture` or `/admin/posture/*` routes, no
banner (pinned by test). On = signal-derived; the override is ignored.

## Signal registry (`posture-1`, ordered; policy constants in module)

| Signal | warning | critical |
|---|---|---|
| ingest_health | last success > 30 h | status ≠ success · > 72 h · no history |
| price_data | newest 1d bar > 5 d | > 10 d · none |
| ingest_contracts | flag disabled (validation unenforced) | (ABORT detection wires in when contract reports persist) |
| scheduler (reuses `ops/scheduling_health.overdue_jobs`) | any overdue/stuck schedule | stuck/overdue schedule in the publication-input set (`ingest_prices_daily`, `run_daily_pipeline`, `generate_stock_candidates`) |
| drift (reuses SQL-first `monitoring/drift.run_drift_report`) | warn OR alert — **policy: statistical drift alone never reaches SAFE** | — |
| provenance | runtime git sha unknown (systemic; candidate-level provenance stays a Preflight block — no circularity) | — |
| outcome_pipeline | no successful outcome-labeling run within 4 d (weekend/holiday-tolerant grace; open positions never alarm) | — |
| owner_incident | open incident severity=restricted | open incident severity=safe |

Per-signal exception → that signal fails closed as a warning (never silently
ok, never a whole-evaluator crash).

Posture proposal: any critical → SAFE · any warning → RESTRICTED · else
clean/NORMAL.

## Transition diagram + hysteresis (deterministic, no timers)

```
                    any critical                any warning
     NORMAL ───────────────────────▶ SAFE ◀────────────────── RESTRICTED
        │                             │  ▲                        ▲ │
        │ any warning                 │  │ signals improve        │ │ clean cycle 1
        ▼                             │  │ but NOT acknowledged   │ │ (cooldown, stays
     RESTRICTED ──── any critical ────┘  │ → stays SAFE           │ │  RESTRICTED)
        │                                │                        │ ▼
        │ clean + prev cycle clean       │ owner ACK (allowed     │ clean cycle 2
        ▼                                │ only with no critical) │
     NORMAL                              └──▶ RESTRICTED(recovering) ──▶ NORMAL
```

* Downgrades always immediate (auto).
* ANY improvement out of SAFE requires prior owner acknowledgment — without
  it the evaluator re-emits SAFE with `awaiting_acknowledgment`.
* Recovery moves one step per evaluation cycle: SAFE →(ack+clean)→
  RESTRICTED(recovering) →(clean)→ NORMAL; warning-RESTRICTED recovers via
  one clean cooldown cycle then NORMAL.
* Flap-proof: identical stable signal state is idempotent (see events) so
  repeated identical cycles produce zero new rows and zero posture churn.

## Event ledger (migration 120, append-only)

`system_posture_event`: id · posture (CHECK) · reasons_json (≤4000) ·
signal_snapshot_json (≤16000) · triggered_by (CHECK: `auto`|`system`|
`owner:<email>`) · previous_event_id (self-FK chain) · evaluator_version ·
evaluator_git_sha · input_hash · acknowledged_at/by (written only at insert
by the ack event itself) · created_at.
Idempotency/concurrency: `UNIQUE NULLS NOT DISTINCT (previous_event_id,
input_hash, posture, triggered_by)` — identical evaluations with the same
predecessor collapse to one row, including the NULL-predecessor first event.
`input_hash` = sha256 over evaluator version + posture + the STABLE signal
basis (ids, levels, fact identities such as run ids — continuous ages are
stored for humans but excluded from the hash, same fix class as pf-2).
No UPDATE/DELETE path exists in the service (pinned by introspection);
acknowledgment and incident open/close are their own events.

## Evaluation paths

1. **Scheduled** — worker job `evaluate_system_posture` (registered in the
   claim/lease-safe registry; flag-guarded no-op when off). No schedule row
   ships in any migration: enabling it is a runbook step
   (`INSERT INTO job_schedule (name, cron_expr, enabled, next_run_at) VALUES
   ('evaluate_system_posture', '*/15 * * * *', true, now())` — dev first).
2. **Lazy fallback** — `current_posture_event(db)` with a 60 s in-process
   TTL cache; evaluates+records when cold.
3. **Owner manual** — `POST /admin/posture/evaluate` runs the same
   evaluator; cannot override its result.

## Failure behavior

Evaluator/db exception in the read path → RESTRICTED (never NORMAL);
**3 consecutive failures → SAFE** (bounded documented rule; resets on
success). No session → RESTRICTED. Malformed incident payload → treated as
severity=safe (fail closed). Event-write failures surface as exceptions →
the same fail-closed path (a silent NORMAL is impossible: NORMAL only ever
comes from a successfully persisted clean evaluation).

## API

Public (flag-mounted) `GET /api/system/posture` → `{posture, message,
evaluated_at, new_ideas_paused, existing_ideas_available,
portfolio_available}` — never provider details, hostnames, job ids, raw
signal JSON, stack traces, or owner identity (pinned by redaction test).
Owner (require_owner 404 posture): `POST /admin/posture/evaluate` ·
`GET /admin/posture/events[/{id}]` (full reasons + snapshot) ·
`POST /admin/posture/incident {severity: restricted|safe, reason}` ·
`POST /admin/posture/incident/close` (re-evaluates; cannot manufacture
NORMAL) · `POST /admin/posture/acknowledge` (409 while any critical remains).

## UI

Beginner: `PostureBanner` on Discover, Today, and idea detail — SAFE: "New
ideas are paused while ArthOS checks its data. Your practice portfolio and
existing ideas are still available." RESTRICTED: "Some data is delayed. New
ideas may include additional limitations." Calm StatusPanel language; no
panic wording (pinned by test); absent on NORMAL/flag-off.
Owner: Research Safe Mode panel on `/admin/preflight` (current posture chip,
last transition, ordered reasons, evaluate/ack/incident/close actions,
transition history). Trust Center gains a READ-ONLY "Publication posture"
section — evidence surface, never controls.

## Relationship to Preflight (pf-2)

Preflight consumes `(posture, posture_event_id)`; the event id is part of
the pf-2 input hash, so any posture transition invalidates every stale
publishable verdict (pinned by pg test). SAFE → per-candidate HOLD;
RESTRICTED → limitation (caps at READY_WITH_LIMITATIONS).

## Read-side-effect review (measured, dev, 200 candidates)

Per-candidate path: ~18 s cold / ~8.7 s warm → replaced by the bulk path
(`ensure_current_verdicts_bulk`): **7 fixed queries + 1 batched idempotent
insert; measured 1.18 s cold (200 evaluations) / 0.64–0.81 s warm (0
evaluations)**. Bounds: ≤ `MAX_PREFLIGHT_EVALS_PER_REQUEST` (250)
candidates per request, candidates beyond the cap fail closed; a module
lock single-flights concurrent cold requests (thundering-herd losers would
be harmless via the DB unique key, just wasteful). Writes per request:
steady state 0; worst case one batched INSERT of ≤250 rows/day/rule-set
change. Bulk/single parity pinned by test.
**Design note (next slice, not this one):** routine evaluation should move
into the nightly publication pipeline (evaluate right after
recommendations generate, via the scheduled job), demoting the read path to
pure lookup + lazy fail-closed fallback. The seam already supports this —
the scheduled `evaluate_system_posture` job plus a nightly
`ensure_current_verdicts_bulk` call over the latest generation is the whole
change; no engine refactor required.

## Rollback

Flag off → routes/banner/panel vanish, evaluator dormant, preflight consumes
override/NORMAL exactly as Wave 1A shipped. `alembic downgrade
119_recommendation_preflight` drops the event table (additive-only).

## Production promotion gates

1. Existing promotion plan Stage B (unchanged critical path).
2. ≥1 week of dev posture history with zero flapping (no
   NORMAL↔RESTRICTED oscillation on identical signals) and correct weekend
   outcome-grace behavior.
3. Scheduled job enabled in dev and observed through ≥3 nightly cycles.
4. Owner copy review of banner + incident flows.
5. Separate approval for the prod flag + schedule row (standard hard stop).

## Tests (all green 2026-07-13)

15 unit (`test_system_posture_unit.py`): proposal matrix, immediate
downgrades, cooldown cycles, SAFE-ack gate incl. impossibility of direct
SAFE→NORMAL, ack-marker unlock, no-flapping.
26 pg (`test_system_posture_pg.py`): flag-off zero-read/zero-write with
override honored; every signal trigger + warning/critical classification;
idempotent evaluation; changed-signals append; NULLS-NOT-DISTINCT
concurrency collapse; no UPDATE/DELETE; payload-bound + trigger-vocabulary
CHECKs; full recovery path (SAFE → ack → RESTRICTED(recovering) → cooldown
→ NORMAL with steady-state warnings silenced); ack refused while
critical / when not SAFE; incident declare severity mapping, close
re-evaluates and cannot manufacture NORMAL, close-without-open refused;
evaluator failure → RESTRICTED then SAFE at threshold; db failure never
NORMAL; public projection redaction; preflight coupling (posture event id
in hash, SAFE→HOLD); paper/portfolio decoupling.
Plus Wave-1A suites re-green under pf-2 (44 unit + 15 hash-boundary +
20 pg incl. bulk parity + fail-closed) and 249 web tests (banner calm-copy
+ absence states). Live dev drill: owner SAFE incident → 0 published +
banner; close+ack+evaluate → RESTRICTED(recovering); latency measured
above; screenshots `safe-mode-banner-desktop.jpeg`,
`posture-owner-panel-desktop.jpeg`.
