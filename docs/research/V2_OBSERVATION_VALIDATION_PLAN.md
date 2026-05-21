# V2 Observation & Validation Plan — 60–90 Day OOS Window

**Date:** 2026-04-26
**Status:** ACTIVE — observation phase commences with the next weekly snapshot
**Decision:** Option A — WAIT / OBSERVE FIRST. No new code. No ML. No threshold tuning. No execution changes.
**Duration:** 60 calendar days minimum; 90 days target before any reconsideration of further phases.
**Owner:** Operator + research review
**Cadence:** Weekly snapshot job already runs Monday 00:15 UTC; this plan adds a structured weekly review against existing outputs.

---

## TL;DR

The V2 promotion-trigger framework + OOS monitoring layer + statistical
validation module are complete and live-ready. **The next 60–90 days
are pure observation.** No new features, no optimization, no ML
implementation. Operator runs a standardized weekly review against the
existing snapshot + monitoring report data, tracking specific
quantities and flagging specific patterns. **At the end of the
window, a separate decision is made — informed by the observation
record — about whether to revisit Phase 10C.2 (ML implementation) or
extend observation further.**

This document is the operator's runbook for that observation window.

---

## 0. Hard rules for the observation window

| Rule | Enforcement |
|---|---|
| No execution change | All execution surfaces remain as configured. `ENGINE_B_MODE` stays in {LEGACY, SHADOW_COMPARE}. |
| No strategy logic change | B2 / V2 / Engine A / Engine B byte-identical to current state |
| No gate threshold change | All Phase 9B constants frozen; revision-history doc unchanged |
| No state machine change | No new states; no transition rule edits |
| No ML implementation | Phase 10C.2 not started; no ML modules added |
| No auto-promotion | Manual approval workflow remains the only promotion path |
| No new tables / migrations | Schema frozen at migration 046 |
| No new gates / new red flags | Phase 9B + Phase 10B.2 surfaces are the complete set |
| Approval policy unchanged | Operator can still approve via `/api/v2-promotion/approve` if and when Gate 8 conditions are met; this plan adds NO new approval mechanics |

---

## 1. OOS Observation Framework

### 1.1 Primary tracked surfaces

Operator pulls from existing read-only endpoints — no new code paths
needed:

| Source | Surface | Endpoint / module |
|---|---|---|
| Latest snapshot | `state`, `confidence`, `verdict_streak`, `readiness_streak`, `rollback_reason`, `snapshot_content_hash`, `code_version`, `timezone` | `GET /api/v2-promotion/state` |
| Snapshot history | last 16 snapshots, oldest-first | `GET /api/v2-promotion/snapshots?weeks=16` |
| Gate detail | per-gate pass/fail + reason | `GET /api/v2-promotion/gates` |
| OOS monitoring report (Phase 10B.2) | `assessment`, `red_flags[*]`, `recommended_action`, `edge.trend`, `edge.slope_bps_per_week`, `streaks.streak_reset_count_last_8w`, `governance.*` | Direct call: `apps.api.src.research.v2_oos_monitoring.fetch_and_build_weekly_report(session)` |
| Comparison bundle | `metrics.*`, `metrics_by_regime.*`, `tail.*`, `tail_by_regime.*`, `verdict.*`, `confidence_breakdown.basis_warnings` | `GET /api/b2-v2/comparison?days=365` |
| Statistical validation (Phase 10A.2) | `pbo`, `deflated_sharpe`, `bootstrap_ci.*` | Direct call: `apps.api.src.research.v2_stat_validation.compute_stat_validation(...)` — only when sample sufficient (§5) |

### 1.2 Per-week tracked quantities (mandatory)

Captured every Monday after the 00:15 UTC snapshot lands:

