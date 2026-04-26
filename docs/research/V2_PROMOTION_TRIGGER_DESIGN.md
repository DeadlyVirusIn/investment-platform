# V2 Promotion Trigger Framework — Design

**Date:** 2026-04-25
**Status:** DESIGN ONLY — awaiting operator approval before implementation
**Scope:** Governance layer above the advisory B2 vs V2 comparison framework
**Related:**
- `B2_V2_COMPARISON_FRAMEWORK_DESIGN.md` (the advisory comparison framework — v2)
- `B2_V2_COMPARISON_RESULTS.md` (implementation summary)
- `B2_V2_PERSIST3_UPDATE.md` (V2 strategy introduction)

---

## TL;DR

Defines the exact conditions under which V2
(`tsmom_60_no_stress_v2_persist3`) can replace B2
(`tsmom_60_no_stress`) as the **preferred shadow directional sleeve**.

This is a **separate governance layer** above the B2 vs V2 comparison
framework. The comparison framework is advisory; this trigger framework
adds hard gates, weekly snapshot persistence, a state machine, rollback
rules, and operator-approval requirements.

**`APPROVED_FOR_SHADOW_REPLACEMENT` does NOT mean production
execution.** It only means V2 may replace B2 as the *preferred shadow
candidate*. Actual production routing still requires separate Engine B
migration gates governed by `engine_b_promotion.py`.

---

## Hard Rules (non-negotiable)

| Rule | Enforcement |
|---|---|
| No auto-promotion | State machine never advances past `STRONG_CANDIDATE` without explicit operator approval written to a dedicated table |
| No live execution change | Framework does not touch `engine_b_router.py`, `ENGINE_B_MODE`, paper_trade_log, decision_log, or any production execution surface |
| No ML changes | Framework does not toggle, configure, or evaluate ML routes |
| No threshold optimization | All gate thresholds are module-level constants. Changing any value requires a documented revision-history entry |
| Comparison framework remains advisory | Verdict from `b2_v2_comparison.py` is consumed read-only; this layer adds gates, never changes the comparison's verdict |

---

## Non-Goals (explicit)

- ❌ **Not** a production routing change. State `APPROVED_FOR_SHADOW_REPLACEMENT` only re-labels which strategy is the "preferred shadow directional sleeve" for downstream readers (operator dashboards, future Engine B promotion-gate inputs).
- ❌ **Not** an `ENGINE_B_MODE` flip. Engine B mode remains under operator-only env-var control via `engine_b_promotion.py`.
- ❌ **Not** an ML promotion path. ML routes remain advisory and governed by their own gates.
- ❌ **Not** a B2 retirement. B2 continues to compute decisions, write to `paper_shadow_log`, and serve as the comparison baseline indefinitely after V2 promotion.
- ❌ **Not** a kill-switch for V2. Rollback rules govern downgrade between states; V2 strategy itself is never disabled by this framework.
- ❌ **Not** a re-run of the comparison framework. Reads existing `compute_all` output, never recomputes metrics.
- ❌ **Not** a backtest. Operates strictly on live shadow data accumulating in `paper_shadow_log`.
- ❌ **Not** a substitute for `engine_b_promotion.py`. That module governs production routing; this framework governs shadow-preference.

---

## State Machine

```
                ┌──────────────┐
                │  NOT_READY   │  initial; any hard gate failed
                └──────┬───────┘
                       │  sample-size gates pass (Gate 1)
                       ▼
                ┌──────────────┐
                │    WATCH     │  enough data; verdict not yet stable
                └──────┬───────┘
                       │  verdict == V2_BETTER for ≥1 snapshot
                       │  AND edge gate (Gate 3 partial) passes
                       ▼
                ┌──────────────────┐
                │ READY_FOR_REVIEW │  emerging signal; not yet 4 weeks
                └──────┬───────────┘
                       │  verdict V2_BETTER for 4 consecutive weeks
                       │  AND readiness STRONG_CANDIDATE for ≥2 consecutive
                       │  AND ALL Gates 1–7 pass
                       ▼
                ┌──────────────────┐
                │ STRONG_CANDIDATE │  all hard gates pass; awaiting operator
                └──────┬───────────┘
                       │  explicit operator approval written
                       │  (Gate 8)
                       ▼
                ┌────────────────────────────────────────┐
                │   APPROVED_FOR_SHADOW_REPLACEMENT      │
                │   (preferred shadow sleeve = V2)       │
                │   ── no production routing change ──   │
                └────────────────────────────────────────┘
```

