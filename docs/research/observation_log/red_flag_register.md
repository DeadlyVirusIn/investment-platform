# Red Flag Register — V2 Observation Window

Running count + escalation log per red flag for the 60–90 day OOS
observation window beginning **2026-04-26**.

## Per-flag tracking

| Red flag code | Severity | Trigger count this window | First triggered (week) | Last triggered (week) | Pattern notes |
|---|---|---:|---|---|---|
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

## Escalation log

(append-only; one entry per escalation event observed)

### Escalation event template

```
**Date:** YYYY-MM-DD (ISO YYYY-Www)
**Flag:** <code>
**Pattern:** <e.g. "fired 2 weeks running" / "WATCH → REVIEW">
**Hypothesized root cause:** <free text>
**Action:** <"noted only" / "investigated — see week file" / etc.>
```

## Tail-event clustering log

(record gap days between successive `tail_guard_triggered = true`
events OR SUSPENDED entries OR `tail_delta_p99_bps < -10` events)

| Event | ISO week | tail_delta_p99_bps | Days since prior tail event |
|---|---|---|---|
| — | — | — | — |

## Approval expiry behavior log

(one row per APPROVE submitted during the window)

| Approval id | snapshot_id | approver | approved_at | expired_at (if observed) | rescinded? | hash_match_at_expiry? |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

## Concern thresholds (for reference)

(from §3.2 of `V2_OBSERVATION_VALIDATION_PLAN.md` — operator notices, does NOT act)

- Same flag fires ≥ 2 weeks running → **Watch**
- Severity escalation: WATCH → REVIEW for any flag in trailing 4w → **Watch**
- Two distinct REVIEW-severity flags in same week → **Concern**
- TAIL_EMERGENCY ≥ 2 in 12 weeks (also caught by REPEATED_SUSPENDED)
- APPROVAL_HASH_MISMATCH while state is APPROVED → **High concern**
- INSUFFICIENT_SAMPLE_PERSIST ≥ 6 weeks → **Watch**
- STREAK_RESET_FREQUENT alongside DOWN edge trend → **Concern**
- COMPARISON_HEALTH_DEGRADED ≥ 1 week → **Concern**
- ≥ 3 silent approval expiries in 90 days → operationally tight 14-day window — note for future design review (do NOT change during this window)