| Category | Quantity | Notes |
|---|---|---|
| **State** | current state | NOT_READY / SUSPENDED / WATCH / READY_FOR_REVIEW / STRONG_CANDIDATE / APPROVED |
| | prior state | Compared week-over-week for transitions |
| | rollback_reason | Plain-text from snapshot row |
| **Confidence** | `promotion_confidence` (0–1) | Stored value, not recomputed |
| | `confidence_breakdown.basis_warnings[]` | List of "vacuously high" component warnings (Phase 9B.2) |
| **Edge** | `metrics.avg_return_diff_1d_bps` | Snapshot-stored value |
| | `metrics.impact_weighted_edge` | Same |
| | `edge.trend` (UP / FLAT / DOWN / INSUFFICIENT) | From OOS report |
| | `edge.slope_bps_per_week` | From OOS report |
| | `edge.last_4w_avg_edge_bps` vs `prior_4w_avg_edge_bps` | Numeric pair |
| **Tail** | `tail.tail_delta_p99_bps` | Stored value |
| | `tail.tail_delta_p95_bps` | Stored value |
| | `tail_guard_triggered` (bool) | Stored value |
| | `tail_by_regime.{stress,directional,neutral}.{b2,v2}.{p99,p95,worst_5}_loss_bps` | Per-regime tail decomposition |
| **Streaks** | `verdict_streak` | Stored value |
| | `readiness_streak` | Stored value |
| | `streak_reset_count_last_8w` | From OOS report |
| **Governance** | approval_status | NONE / ACTIVE / EXPIRING_SOON / EXPIRED / RESCINDED |
| | days_until_expiry (signed integer) | From OOS report |
| | snapshot_content_hash_match | Bool — approval still binds to current snapshot |
| | `code_version`, `timezone`, `schema_version` | Operational metadata |
| **SUSPENDED / rollback** | SUSPENDED occurrences in trailing 12 weeks | Manual count |
| | distinct rollback reasons | Free-text dedup |
| | streak hard-reset triggered by force_reset | Confirmed via `verdict_streak == 0 AND prior > 0` after SUSPENDED entry |
| **Red flags** | full `red_flags[]` array | From OOS report; preserve every entry verbatim |
| **Assessment** | NORMAL / WATCH / REVIEW_REQUIRED | From OOS report |
| **Recommended action** | NONE / REVIEW / INVESTIGATE / DO_NOT_APPROVE | From OOS report — never APPROVE / EXECUTE |

### 1.3 Persistence (no new tables)

Operator records the above in a flat-file weekly log:
`docs/research/observation_log/YYYY-Www.md` (one file per ISO week,
free-form structured Markdown). **No DB schema change.** No migration.
Files are version-controlled like any other research note.

If a weekly snapshot is missed (job failure, holiday), the operator
records the gap with `STATE: NO_SNAPSHOT` and the reason. The next
week's review notes the gap.

---

## 2. Weekly Review Template

Saved per week as `docs/research/observation_log/YYYY-Www.md`:

