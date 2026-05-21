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

## Statistical validation diagnostics (when sample sufficient)

(invoke `compute_stat_validation(...)` only after `OOS_60_DAYS` milestone reached)

| Diagnostic | Value | Notes |
|---|---|---|
| pbo.overfit_risk | LOW / MEDIUM / HIGH / INSUFFICIENT_SAMPLE | |
| pbo.pbo_score | 0.NN | |
| deflated_sharpe.deflated_sharpe | N.NN | |
| deflated_sharpe.is_significant | true / false | |
| deflated_sharpe.n_trials supplied | N | (honest count of variants compared) |
| bootstrap_ci.avg_return_diff_1d_bps.ci_low | NN.NN | |
| bootstrap_ci.avg_return_diff_1d_bps.ci_high | NN.NN | |
| bootstrap_ci.impact_weighted_edge.ci_low | 0.NNNN | |

## Assessment

- **assessment:** NORMAL / WATCH / REVIEW_REQUIRED
- **recommended_action:** NONE / REVIEW / INVESTIGATE / DO_NOT_APPROVE

## Milestones reached this week (informational)

- [ ] OOS_60_DAYS — Gate 1 OOS floor crossed
- [ ] DIVERGENT_30 — Gate 1 divergent-day floor crossed
- [ ] DIVERGENT_50 — Gate 4 tail-claim sample-guard floor crossed
- [ ] TAIL_N_250 — both b2.n and v2.n surpass tail-claim observation floor
- [ ] OOS_90_DAYS — observation-window minimum target reached
- [ ] ALL_REGIMES_OBSERVED — all 3 regime labels appeared in window

## Notes (operator free-form)

- <observation 1>
- <observation 2>

## Action taken this week (always non-execution)

- [ ] No action required (NORMAL)
- [ ] Reviewed report; no operator intervention
- [ ] Investigated red flag(s) — see notes
- [ ] No approval submitted (deferring per observation-window discipline)
- [ ] Approval submitted (rationale + Gate 8 confirmation in notes)
- [ ] Other (specify)

## Carry-forward to next week

- <items to watch>
