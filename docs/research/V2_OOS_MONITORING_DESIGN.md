# V2 OOS Monitoring Report Layer — Design (Phase 10B.1)

**Date:** 2026-04-26
**Status:** DESIGN ONLY — awaiting approval before Phase 10B.2 implementation
**Scope:** Pure read-only weekly reporting. NO impact on execution, gates,
state machine, approval, sizing, routing, or scheduler. NO ML inputs.

---

## TL;DR

A new pure-function module `apps/api/src/research/v2_oos_monitoring.py` that
produces a per-week JSON report from existing `v2_promotion_snapshot` +
`v2_promotion_approval` data. Reports surface red flags, trend movement,
and an `NORMAL | WATCH | REVIEW_REQUIRED` assessment that an operator can
glance at on Monday morning. **The report is informational only.** It
never recommends approval, never triggers jobs, never recomputes gates,
never depends on ML.

---

## Hard Boundaries (mirror Phase 10B instructions)

| Constraint | Enforcement |
|---|---|
| No live execution change | Module imports stdlib + sqlalchemy READ-ONLY (Session.scalar/scalars) |
| No strategy logic change | No imports of `shadow_strategy*`, `engine_b*` |
| No gate / state-machine / approval coupling | No imports of `v2_promotion_gates`, `v2_promotion_state` (constants for state-name comparison may be re-exported as a frozen tuple, OR copied as local constants — design choice in §11) |
| No recomputation | All numeric values come from snapshot row fields verbatim; never re-evaluates gates / state / confidence |
| No ML | No imports of any ML module; no model invocation |
| Read-only | SELECT only; no INSERT / UPDATE / DELETE |
| No scheduler trigger | Module never invokes `run_v2_promotion_snapshot` or any worker job |

Verified after implementation by:
```bash
git grep -E "INSERT|UPDATE|DELETE|session\.add|session\.commit" \
    apps/api/src/research/v2_oos_monitoring.py
# expected: zero matches
git grep -E "ml_|run_v2_promotion_snapshot|engine_b_router|paper_trade_log" \
    apps/api/src/research/v2_oos_monitoring.py
# expected: only docstring mentions
```

---

## Data Sources (read-only)

### Primary: `v2_promotion_snapshot` (Phase 1 + 9A schema)

Fields consumed verbatim:
- `id`, `as_of_date`, `iso_year`, `iso_week`
- `state`, `prior_state`, `rollback_reason`
- `promotion_confidence`, `verdict_streak`, `readiness_streak`
- `comparison_bundle_json` — extracts:
  - `verdict.verdict`, `verdict.readiness`, `verdict.confidence`
  - `verdict.tail_guard_triggered`
  - `metrics.avg_return_diff_1d_bps`, `metrics.impact_weighted_edge`, `metrics.n_divergent_days`
  - `tail_by_regime` (Phase 9B.3) when present
- `gates_json` — extracts:
  - `gates[*].passed`, `gates[*].name`, `gates[*].reason`
  - `confidence_breakdown.basis_warnings` (Phase 9B.2)
  - `comparison_fetch_ok`
- `snapshot_content_hash`, `schema_version`, `code_version`, `evaluated_at_utc`, `timezone` (Phase 9A)

### Secondary: `v2_promotion_approval` (read-only)

For approval-staleness context:
- `decision`, `approver`, `rationale`, `approved_at`
- `snapshot_content_hash_at_approval` (Phase 9A.3)

### Optional (v1 NOT required): `stat_validation` bundle (Phase 10A.2)

If `comparison_bundle_json["stat_validation"]` exists (it does NOT in v1
since the opt-in `compute_all` integration was deferred), the report
exposes its `pbo_score`, `deflated_sharpe`, and `bootstrap_ci.*` fields
verbatim. v1 design treats absence as expected; never raises.

### Out of scope