### State definitions

| State | Meaning | Required gates |
|---|---|---|
| `NOT_READY` | Initial state; insufficient data or any hard gate failed | none |
| `WATCH` | Sufficient sample but no V2 edge yet | Gate 1 |
| `READY_FOR_REVIEW` | Emerging V2 edge but lacks consecutive-week stability | Gates 1, 3 (partial — edge positive), and verdict V2_BETTER ≥1 snapshot |
| `STRONG_CANDIDATE` | All quantitative gates pass; awaiting operator | Gates 1–7 (all pass) AND verdict streak AND readiness streak |
| `APPROVED_FOR_SHADOW_REPLACEMENT` | Operator-approved; V2 is preferred shadow sleeve | All Gates 1–7 + Gate 8 (operator approval row exists) |

### Transition rules

- **Forward transitions** are *evaluated* automatically every snapshot,
  *executed* automatically only up to `STRONG_CANDIDATE`. The
  `STRONG_CANDIDATE → APPROVED_FOR_SHADOW_REPLACEMENT` transition
  REQUIRES an explicit row in `v2_promotion_approval` written by the
  operator (see Gate 8).
- **Backward transitions** (rollback) are evaluated automatically every
  snapshot per the rollback rules in §6. The framework can rescind
  `STRONG_CANDIDATE` automatically. It can **not** rescind
  `APPROVED_FOR_SHADOW_REPLACEMENT` automatically — that requires an
  operator-written rescission row.
- **No state skipping.** A snapshot that would advance two states at
  once advances exactly one. The next snapshot may advance further.

---

## Hard Gates

All hard gates evaluated against the most recent snapshot's bundle from
the comparison framework, plus the rolling history of prior snapshots.

### Gate 1 — Minimum Sample

| Sub-condition | Threshold |
|---|---:|
| `n_input_rows` (joined shadow days) | ≥ 60 |
| `n_divergent_rows` | ≥ 30 |
| `metrics.n_b2_flat_v2_long` | ≥ 10 |
| OOS days since framework implementation date (`2026-04-25`) | ≥ 10 |

All four must pass. The OOS condition is computed against snapshot
dates strictly greater than the implementation date — guards against
backfill windfalls.

### Gate 2 — Verdict Stability

| Sub-condition | Threshold |
|---|---|
| `verdict.verdict == "V2_BETTER"` for the **last 4 consecutive weekly snapshots** | strict equality |
| `verdict.readiness == "STRONG_CANDIDATE"` for the **last 2 consecutive weekly snapshots** | strict equality |
| `verdict.confidence ≥ 0.70` (current snapshot) | numeric |

Streak counter resets on any snapshot that fails the corresponding
condition. There is no leniency window — a single `INCONCLUSIVE` week
breaks the streak.

### Gate 3 — Edge Quality

| Sub-condition | Threshold |
|---|---:|
| `metrics.avg_return_diff_1d_bps` (current snapshot) | ≥ +5 |
| `metrics.cumulative_return_diff_pct` (current snapshot) | ≥ +0.5% |
| `metrics.impact_weighted_edge` (current snapshot) | > 0 |
| `metrics.impact_weighted_edge` trend over last 4 snapshots | non-decreasing OR within +10% noise band |

Edge quality is computed snapshot-current; the trend sub-condition
guards against impact-weighted edge collapsing while raw edge holds
(possible if denominators shrink).

### Gate 4 — Tail Risk