```markdown
# V2 Weekly OOS Review — ISO YYYY-Www

**Snapshot date:** YYYY-MM-DD
**Snapshot id:** N
**Reviewer:** <operator name>
**Review timestamp:** YYYY-MM-DD HH:MM UTC
**Snapshot content hash:** <first 12 chars>
**Code version:** <git sha or release tag>
**Timezone in effect:** <SCHEDULER_TZ value>

## State

- **State:** <NOT_READY | SUSPENDED | WATCH | READY_FOR_REVIEW | STRONG_CANDIDATE | APPROVED_FOR_SHADOW_REPLACEMENT>
- **Prior state:** <state from previous snapshot>
- **Rollback reason:** <verbatim from snapshot row, or "—">

## Confidence

- **promotion_confidence:** 0.NN
- **basis_warnings:** [list, or empty]

## Edge summary

| Metric | Value |
|---|---|
| edge_bps | NN.NN |
| impact_weighted_edge | 0.NNNN |
| trend | UP / FLAT / DOWN / INSUFFICIENT |
| slope_bps_per_week | NN.NN |
| last_4w_avg_edge_bps | NN.NN |
| prior_4w_avg_edge_bps | NN.NN |

## Tail summary

| Metric | Value |
|---|---|
| tail_guard_triggered | true / false |
| tail_delta_p99_bps | NN.NN |
| tail_delta_p95_bps | NN.NN |
| stress regime — V2 p99 | NN.NN |
| stress regime — B2 p99 | NN.NN |
| directional regime — V2 p99 | NN.NN |
| directional regime — B2 p99 | NN.NN |

## Streaks

| Streak | Value | vs Prior week |
|---|---|---|
| verdict_streak | N | +1 / 0 / RESET |
| readiness_streak | N | +1 / 0 / RESET |
| streak_reset_count_last_8w | N | (informational) |

## Governance

- **approval_status:** NONE / ACTIVE / EXPIRING_SOON / EXPIRED / RESCINDED
- **days_until_expiry:** N (negative if expired)
- **snapshot_content_hash_match:** true / false
- **schema_version:** N

## Red flags

(verbatim from OOS monitoring report — do not edit)

| Code | Severity | Message |
|---|---|---|
| ... | ... | ... |

## Assessment

- **assessment:** NORMAL / WATCH / REVIEW_REQUIRED
- **recommended_action:** NONE / REVIEW / INVESTIGATE / DO_NOT_APPROVE

## Notes (operator free-form)

- <observation 1>
- <observation 2>

## Action taken this week (always non-execution)

- [ ] No action required (NORMAL)
- [ ] Reviewed report; no operator intervention
- [ ] Investigated red flag(s) — see notes
- [ ] No approval submitted (this week's gates do not authorize approval)
- [ ] Other (specify)

## Carry-forward to next week

- <items to watch>
```

**The "Action taken" checklist deliberately has no APPROVE / EXECUTE
options.** All approval activity flows through the existing
`/api/v2-promotion/approve` endpoint and is governed by Gate 8 — this
weekly review is informational only.

---

## 3. Red Flag Monitoring Plan

### 3.1 Per-flag tracking

For each of the 12 red flags defined in Phase 10B.2, maintain a
running count + escalation log in `docs/research/observation_log/red_flag_register.md`:

| Red flag code | Severity | Trigger count this window | First triggered | Last triggered | Pattern notes |
|---|---|---|---|---|---|
| TAIL_EMERGENCY | REVIEW | 0 | — | — | — |
| REPEATED_SUSPENDED | REVIEW | 0 | — | — | — |
| HIGH_CONF_FAILING_GATES | REVIEW | 0 | — | — | — |
| RAPID_ASCENT | WATCH | 0 | — | — | — |
| APPROVAL_EXPIRING_SOON | WATCH | 0 | — | — | — |
| APPROVAL_EXPIRED | WATCH | 0 | — | — | — |
| APPROVAL_HASH_MISMATCH | REVIEW | 0 | — | — | — |
| COMPARISON_HEALTH_DEGRADED | REVIEW | 0 | — | — | — |
| INSUFFICIENT_SAMPLE_PERSIST | WATCH | 0 | — | — | — |
| STREAK_RESET_FREQUENT | WATCH | 0 | — | — | — |
| CONFIDENCE_BASIS_WARNINGS | INFO | 0 | — | — | — |
| BUNDLE_SCHEMA_DOWNGRADE | INFO | 0 | — | — | — |

### 3.2 Escalation patterns to recognize

Concern thresholds (operator notices, does NOT act on automatically):