- `paper_shadow_log` — never queried directly
- `paper_trade_log`, `decision_log`, `position_snapshot`, etc. — never queried
- ML scoring tables — never queried
- External APIs — never called

---

## Module Layout

```
apps/api/src/research/v2_oos_monitoring.py
apps/api/tests/unit/test_v2_oos_monitoring.py        (deterministic, no DB)
apps/api/tests/integration/test_v2_oos_monitoring.py (Postgres testcontainer; read-only)
```

Single source-file module; no subdirectory. Two test files:
- Unit: pure-function tests over hand-built snapshot dicts
- Integration: read-only DB queries against seeded snapshot rows

---

## Public API

```python
# Frozen module constants — no operator tuning
TREND_LOOKBACK_WEEKS = 4
TREND_PRIOR_WEEKS = 4
EDGE_TREND_DEAD_ZONE_BPS = 0.5
RAPID_ASCENT_MAX_WEEKS = 5      # NOT_READY → STRONG_CANDIDATE in ≤ N weeks
APPROVAL_EXPIRY_WARN_DAYS = 4
INSUFFICIENT_SAMPLE_PERSIST_WEEKS = 3   # consecutive weeks → red flag
SUSPENDED_REPEAT_WINDOW_WEEKS = 12
SUSPENDED_REPEAT_THRESHOLD = 2  # 2 SUSPENDED entries within 12 weeks → red

REPORT_SCHEMA_VERSION = 1


# Result dataclasses (frozen, JSON-serializable)

@dataclass(frozen=True)
class EdgeReport:
    edge_bps: float | None
    impact_weighted_edge: float | None
    trend: str          # "UP" | "FLAT" | "DOWN"
    last_4w_avg_edge_bps: float | None
    prior_4w_avg_edge_bps: float | None
    slope_bps_per_week: float | None


@dataclass(frozen=True)
class TailReport:
    tail_guard_triggered: bool
    tail_delta_p99_bps: float | None
    tail_delta_p95_bps: float | None
    tail_by_regime_present: bool


@dataclass(frozen=True)
class StreaksReport:
    verdict_streak: int
    readiness_streak: int
    streak_reset_count_last_8w: int


@dataclass(frozen=True)
class GovernanceReport:
    approval_status: str            # NONE | ACTIVE | EXPIRING_SOON | EXPIRED | RESCINDED
    days_until_expiry: int | None
    is_stale: bool
    snapshot_content_hash_match: bool   # current snapshot hash matches latest approval
    code_version: str | None
    timezone: str | None
    schema_version: int | None


@dataclass(frozen=True)
class RedFlag:
    code: str           # e.g. "TAIL_EMERGENCY", "STALE_APPROVAL"
    severity: str       # "INFO" | "WATCH" | "REVIEW"
    message: str


@dataclass(frozen=True)
class WeeklyOOSReport:
    schema_version: int
    week: str                     # "YYYY-Www"
    as_of_date: str               # ISO
    snapshot_id: int
    state: str
    confidence: float
    confidence_basis: tuple[str, ...]
    edge: EdgeReport
    tail: TailReport
    streaks: StreaksReport
    governance: GovernanceReport
    assessment: str               # "NORMAL" | "WATCH" | "REVIEW_REQUIRED"
    red_flags: tuple[RedFlag, ...]
    notes: tuple[str, ...]


# Top-level entry points

def build_weekly_report(
    *,
    snapshot: V2PromotionSnapshot,
    prior_snapshots: list[V2PromotionSnapshot],   # newest-last, ≥ 8 weeks ideal
    approvals_for_snapshot: list[V2PromotionApproval],
) -> WeeklyOOSReport:
    """Pure function; no DB access. Builds the report from supplied rows.

    `prior_snapshots` should be the trailing N (≤16) snapshots PRECEDING
    `snapshot` (i.e. excluding the current one), oldest-first."""
    ...


def fetch_and_build_weekly_report(
    session: Session,
    *,
    snapshot_id: int | None = None,        # None → latest
    history_window_weeks: int = 16,
) -> WeeklyOOSReport | None:
    """Convenience read-only wrapper. SELECT-only DB I/O; no writes."""
    ...
```