| Sub-condition | Threshold |
|---|---:|
| `verdict.tail_guard_triggered == false` (current snapshot) | strict |
| `tail.tail_delta_p99_bps` | ≥ −10 |
| `tail.tail_delta_p95_bps` | ≥ −5 |
| Each of V2's `worst_5_losses_bps` | ≤ corresponding B2 worst-5 entry × 1.10 (V2 may be at most 10% deeper at any rank) |

Worst-5 comparison is rank-aligned (sorted ascending: V2[i] vs B2[i]
for i in 0..4).

### Gate 5 — Regime Validation

Computed from `metrics_by_regime`:

| Sub-condition | Threshold |
|---|---|
| `metrics_by_regime.directional.avg_return_diff_1d_bps` | > 0 |
| Tail in stress days for V2 (sub-bundle p99) | ≥ B2's stress-day p99 − 10 bps |
| `metrics_by_regime.neutral.avg_return_diff_1d_bps` | ≥ −2 (small negative tolerated; neutral is low-information) |
| Single-regime concentration | No regime contributes > 80% of the cumulative V2 advantage; defined as `regime_cum_diff_pct[r] / sum(regime_cum_diff_pct) ≤ 0.80` for every regime where the sum is positive |

The concentration check guards against the V2 edge being entirely
driven by one regime bucket — the persist-3 thesis predicts payoff
*in* stress days, not *only* in any single regime.

### Gate 6 — Stability

| Sub-condition | Threshold |
|---|---|
| `stability.first_half_vs_second_half.first_half_edge_bps` | > 0 |
| `stability.first_half_vs_second_half.second_half_edge_bps` | > 0 |
| `stability.last_30_vs_prior_30.trend` | NOT in (`DECLINING`, `INSUFFICIENT`) |

Both halves must show positive edge — a strong second half compensating
for a negative first half is rejected (potential overfit / regime
luck).

### Gate 7 — No Conflict With Governance

| Sub-condition | Threshold |
|---|---|
| B2 promotion pause may remain active — Engine B promotion state is **read-only context**, not a blocker (B2 may stay paused independently of V2 shadow preference) | informational only |
| Current `ENGINE_B_MODE` ∈ (`LEGACY`, `SHADOW_COMPARE`) | strict |
| `b2_v2_comparison` framework is healthy: no API errors in last 7 snapshot fetches; no schema-drift errors | strict |
| ML routes status: no ML promotion to live; ML remains advisory | strict |

Engine B mode beyond `SHADOW_COMPARE` invalidates the shadow comparison
because the routed signal would diverge from B2's signal. The framework
must abstain (state forced to `NOT_READY`) until mode reverts.

### Gate 8 — Operator Approval

| Sub-condition | Threshold |
|---|---|
| Row exists in `v2_promotion_approval` table with `decision='APPROVE'`, `as_of_date >= snapshot.as_of_date − 14 days`, `approver` non-empty | strict |
| Approval row references the snapshot it approves (`snapshot_id` FK) | strict |
| No subsequent `decision='RESCIND'` row for the same snapshot | strict |

The 14-day window prevents stale approvals from auto-promoting after
intervening data drift. A new approval is required if the snapshot
relevant for promotion is older than 14 days.

---

## Confidence Score

Single 0–1 score reported alongside the state. **Distinct from the
comparison framework's confidence** — that one scores the *verdict*;
this one scores *promotion-readiness*.

```
promotion_confidence =
    0.20 * sample_score          # Gate 1 margin (cap at 1.0 once 2× thresholds met)
  + 0.20 * verdict_streak_score  # min(verdict_streak / 4, 1.0)
  + 0.15 * readiness_streak_score# min(readiness_streak / 2, 1.0)
  + 0.15 * edge_score            # clamp((edge_bps - 5) / 15, 0, 1)
  + 0.10 * tail_score            # 1.0 if all Gate-4 conditions pass with margin; linear degrade as p99 delta approaches threshold
  + 0.10 * regime_score          # 1.0 if all Gate-5 sub-conditions pass; degrades on concentration approach to 80%
  + 0.10 * stability_score       # 1.0 if both halves > 0 and trend not declining; 0.5 if one half tiny-negative
```