| Pattern | Concern level |
|---|---|
| Same flag fires ≥ 2 weeks running | **Watch** — note in next review |
| Severity escalation: WATCH → REVIEW for any flag in trailing 4w | **Watch** — log root cause hypothesis |
| Two distinct REVIEW-severity flags in same week | **Concern** — investigate before next snapshot |
| TAIL_EMERGENCY fires ≥ 2 times in 12 weeks | Already caught by REPEATED_SUSPENDED — confirm root cause + check if Phase 9A.1 force_reset / SUSPENDED behavior is operating as designed |
| APPROVAL_HASH_MISMATCH fires while state is APPROVED | **High concern** — evidence diverged from approval; investigate why snapshot recomputed |
| INSUFFICIENT_SAMPLE_PERSIST fires for ≥ 6 weeks | **Watch** — data accumulation slower than expected; revisit feasibility of 60–90 day window |
| STREAK_RESET_FREQUENT fires alongside DOWN edge trend | **Concern** — V2 verdict instability |
| COMPARISON_HEALTH_DEGRADED fires ≥ 1 week | **Concern** — investigate fetch reliability + scheduler health |

### 3.3 Tail-event clustering

Track the gap (in days) between successive tail events:
- `tail_guard_triggered = true` events
- SUSPENDED entries
- `tail_delta_p99_bps < -10` events (gate-failing, even if not emergency-grade)

Plot the gap series in the carry-forward notes. Clustering (e.g. 3
events within 30 days) is a flag for **interpretation**, not action.
The framework's response (SUSPENDED + force_reset) is already correct;
operator just notes the pattern.

### 3.4 Approval expiry behavior tracking

For each APPROVE row written during the window:

| Approval id | snapshot_id | approver | approved_at | expired_at (if observed) | rescinded? | hash_match_at_expiry? |
|---|---|---|---|---|---|---|

If approval expiry happens silently (no operator re-approval) more
than 3 times in 90 days, that's a signal that the 14-day window is
operationally tight. **Do not change the window** during the
observation period — record the pattern and address in a future design
review.

---

## 4. OOS Data Sufficiency Criteria

Phase 9B.1 already locked these floors. The observation window's
**informational** sufficiency check (operator-side, NOT gate-side):

| Criterion | Phase 9 gate threshold | Operator-side "meaningful OOS" interpretation |
|---|---:|---|
| OOS days since FRAMEWORK_IMPLEMENTATION_DATE (2026-04-25) | ≥ 60 (Gate 1) | ≥ 60: Gate 1 may pass. Operator records this milestone. ≥ 90: stronger evidence. |
| Joined shadow days in current snapshot | ≥ 60 (Gate 1) | Mirror of gate; recorded as plain count |
| Divergent days | ≥ 30 (Gate 1), ≥ 50 (Gate 4 internal sample guard) | Two milestones: 30 = Gate 1 passes; 50 = Gate 4 tail-claim sample guard passes |
| `n_b2_flat_v2_long` | ≥ 10 (Gate 1) | Specific divergence-class count |
| Tail observations (`tail.b2.n` and `tail.v2.n`) | > 250 (Gate 4 internal) | Operationally meaningful tail estimates require ≥ 250 |
| Regime coverage | None encoded in gates | Operator manually inspects: did all 3 regimes (STRESS / DIRECTIONAL / NEUTRAL) appear in the window? Concentrated regime exposure is a confound, not a system fault. |
| Stability | Phase 9 stability gate (both halves > 0) | Mirror; recorded |

### 4.1 Promotion-readiness gate-checking is automatic

The operator does NOT need to compute these against thresholds — the
snapshot job does it. The operator notes whether each gate passed or
failed in the weekly review. This plan does not introduce new sample
thresholds.

### 4.2 "Meaningful OOS" milestones to mark

Mark in the observation_log when each is first reached:

- `OOS_60_DAYS` — Gate 1 OOS floor crossed
- `DIVERGENT_30` — Gate 1 divergent-day floor crossed
- `DIVERGENT_50` — Gate 4 tail-claim floor crossed
- `TAIL_N_250` — both b2.n and v2.n surpass tail-claim observation floor
- `OOS_90_DAYS` — observation-window minimum target reached
- `ALL_REGIMES_OBSERVED` — all 3 regime labels appeared in the window