All non-DB functions are **pure**. Determinism: given the same snapshot
inputs, output is byte-identical.

---

## Trend Logic

All derivations are pure post-hoc reads of stored snapshot fields. No
recomputation of gates, state, or confidence.

### Edge slope (`edge.trend`)

```
last_4 = mean(metrics.avg_return_diff_1d_bps for last 4 prior_snapshots)
prior_4 = mean(metrics.avg_return_diff_1d_bps for prior 4 snapshots before that)
delta = last_4 - prior_4
trend = "UP"   if delta >  EDGE_TREND_DEAD_ZONE_BPS
trend = "DOWN" if delta < -EDGE_TREND_DEAD_ZONE_BPS
trend = "FLAT" otherwise
slope_bps_per_week = (last_4 - prior_4) / 4    (rough estimate; no regression in v1)
```

Insufficient history (< 8 prior snapshots): trend = `"INSUFFICIENT"`,
slope = `None`, no red flag (just informational).

### Streak reset frequency (`streaks.streak_reset_count_last_8w`)

Counts transitions where `verdict_streak` decreased week-over-week
across the last 8 prior snapshots. High counts indicate noisy verdict
behavior — surfaces as a WATCH-level red flag if ≥ 3.

### Tail stability

Tracked via `tail_by_regime_present` flag (Phase 9B.3 schema). v1 does
not compute tail-instability metrics — operator inspects the snapshot
bundle directly via the existing `/api/v2-promotion/gates` endpoint.
Future v2 may add per-regime tail trend.

---

## Red-flag definitions

Each red flag has a fixed `code`, `severity` (INFO / WATCH / REVIEW),
and a human-readable `message` template. Severity rolls up to the
report's `assessment` field per §Assessment Classification.

| Code | Trigger | Severity | Message template |
|---|---|---|---|
| `TAIL_EMERGENCY` | `state == "SUSPENDED"` AND `rollback_reason` contains "emergency" | REVIEW | `Tail emergency triggered SUSPENDED on {as_of_date}: {rollback_reason}` |
| `REPEATED_SUSPENDED` | ≥ `SUSPENDED_REPEAT_THRESHOLD` distinct SUSPENDED entries in trailing `SUSPENDED_REPEAT_WINDOW_WEEKS` snapshots | REVIEW | `{count} SUSPENDED events in last {window}w — investigate underlying tail risk` |
| `HIGH_CONF_FAILING_GATES` | `confidence ≥ 0.70` AND any of `gates[1..7].passed == false` | REVIEW | `Confidence {conf:.2f} ≥ 0.70 but {n_failed_gates} gate(s) failing: {failed_gate_names}` |
| `RAPID_ASCENT` | First STRONG_CANDIDATE reached within ≤ `RAPID_ASCENT_MAX_WEEKS` of first NOT_READY in same hash chain | WATCH | `STRONG_CANDIDATE reached in {weeks} weeks (rapid); double-check OOS depth` |
| `APPROVAL_EXPIRING_SOON` | `governance.days_until_expiry` ≤ `APPROVAL_EXPIRY_WARN_DAYS` AND > 0 | WATCH | `Approval expires in {days} day(s); operator action required to retain APPROVED state` |
| `APPROVAL_EXPIRED` | `governance.days_until_expiry` ≤ 0 AND no fresh approve | WATCH | `Approval staleness window passed; state will degrade on next snapshot` |
| `APPROVAL_HASH_MISMATCH` | `snapshot_content_hash_at_approval != snapshot.snapshot_content_hash` | REVIEW | `Active approval references stale snapshot hash; evidence has changed since approval` |
| `COMPARISON_HEALTH_DEGRADED` | `comparison_fetch_ok == false` on current OR ≥ 2 of last 7 snapshots | REVIEW | `Comparison framework health degraded ({n_failures}/7 fetches failed)` |
| `INSUFFICIENT_SAMPLE_PERSIST` | Any gate failed with `INSUFFICIENT_*` reason for ≥ `INSUFFICIENT_SAMPLE_PERSIST_WEEKS` consecutive snapshots | WATCH | `Insufficient sample persists for {weeks}w; data accumulation slower than expected` |
| `STREAK_RESET_FREQUENT` | Streak reset count in last 8w ≥ 3 | WATCH | `Verdict streak reset {count} times in last 8w; underlying signal is noisy` |
| `CONFIDENCE_BASIS_WARNINGS` | `confidence_breakdown.basis_warnings` non-empty | INFO | `Confidence components flagged as vacuously high: {warnings_summary}` |
| `BUNDLE_SCHEMA_DOWNGRADE` | `schema_version` < latest known | INFO | `Snapshot bundle schema {v} behind latest known; expected fields may be missing` |