Each component is in [0, 1]; the weighted sum is in [0, 1].

`promotion_confidence ≥ 0.70` is **necessary but not sufficient** for
`STRONG_CANDIDATE` — all hard gates must also pass. The score is
informational, not a gate substitute.

---

## Weekly Snapshot Logic

### Schedule

- One snapshot per ISO-week, taken on Monday 00:15 UTC (after the prior
  week's last fwd_return_1d has settled).
- Snapshots are immutable. Re-running the snapshot job for an existing
  ISO-week is a no-op.

### Storage (proposed table)

```
TABLE v2_promotion_snapshot
  id                       BIGSERIAL PRIMARY KEY
  as_of_date               DATE NOT NULL
  iso_year                 INT NOT NULL
  iso_week                 INT NOT NULL
  comparison_bundle_json   JSONB NOT NULL    -- exact compute_all() output
  state                    TEXT NOT NULL     -- NOT_READY | WATCH | READY_FOR_REVIEW | STRONG_CANDIDATE | APPROVED_FOR_SHADOW_REPLACEMENT
  prior_state              TEXT              -- previous snapshot's state (NULL on first)
  promotion_confidence     NUMERIC(5,4) NOT NULL
  gates_json               JSONB NOT NULL    -- per-gate pass/fail + reason
  verdict_streak           INT NOT NULL      -- consecutive V2_BETTER weeks ending at this snapshot
  readiness_streak         INT NOT NULL
  rollback_reason          TEXT              -- NULL unless this snapshot rolled back
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()

  UNIQUE (iso_year, iso_week)
```

```
TABLE v2_promotion_approval
  id                       BIGSERIAL PRIMARY KEY
  snapshot_id              BIGINT NOT NULL REFERENCES v2_promotion_snapshot(id)
  decision                 TEXT NOT NULL CHECK (decision IN ('APPROVE','RESCIND'))
  approver                 TEXT NOT NULL
  rationale                TEXT NOT NULL
  approved_at              TIMESTAMPTZ NOT NULL DEFAULT now()
```

### Snapshot job

Pure read + insert. Pseudocode:

```
fetch_comparison_bundle(days=365, instrument=SPY)
load_prior_snapshots(last_8_weeks)
gates_result = evaluate_all_gates(bundle, prior_snapshots)
streak_result = update_streaks(prior_snapshots[-1], bundle.verdict)
confidence    = compute_promotion_confidence(gates_result, streak_result)
state         = state_machine.advance_or_rollback(
                    prior_state=prior_snapshots[-1].state,
                    gates=gates_result,
                    streaks=streak_result,
                    operator_approval_present=check_approval(),
                )
insert_snapshot(...)
```

The job NEVER reads or writes any execution surface. It only reads
`paper_shadow_log` (indirectly via the comparison API), reads its own
prior snapshots, and inserts one new snapshot row.

### Streak semantics

`verdict_streak` and `readiness_streak` are computed as: count of
consecutive prior snapshots ending with the current one whose
verdict/readiness equals the target value. A break sets the streak to
0 (or 1 if the current snapshot itself satisfies the condition).

Snapshots are evaluated weekly; a 4-week verdict streak therefore
spans ~28 calendar days.

---

## UI Copy

A new card on the Ops page, **separate from** the existing
`B2vsV2ComparisonCard`. Suggested label: **"V2 Promotion Trigger"**.

### Header

> **V2 Promotion Trigger** — governance · operator-only decision · no production routing change

### State badge

| State | Color | Tooltip |
|---|---|---|
| `NOT_READY` | neutral | "Insufficient data or hard gate failed. See gate breakdown below." |
| `WATCH` | info | "Sample-size gates pass; awaiting V2 edge to emerge." |
| `READY_FOR_REVIEW` | warning | "V2 edge emerging; verdict-stability streak in progress." |
| `STRONG_CANDIDATE` | success (outlined) | "All quantitative gates pass. Operator approval required to advance." |
| `APPROVED_FOR_SHADOW_REPLACEMENT` | success (filled) | "V2 is preferred shadow directional sleeve. Production routing unchanged." |

### Always-visible disclaimer (under header)

> This badge governs **shadow-preference only**. Production routing
> remains controlled by Engine B migration gates and is **not
> affected** by this state.

### Gate breakdown (table)

One row per gate (1–8), columns: `Gate`, `Status` (PASS/FAIL/N-A),
`Detail`. Failing gates show the specific sub-condition that failed.

### Streak strip

Two horizontal pill rows:

```
Verdict streak: ●●●●○○○○  4 / 4 weeks (V2_BETTER)
Readiness streak: ●●○○○  2 / 2 weeks (STRONG_CANDIDATE)
```

### Promotion confidence bar

0–100% bar with sub-component breakdown on hover (sample / verdict /
readiness / edge / tail / regime / stability).

### Operator action area (only visible when `STRONG_CANDIDATE`)

```
┌─────────────────────────────────────────────────────────────┐
│ Approve V2 as preferred shadow directional sleeve?          │
│                                                             │
│ This does NOT change production routing.                    │
│ This does NOT modify Engine B mode or risk parameters.      │
│ This only re-labels which strategy is the preferred         │
│ shadow candidate going forward.                             │
│                                                             │
│ Rationale (required):  [______________________________]     │
│ Approver (required):   [______________________________]     │
│                                                             │
│         [ Cancel ]    [ Approve Shadow Replacement ]        │
└─────────────────────────────────────────────────────────────┘
```

The "Approve" button POSTs to `/api/v2-promotion/approve` (writes a
row to `v2_promotion_approval`). On success, the card refreshes; the
*next* snapshot will reflect the new state.

### Rescission area (only visible when `APPROVED_FOR_SHADOW_REPLACEMENT`)

```
┌─────────────────────────────────────────────────────────────┐
│ Rescind V2 shadow-preference approval                       │
│                                                             │
│ Reverts state to STRONG_CANDIDATE on next snapshot.         │
│ Does not affect production routing.                         │
│                                                             │
│ Rationale (required):  [______________________________]     │
│         [ Cancel ]                  [ Rescind Approval ]    │
└─────────────────────────────────────────────────────────────┘
```

### Rollback alert (when current snapshot's `rollback_reason` is set)

Amber banner above the gate table:

> ⚠ State rolled back from `<prior_state>` to `<state>` on
> `<as_of_date>`: `<rollback_reason>`

---

## Rollback Rules

Evaluated every snapshot. The state machine downgrades automatically
to the **highest state that still satisfies all required gates** for
that level (with one exception: `APPROVED_FOR_SHADOW_REPLACEMENT`
requires an operator rescission to leave).

### Automatic rollback table

| From state | Triggers automatic downgrade to |
|---|---|
| `STRONG_CANDIDATE` → `READY_FOR_REVIEW` | Any of: verdict streak breaks below 4; readiness streak breaks below 2; confidence < 0.70; any of Gates 3, 4, 5, 6 fails |
| `STRONG_CANDIDATE` → `WATCH` | Edge gate fully fails AND verdict ≠ V2_BETTER for current snapshot |
| `STRONG_CANDIDATE` → `NOT_READY` | Gate 1 (sample) fails OR Gate 7 fails (governance conflict) OR Gate 4 hard breach (tail_delta_p99 < −25 OR tail_guard_triggered for 2 consecutive snapshots) |
| `READY_FOR_REVIEW` → `WATCH` | Verdict ≠ V2_BETTER for current snapshot OR Gate 3 partial (edge_bps < +5) fails |
| `READY_FOR_REVIEW` → `NOT_READY` | Gate 1 fails OR Gate 7 fails |
| `WATCH` → `NOT_READY` | Gate 1 fails OR Gate 7 fails |

### Operator-rescission rollback

| From state | Trigger | To state |
|---|---|---|
| `APPROVED_FOR_SHADOW_REPLACEMENT` → `STRONG_CANDIDATE` | Operator writes `decision='RESCIND'` row | next snapshot evaluates as `STRONG_CANDIDATE` if Gates 1–7 still pass, else falls further per automatic rules |

### Tail-risk emergency rollback

If on any snapshot:
- `tail_guard_triggered == true` for **2 consecutive snapshots**, OR
- `tail_delta_p99_bps < −25` on the current snapshot

…then state is forced to `NOT_READY` regardless of prior state, including from `APPROVED_FOR_SHADOW_REPLACEMENT`. The framework writes a snapshot row with `rollback_reason='tail-risk emergency'` and surfaces a red banner. **Forced rollback from `APPROVED_FOR_SHADOW_REPLACEMENT`** is the *only* automatic exit from that state — and it does not require operator action because the tail breach itself is the operator-actionable signal.

---

## Implementation Plan

This section is the implementation **plan** — not implementation
itself. Implementation occurs only after operator approval of this
design doc.

### Phase 1 — Schema + persistence (1–2 days)

1. Migration: create `v2_promotion_snapshot` and `v2_promotion_approval` tables.
2. SQLAlchemy models for both tables.
3. Indexes: `(iso_year, iso_week)` unique; `(snapshot_id)` on approval table; `(as_of_date DESC)` on snapshots for fast last-N queries.

### Phase 2 — Gate evaluation module (2–3 days)

1. New file `apps/api/src/research/v2_promotion_gates.py` — pure functions:
   - `evaluate_gate_1(...) → GateResult`
   - … one per gate
   - `evaluate_all_gates(bundle, prior_snapshots, approval_row) → dict[str, GateResult]`
2. Frozen threshold constants in module.
3. Unit tests with hand-crafted bundles + mock prior-snapshot histories — same shape as `test_b2_v2_comparison.py`.

### Phase 3 — State machine + confidence (1–2 days)

1. New file `apps/api/src/research/v2_promotion_state.py`:
   - `advance_or_rollback(prior_state, gates, streaks, approval_present) → (new_state, rollback_reason)`
   - `compute_promotion_confidence(gates, streaks) → float`
   - `update_streaks(prior_snapshot, current_verdict) → (verdict_streak, readiness_streak)`
2. Unit tests covering every transition arrow + every rollback rule.

### Phase 4 — Snapshot job (1 day)

1. New file `apps/worker/src/jobs/v2_promotion_snapshot.py`:
   - Reads comparison bundle
   - Reads prior snapshots
   - Reads pending approval row (if any)
   - Computes gates + state + confidence
   - INSERTs snapshot row
2. Idempotency: if a row already exists for `(iso_year, iso_week)`, do nothing.
3. Register in `apps/worker/src/jobs/registry.py` with weekly schedule (Monday 00:15 UTC).

### Phase 5 — Read-only API (1 day)

1. New file `apps/api/src/api/v2_promotion.py`:
   - `GET /api/v2-promotion/state` — current state + latest snapshot
   - `GET /api/v2-promotion/snapshots?weeks=12` — historical snapshots
   - `GET /api/v2-promotion/gates` — per-gate detail for current snapshot
2. **One** mutating endpoint, both writes only to `v2_promotion_approval`:
   - `POST /api/v2-promotion/approve` — body: `{rationale, approver, snapshot_id}`
   - `POST /api/v2-promotion/rescind` — body: `{rationale, approver, snapshot_id}`
3. Both mutating endpoints REQUIRE all of: snapshot_id matching the current `STRONG_CANDIDATE` snapshot (for approve), or matching the current approved snapshot (for rescind); rationale ≥ 20 chars; approver from a hardcoded allowlist (operator emails) — design requires the allowlist to be maintained outside the framework.
4. Register the router in `apps/api/src/main.py`.

### Phase 6 — UI (2–3 days)

1. New hook `apps/web/src/lib/v2Promotion/hooks.ts`.
2. New card `apps/web/src/components/ops/V2PromotionTriggerCard.tsx` (per UI Copy section).
3. Mount on Ops page below `B2vsV2ComparisonCard`.
4. Approval / rescission modals invoking POST endpoints with confirmation step.

### Phase 7 — Verification (1 day)

1. End-to-end: insert seed snapshots, drive state machine through every transition via API + UI, assert downstream effects.
2. Document a runbook in `docs/research/V2_PROMOTION_TRIGGER_RUNBOOK.md` (created during implementation, not now).

### Files NOT to be modified during implementation

- `apps/api/src/research/shadow_strategy.py`
- `apps/api/src/research/shadow_strategy_v2.py`
- `apps/api/src/research/engine_b_promotion.py`
- `apps/api/src/research/engine_b_router.py`
- `apps/api/src/research/engine_b_decision.py`
- `apps/api/src/research/engine_b_analytics.py`
- `apps/api/src/research/b2_v2_comparison.py`
- `apps/api/src/api/b2_v2_comparison.py`
- `apps/api/src/api/engine_b_transition.py`
- Any execution / routing / risk / ML module

---

## Acceptance Criteria (for implementation)

1. All hard gates evaluated per the definitions above.
2. State machine transitions match the diagram exactly — covered by unit tests for every arrow.
3. Snapshot job is idempotent on `(iso_year, iso_week)`.
4. `APPROVED_FOR_SHADOW_REPLACEMENT` only reachable through an operator-written approval row.
5. Tail-risk emergency rollback verified: forced regression from `APPROVED_FOR_SHADOW_REPLACEMENT` to `NOT_READY` on synthetic tail-breach snapshots.
6. UI never offers an approval CTA outside the `STRONG_CANDIDATE` state.
7. No file in the "NOT to be modified" list is touched.
8. `git grep "ENGINE_B_MODE\|engine_b_router\|paper_trade_log\|decision_log"` in the new modules returns zero matches.

---

## Open Questions for Operator

The following are intentionally unresolved in this design and require
operator input before implementation:

1. **Approver allowlist** — list of email addresses authorized to write to `v2_promotion_approval`. Suggested: same set as those who currently flip `ENGINE_B_MODE`.
2. **Snapshot timezone** — design proposes Monday 00:15 UTC. Confirm or override.
3. **Notification on state change** — should `STRONG_CANDIDATE` advancement page on-call, send a Slack message, send only an email digest, or be passively visible only? Design currently assumes passively visible only.
4. **Historical replay** — should the framework, on first deployment, retroactively snapshot the last N weeks from existing `paper_shadow_log` data, or start fresh from the deployment week? Design currently assumes start fresh, to keep the OOS-day requirement clean.
5. **Audit retention** — how long should `v2_promotion_snapshot` rows be retained? Design assumes indefinite.

---

## Summary of Boundaries

| Boundary | Where enforced |
|---|---|
| No production routing change | Framework writes only to `v2_promotion_snapshot` and `v2_promotion_approval`; never touches `paper_trade_log`, `decision_log`, `engine_b_router`, or `ENGINE_B_MODE` |
| No B2 / V2 logic change | Framework reads `paper_shadow_log` indirectly through the comparison API; never writes to it |
| No threshold optimization | All thresholds are module-level constants requiring revision-history doc updates to change |
| No auto-promotion past `STRONG_CANDIDATE` | State machine requires an approval row written by an allowlisted operator |
| No automatic exit from `APPROVED_FOR_SHADOW_REPLACEMENT` | Except the tail-risk emergency rollback, which is the only automatic exit and is itself bounded |
| No ML changes | Framework does not read ML state; ML routes remain advisory |
| No risk-parameter changes | Framework does not touch position sizing, stops, or any risk module |

---

**Awaiting operator approval. Reply `approved` to proceed to Phase 1 of the implementation plan.**