These milestones are **informational checkpoints**, not actions.
Reaching them does NOT trigger promotion or any framework change.

---

## 5. Statistical Validation Usage (10A)

The Phase 10A.2 module is implemented but **not invoked** by the
governance layer. During the observation window, the operator
optionally invokes it for **interpretation only**.

### 5.1 When to start using each function

| Function | Earliest meaningful call | Pre-condition | Caveat |
|---|---|---|---|
| `bootstrap_ci(divergence_deltas)` | When ≥ 60 divergent days observed | `len(divergence_deltas) >= 60` | iid percentile bootstrap; CI may understate uncertainty for autocorrelated returns. Use lower bound, not point estimate, for evaluation. |
| `compute_deflated_sharpe(divergence_deltas, n_trials=N)` | When ≥ 60 divergent days observed | Same; also requires honest `n_trials` (number of variants compared in selecting V2 — minimum is 5 per `B2_V2_PERSIST3_UPDATE.md`) | DSR is an information-only diagnostic; not a gate |
| `compute_pbo(return_matrix=...)` | When `T ≥ 200` rows of joined paper_shadow_log accumulated | Module returns INSUFFICIENT_SAMPLE if T < 200 | Requires constructing a multi-variant return matrix from candidates documented in prior research; non-trivial setup. Defer until OOS_90_DAYS milestone. |
| `compute_stat_validation(...)` | All of the above pre-conditions met | n/a | Returns full bundle; warnings list flags partial coverage |

### 5.2 How to use the outputs

| Output | Operator interpretation |
|---|---|
| `pbo.overfit_risk == "LOW"` | Mild positive signal; persist-3 selection not obviously noise-driven over the joined sample. **Does NOT override Phase 9 gates.** |
| `pbo.overfit_risk == "MEDIUM"` | Concern; persist-3 may be partly overfit. Note in observation_log; do not act. |
| `pbo.overfit_risk == "HIGH"` | Strong concern; consider whether continued shadow operation is worth the data cost. Still does NOT change governance. |
| `deflated_sharpe.is_significant == True` | V2 edge survives multiple-trials adjustment. Informational. |
| `deflated_sharpe.is_significant == False` AND DSR sample sufficient | Edge does NOT survive multiple-trials adjustment. **Strong concern.** Operator notes in observation_log; framework continues to evaluate per Phase 9 gates. Operator should NOT approve V2 promotion in this state even if Gate 8 conditions are met. |
| `bootstrap_ci.avg_return_diff_1d_bps.ci_low > 0` | 90% lower-bound on edge is positive; supportive evidence. |
| `bootstrap_ci.avg_return_diff_1d_bps.ci_low ≤ 0` | Edge cannot be statistically distinguished from zero at 90%. **Operator should NOT approve.** |
| Any `INSUFFICIENT_SAMPLE` warning | Sample too thin; ignore that sub-result. |

### 5.3 What stat-validation output does NOT do

- Does NOT change any gate threshold
- Does NOT advance or rollback state
- Does NOT modify any approval row
- Does NOT trigger any job
- Does NOT appear in `comparison_bundle_json` (per Phase 10A.2 design — opt-in
  flag was deferred and remains so during this observation window)

The operator computes stat_validation manually when needed, records
outputs in the observation_log, and uses them only for interpretation.

---

## 6. Promotion Readiness Interpretation (NOT ACTION)

### 6.1 Signals to recognize