Triggers evaluate against:
- The current snapshot's stored fields
- The trailing N prior snapshots (no recomputation)
- The approval table for the current snapshot (read-only)

**No red flag triggers a state mutation. None of them recommend
approval. None invoke any execution surface.**

---

## Assessment Classification

```
if any red_flag.severity == "REVIEW":
    assessment = "REVIEW_REQUIRED"
elif any red_flag.severity == "WATCH":
    assessment = "WATCH"
else:
    assessment = "NORMAL"
```

Reported alongside `recommended_action`, which is one of:
- `NONE` — assessment NORMAL
- `REVIEW` — assessment WATCH; operator should glance at the report
- `INVESTIGATE` — assessment REVIEW_REQUIRED; operator should open the snapshot's gate detail
- `DO_NOT_APPROVE` — overrides REVIEW when state is already STRONG_CANDIDATE and a REVIEW-severity flag exists

**Never `APPROVE` or `EXECUTE` in any code path.** Only the existing
operator approval API (`POST /api/v2-promotion/approve`) can express
operator approval — the report has no opinion.

---

## Output format

JSON only in v1. Schema:

```json
{
  "schema_version": 1,
  "week": "2026-W21",
  "as_of_date": "2026-05-18",
  "snapshot_id": 42,
  "state": "STRONG_CANDIDATE",
  "confidence": 0.85,
  "confidence_basis": [],
  "edge": {
    "edge_bps": 12.0,
    "impact_weighted_edge": 0.10,
    "trend": "UP",
    "last_4w_avg_edge_bps": 11.5,
    "prior_4w_avg_edge_bps": 8.0,
    "slope_bps_per_week": 0.875
  },
  "tail": {
    "tail_guard_triggered": false,
    "tail_delta_p99_bps": -2.0,
    "tail_delta_p95_bps": 0.0,
    "tail_by_regime_present": true
  },
  "streaks": {
    "verdict_streak": 5,
    "readiness_streak": 3,
    "streak_reset_count_last_8w": 0
  },
  "governance": {
    "approval_status": "ACTIVE",
    "days_until_expiry": 9,
    "is_stale": false,
    "snapshot_content_hash_match": true,
    "code_version": "0.1.0",
    "timezone": "UTC",
    "schema_version": 2
  },
  "assessment": "NORMAL",
  "red_flags": [],
  "notes": [],
  "recommended_action": "NONE"
}
```

Future optional surfaces (out of scope for v1):
- `GET /api/v2-promotion/oos-report?snapshot_id=...` (read-only)
- UI panel rendering the report verbatim (no client-side recomputation)
- Saved-report append-only table (only if explicitly designed; v1 stays pure-fn)

---

## Example reports

### Example 1 — NORMAL (clean STRONG_CANDIDATE progression)

```json
{
  "week": "2026-W21",
  "state": "STRONG_CANDIDATE",
  "confidence": 0.85,
  "edge": {"edge_bps": 12.0, "trend": "UP", "slope_bps_per_week": 0.5, ...},
  "streaks": {"verdict_streak": 5, "readiness_streak": 3, "streak_reset_count_last_8w": 0},
  "governance": {"approval_status": "NONE", "is_stale": false, "snapshot_content_hash_match": true, ...},
  "assessment": "NORMAL",
  "red_flags": [],
  "recommended_action": "NONE"
}
```

### Example 2 — WATCH (approval expiring + insufficient sample persist)

```json
{
  "week": "2026-W34",
  "state": "APPROVED_FOR_SHADOW_REPLACEMENT",
  "confidence": 0.92,
  "governance": {
    "approval_status": "EXPIRING_SOON",
    "days_until_expiry": 3,
    "is_stale": false,
    "snapshot_content_hash_match": true,
    ...
  },
  "assessment": "WATCH",
  "red_flags": [
    {
      "code": "APPROVAL_EXPIRING_SOON",
      "severity": "WATCH",
      "message": "Approval expires in 3 day(s); operator action required to retain APPROVED state"
    },
    {
      "code": "INSUFFICIENT_SAMPLE_PERSIST",
      "severity": "WATCH",
      "message": "Insufficient sample persists for 4w; data accumulation slower than expected"
    }
  ],
  "recommended_action": "REVIEW"
}
```

### Example 3 — REVIEW_REQUIRED (tail emergency forced SUSPENDED)

```json
{
  "week": "2026-W51",
  "state": "SUSPENDED",
  "confidence": 0.47,
  "edge": {"edge_bps": 12.0, "trend": "DOWN", ...},
  "tail": {"tail_guard_triggered": true, "tail_delta_p99_bps": -28.0, ...},
  "streaks": {"verdict_streak": 0, "readiness_streak": 0, "streak_reset_count_last_8w": 1},
  "assessment": "REVIEW_REQUIRED",
  "red_flags": [
    {
      "code": "TAIL_EMERGENCY",
      "severity": "REVIEW",
      "message": "Tail emergency triggered SUSPENDED on 2026-12-21: tail-risk emergency: tail_delta_p99_bps -28.00 < hard floor -25.0"
    }
  ],
  "recommended_action": "INVESTIGATE"
}
```

### Example 4 — REVIEW_REQUIRED (high confidence + failing gate)

```json
{
  "week": "2026-W30",
  "state": "READY_FOR_REVIEW",
  "confidence": 0.78,
  "edge": {"edge_bps": 7.0, "trend": "FLAT", ...},
  "tail": {"tail_guard_triggered": false, ...},
  "assessment": "REVIEW_REQUIRED",
  "red_flags": [
    {
      "code": "HIGH_CONF_FAILING_GATES",
      "severity": "REVIEW",
      "message": "Confidence 0.78 ≥ 0.70 but 1 gate(s) failing: gate_5_regime_validation"
    }
  ],
  "recommended_action": "INVESTIGATE"
}
```

### Example 5 — REVIEW_REQUIRED (rapid ascent + hash mismatch + DO_NOT_APPROVE)

```json
{
  "week": "2026-W26",
  "state": "STRONG_CANDIDATE",
  "confidence": 0.81,
  "edge": {"edge_bps": 9.0, "trend": "UP", ...},
  "streaks": {"verdict_streak": 4, "readiness_streak": 2, "streak_reset_count_last_8w": 0},
  "governance": {
    "approval_status": "ACTIVE",
    "days_until_expiry": 11,
    "snapshot_content_hash_match": false,
    ...
  },
  "assessment": "REVIEW_REQUIRED",
  "red_flags": [
    {
      "code": "RAPID_ASCENT",
      "severity": "WATCH",
      "message": "STRONG_CANDIDATE reached in 4 weeks (rapid); double-check OOS depth"
    },
    {
      "code": "APPROVAL_HASH_MISMATCH",
      "severity": "REVIEW",
      "message": "Active approval references stale snapshot hash; evidence has changed since approval"
    }
  ],
  "recommended_action": "DO_NOT_APPROVE"
}
```