| Signal | What it means | What to do |
|---|---|---|
| State reaches **STRONG_CANDIDATE** for first time | Gates 1–7 + verdict streak ≥ 4 + readiness streak ≥ 2 + confidence ≥ 0.70 all hold | **Note milestone in observation_log.** Do nothing else. |
| Confidence ≥ 0.80 sustained for 4+ weeks | Stronger-than-threshold confidence; supports Gates 1–7 passing comfortably | **Note in observation_log.** Continue observation. |
| Edge trend = UP for 4+ weeks consecutive | Slope-positive edge across last 8 weeks | **Note in observation_log.** Verify that streak_reset_count_last_8w is 0 to rule out noise. |
| `pbo.overfit_risk == "LOW"` AND DSR significant AND bootstrap CI lower bound > 0 | All three statistical-validation diagnostics align with positive evidence | **Strong informational signal.** Note in observation_log. Continue observation; statistical alignment alone is not approval. |
| All 3 regimes observed in window | Regime coverage criterion (§4.2) met | **Note milestone.** Reduces single-regime concentration risk. |

### 6.2 What the operator does NOT do in response

- ❌ Approve V2 (does not bypass operator approval workflow if Gate 8 itself is satisfied — but during the observation window, the operator's discipline is to defer approval EVEN IF Gate 8 conditions hold)
- ❌ Adjust any Phase 9 threshold to "lock in" favorable results
- ❌ Add new gates or remove existing ones
- ❌ Change the SUSPENDED → NOT_READY transition (it's RESUME-only)
- ❌ Implement Phase 10C.2 or any ML
- ❌ Modify the OOS monitoring report or red flag definitions
- ❌ Skip a weekly review because results look good

### 6.3 Operator approval discipline during observation window

If Gate 8 conditions are met (Phase 9 gates pass + operator wants to
approve), the operator MAY still approve — Phase 9's gates are the
formal authorization. **However, the recommended discipline during
this 60–90 day observation window is: defer approval until the window
closes, then re-evaluate.** Reasoning:

1. The 60–90 day window is specifically designed to gather OOS evidence
   under the new Phase 9B.1 thresholds.
2. Approving mid-window collapses observation into action and
   forecloses the option of using the full window's evidence.
3. The framework allows approval at any time if Gate 8 is satisfied;
   the operator's choice to defer is a *discipline*, not a code-level
   constraint.

If exceptional circumstances justify mid-window approval, the operator
documents the rationale in the observation_log and proceeds via the
existing `/api/v2-promotion/approve` flow.

---

## 7. ML Readiness Criteria (for future Phase 10C.2)

ML implementation **may be reconsidered** only after **all** of the
following hold simultaneously, evaluated at the end of the 60–90 day
observation window:

| # | Criterion | Threshold | Source |
|---|---|---|---|
| 1 | OOS days accumulated | ≥ 60 (target ≥ 90) | Operator log |
| 2 | Stable edge behavior — no edge sign reversal week-over-week in trailing 8 weeks | Operator inspection of `edge.trend` series | Weekly review |
| 3 | Acceptable tail profile — zero TAIL_EMERGENCY events in trailing 12 weeks | Red flag register | Weekly review |
| 4 | PBO via CSCV — `overfit_risk == "LOW"` | Phase 10A.2 module output | Stat validation log |
| 5 | DSR significant — `is_significant == True` AND `n_trials` honestly accounts for all variants compared in V2 selection | Phase 10A.2 module | Stat validation log |
| 6 | Bootstrap CI on edge — lower bound > 0 at 90% | Phase 10A.2 module | Stat validation log |
| 7 | No unresolved REVIEW-severity red flag in latest snapshot | OOS monitoring | Weekly review |
| 8 | All 3 regimes observed in window | Operator inspection | Observation log |
| 9 | Comparison framework health: no `COMPARISON_HEALTH_DEGRADED` flag in trailing 12 weeks | Red flag register | Weekly review |
| 10 | No schema_version downgrade | Snapshot row inspection | Weekly review |

If **any** of the 10 criteria fails, ML implementation is deferred for
another full observation window (60 days). The operator documents
which criteria failed and why.

If **all 10** hold, the operator may convene a separate review to
decide whether to revisit Phase 10C.2's design (last reviewed 2026-04-26)
and potentially proceed with implementation. Re-design + re-approval
of Phase 10C.1 is required before any Phase 10C.2 code is written —
the design doc may need updates based on what the observation window
revealed.

**ML remains disabled and unimplemented until ALL 10 criteria are met
AND a separate explicit operator decision approves Phase 10C.2.**

`ML_CAN_AFFECT_TRADES = false` remains permanent regardless of any
of the above.

---

## 8. What NOT to do (explicit prohibitions)

This list is binding for the duration of the observation window.

### Code prohibitions

- ❌ **No threshold tuning.** All Phase 9 gate constants frozen. Touching `GATE1_MIN_OOS_DAYS`, `GATE3_MIN_EDGE_BPS`, `GATE4_MIN_DIVERGENT_DAYS_FOR_TAIL`, `GATE5_REGIME_CONCENTRATION_MAX`, `TAIL_EMERGENCY_P99_DELTA_HARD_BPS`, `APPROVAL_STALENESS_DAYS`, etc. is forbidden.
- ❌ **No new gates.** The 8-gate framework is complete.
- ❌ **No state machine changes.** No new states; no transition rule edits; no rollback rule edits.
- ❌ **No strategy modifications.** B2 / V2 / Engine A / Engine B byte-identical.
- ❌ **No ML implementation.** Phase 10C.2 not started.
- ❌ **No execution changes.** `ENGINE_B_MODE`, `engine_b_router`, `paper_trade_log` writers, `decision_log` writers — all unchanged.
- ❌ **No comparison framework changes.** `compute_all` byte-identical (no opt-in `include_stat_validation` flag activated).
- ❌ **No snapshot job changes.** `run_v2_promotion_snapshot` byte-identical.
- ❌ **No OOS monitoring changes.** `v2_oos_monitoring.py` byte-identical (do not add red flags, do not change severities).
- ❌ **No statistical validation changes.** `v2_stat_validation.py` byte-identical (do not lower `DEFAULT_MIN_SAMPLE`, do not change `DEFAULT_PBO_OVERFIT_HIGH`).
- ❌ **No new API routes.** `/api/v2-promotion/*` and `/api/b2-v2/*` are the complete surface.
- ❌ **No new UI panels.** `V2PromotionTriggerCard` and `B2vsV2ComparisonCard` are the complete surface (no `MLAdvisoryCard`, no `OOSReportCard`).
- ❌ **No new database migrations.** Schema frozen at 046.
- ❌ **No new scheduled jobs.** Only `v2_promotion_snapshot` runs weekly.
- ❌ **No `ML_CAN_AFFECT_TRADES = true`.** Permanent kill switch stays false.

### Process prohibitions

- ❌ **No operator approval purely because Gate 8 conditions hold.** Discipline: defer until end of window.
- ❌ **No skipping a weekly review.** Even quiet weeks are recorded.
- ❌ **No deleting / editing prior weeks' observation_log entries.** Append-only research record.
- ❌ **No "informally" acting on red flags.** Document, do not act.
- ❌ **No invocation of `compute_stat_validation` to "see what it would say"** before sample sufficiency criteria are met. Module returns INSUFFICIENT_SAMPLE; respect that.
- ❌ **No premature ML implementation** even if the operator personally believes ML would help. Phase 10C.2 design exists; that's the artifact. Code is gated on §7 criteria + separate explicit approval.
- ❌ **No "we've seen enough" early termination of the window.** 60 days is the floor; 90 days is the target. Mid-window termination requires a documented rationale (e.g. catastrophic system failure outside V2 scope).

### Allowed actions

- ✅ Weekly snapshot job runs (already scheduled)
- ✅ Operator runs weekly review against the template
- ✅ Operator updates `observation_log/YYYY-Www.md` files
- ✅ Operator updates `observation_log/red_flag_register.md`
- ✅ Operator manually invokes `compute_stat_validation(...)` after sample sufficient
- ✅ Operator pulls existing API endpoints for inspection
- ✅ Operator may approve V2 via `/api/v2-promotion/approve` IF AND ONLY IF Gate 8 conditions hold AND operator decides discipline does not require deferral (rationale documented in observation_log)
- ✅ Operator may rescind via `/api/v2-promotion/rescind` if a prior approval needs to be undone
- ✅ Operator may submit `RESUME_FROM_SUSPENDED` via `/api/v2-promotion/resume-from-suspended` if a SUSPENDED state needs to be cleared (rationale documented)
- ✅ Bug fixes outside the V2 / governance scope are allowed (other parts of the platform may evolve independently)

---

## 9. End-of-window decision matrix

At day 60 (minimum) or day 90 (target), operator runs the §7 ML
readiness criteria check. Possible outcomes:

| Outcome | Action |
|---|---|
| All 10 criteria pass + operator wants to revisit Phase 10C.2 | Re-open Phase 10C.1 design doc; review whether observation revealed feature/target changes; if yes, revise design then implement; if no, proceed to Phase 10C.2 implementation under a fresh explicit approval |
| Some criteria pass; some don't; operator wants more data | Extend observation by another 60 days; document which criteria failed and what additional evidence is needed |
| Critical issue surfaced (REVIEW-severity flags persisting) | Convene framework-level review; may require Phase 11 (gate revision) — separate design + approval cycle |
| Edge / V2 strategy looks broken | Convene strategy-level review; may require V2 model revision or rollback to B2-only — separate design + approval cycle |
| Operator chooses to approve V2 at end of window | Submit operator approval via existing API; framework advances to APPROVED_FOR_SHADOW_REPLACEMENT on next snapshot. ML still NOT implemented. ML_CAN_AFFECT_TRADES remains false. |

**No outcome of the observation window leads to ML implementation
without re-doing the §7 check + a separate explicit decision.**

---

## 10. Discipline summary

For 60–90 days starting now:

> **Watch. Record. Do not act.**

The framework is doing its job. The operator's job during this window
is to verify — through structured weekly reviews — that the framework's
behavior matches what was designed. The temptation to "improve" or
"optimize" or "add ML" is the failure mode this window is specifically
designed to resist. The discipline is the work.

---

## Appendix A — Files added by this plan

| File | Type | Purpose |
|---|---|---|
| `docs/research/V2_OBSERVATION_VALIDATION_PLAN.md` | NEW (this doc) | Plan + runbook |
| `docs/research/observation_log/` | NEW directory | Container for weekly review files |
| `docs/research/observation_log/README.md` | NEW (will write below) | Index + how-to-use |
| `docs/research/observation_log/red_flag_register.md` | NEW (will write below) | Running red-flag tracking table |
| `docs/research/observation_log/template.md` | NEW (will write below) | Copy-paste template for weekly reviews |

**No source code changes. No tests changes. No DB schema changes. No
worker / scheduler / API / UI changes.**

## Appendix B — Plan does NOT change

- `apps/api/src/research/v2_promotion_gates.py` — unchanged
- `apps/api/src/research/v2_promotion_state.py` — unchanged
- `apps/api/src/research/b2_v2_comparison.py` — unchanged
- `apps/api/src/research/v2_stat_validation.py` — unchanged
- `apps/api/src/research/v2_oos_monitoring.py` — unchanged
- `apps/api/src/api/v2_promotion.py` — unchanged
- `apps/api/src/api/b2_v2_comparison.py` — unchanged
- `apps/worker/src/jobs/v2_promotion_snapshot.py` — unchanged
- `apps/worker/src/jobs/registry.py` — unchanged
- `scripts/seed_symbols.py` — unchanged
- `apps/web/src/components/ops/V2PromotionTriggerCard.tsx` — unchanged
- `apps/web/src/components/ops/B2vsV2ComparisonCard.tsx` — unchanged
- All migrations 001–046 — unchanged
- `settings.ML_CAN_AFFECT_TRADES` — false (permanent)

`SAFE_TO_CONTINUE_OBSERVING`