---

## Test plan (Phase 10B.2 implementation scope)

`apps/api/tests/unit/test_v2_oos_monitoring.py` — pure-function tests over hand-built snapshot dicts:

| Test | Scenario |
|---|---|
| `test_stable_progression_normal_assessment` | 8 weeks of clean STRONG_CANDIDATE → NORMAL, zero red flags |
| `test_streak_reset_scenario_flags_watch` | 4 streak resets in last 8w → STREAK_RESET_FREQUENT (WATCH) |
| `test_tail_emergency_flags_review_required` | Current snapshot SUSPENDED with emergency rollback_reason → TAIL_EMERGENCY (REVIEW) → REVIEW_REQUIRED |
| `test_repeated_suspended_within_window` | 2 SUSPENDED entries in trailing 12w → REPEATED_SUSPENDED (REVIEW) |
| `test_stale_approval_flags_watch` | Active APPROVE row > 14 days old → APPROVAL_EXPIRED (WATCH) |
| `test_approval_expiring_soon_flag` | Approval at days_until_expiry=3 → APPROVAL_EXPIRING_SOON |
| `test_approval_hash_mismatch_flags_review` | Approval hash != current snapshot hash → APPROVAL_HASH_MISMATCH |
| `test_high_conf_with_failing_gate` | Confidence=0.85 with gate_5 failing → HIGH_CONF_FAILING_GATES (REVIEW) |
| `test_rapid_ascent_flagged` | NOT_READY → STRONG_CANDIDATE in 4 weeks → RAPID_ASCENT (WATCH) |
| `test_insufficient_sample_persist` | 3 consecutive snapshots with INSUFFICIENT_TAIL_SAMPLE gate reason → INSUFFICIENT_SAMPLE_PERSIST |
| `test_comparison_fetch_degraded_flagged` | 3/7 trailing fetches failed → COMPARISON_HEALTH_DEGRADED (REVIEW) |
| `test_confidence_basis_warnings_surfaced` | basis_warnings non-empty → CONFIDENCE_BASIS_WARNINGS (INFO) |
| `test_bundle_schema_downgrade_flagged` | schema_version=1 when latest known is 2 → BUNDLE_SCHEMA_DOWNGRADE (INFO) |
| `test_normal_when_no_red_flags` | All sub-conditions clean → NORMAL + NONE |
| `test_recommended_action_do_not_approve_when_strong_with_review` | STRONG_CANDIDATE + REVIEW flag → DO_NOT_APPROVE |
| `test_assessment_rollup_review_dominates_watch` | One REVIEW + multiple WATCH → REVIEW_REQUIRED |
| `test_insufficient_history_does_not_red_flag` | Only 2 prior snapshots → trend=INSUFFICIENT, no red flags raised purely from lack of history |
| `test_report_is_deterministic` | Same inputs → identical bytes |
| `test_report_to_jsonable_serializable` | dataclasses.asdict() round-trips via stdlib json |

`apps/api/tests/integration/test_v2_oos_monitoring.py` — read-only DB tests:

| Test | Scenario |
|---|---|
| `test_fetch_and_build_returns_none_when_empty` | Empty snapshot table → returns None, no error |
| `test_fetch_latest_snapshot_when_id_omitted` | Most-recent snapshot used as the report subject |
| `test_fetch_specific_snapshot_by_id` | snapshot_id supplied → builds report for that one |
| `test_no_writes_to_database` | Before/after row counts identical for snapshot + approval tables |
| `test_handles_missing_optional_fields_gracefully` | Snapshot with NULL snapshot_content_hash, NULL evaluated_at_utc → report still builds |
| `test_no_recompute_uses_stored_state_field_verbatim` | Manually crafted snapshot.state="WATCH" with bundle implying STRONG → report says WATCH |

---

## Boundaries verification (post-implementation)

To be enforced when Phase 10B.2 ships:

1. **No mutating SQL** — grep for `INSERT|UPDATE|DELETE|session.add|session.commit|session.delete` in `v2_oos_monitoring.py` → zero matches
2. **No execution / strategy / scheduler imports** — grep for `engine_b|shadow_strategy|paper_trade_log|decision_log|paper_shadow_log|run_v2_promotion_snapshot|tick_loop|registry` → zero matches
3. **No ML imports** — grep for `\bml_|tensorflow|sklearn|torch|xgboost|lightgbm` → zero matches
4. **No gate / state-machine recomputation** — grep for `evaluate_gate|advance_or_rollback|update_streaks|compute_promotion_confidence` → zero matches
5. **No approval-side mutation** — module never writes to `v2_promotion_approval`
6. **No external HTTP** — grep for `requests|httpx|urllib|aiohttp|fetch` → zero matches
7. **All numbers traceable to snapshot row** — by inspection of source: every numeric field in the report comes from `snapshot.<col>` or `snapshot.comparison_bundle_json[...]` or `snapshot.gates_json[...]`, never from a fresh computation
8. **Test verifying constant-time, no DB I/O for `build_weekly_report`** — pure function call with mocked dataclasses; assert no DB session created

---

## Files to be added (Phase 10B.2)

| File | Type | Lines (est.) |
|---|---|---:|
| `apps/api/src/research/v2_oos_monitoring.py` | NEW | ~600 |
| `apps/api/tests/unit/test_v2_oos_monitoring.py` | NEW | ~700 |
| `apps/api/tests/integration/test_v2_oos_monitoring.py` | NEW | ~250 |

**Files NOT modified in 10B.2:** zero. Pure additive module.

Optional follow-up (separate explicit approval required):
- `apps/api/src/api/v2_promotion.py` — add read-only `GET /api/v2-promotion/oos-report` endpoint
- `apps/web/src/components/ops/V2PromotionTriggerCard.tsx` — render report inline as a separate read-only panel
- New table `v2_oos_report_log` (append-only) — only if operator explicitly wants persistence; v1 stays in-memory pure-fn

---

## Acceptance criteria (Phase 10B.2)

1. All ~25 unit tests + ~6 integration tests pass deterministically.
2. `pytest -p no:randomly` produces identical output across runs.
3. All 8 boundary checks from §Boundaries verification pass.
4. INSUFFICIENT_SAMPLE / INSUFFICIENT_HISTORY surfaced via informational notes only — never raises, never red-flags purely on history depth.
5. Report's `assessment` and `recommended_action` are NEVER `APPROVE` or `EXECUTE`.
6. Snapshot table + approval table row counts unchanged before/after any report build.
7. No imports of `v2_promotion_gates`, `v2_promotion_state` recomputation surfaces (state-name string literals are acceptable as locally-defined constants).
8. Optional read-only stat_validation field consumed only when present; absence does not raise.

---

## What is explicitly out of scope for Phase 10B

- API endpoint exposure (deferred — separate explicit approval required)
- UI panel (deferred — separate explicit approval required)
- Persistent report log table (deferred — v1 is pure-fn only)
- Email / Slack / pager notifications (out of scope; this layer is informational)
- Cross-instrument reports (SPY-only currently)
- Per-regime tail trend analysis (v2)
- Predictive forecasting / ML-based assessment (Phase 10C territory)
- Any change to `v2_promotion_gates.py`, `v2_promotion_state.py`, snapshot job, scheduler, comparison framework

---

## Final recommendation

After Phase 10B.2 ships and passes review, the next safe phase is
**10C.1** — ML advisory layer **design only**. ML coding is gated on
explicit operator approval AFTER 10C.1 design review.

`SAFE_TO_CONTINUE_OBSERVING` pending operator approval of this design.

**Awaiting operator approval to implement Phase 10B.2.**
