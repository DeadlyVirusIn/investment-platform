# B2 vs V2 Head-to-Head Evaluation — Implementation Results & Next Steps

**Date:** 2026-04-25
**Status:** Framework implemented + tested. **NO production change.** **NO routing change.** **NO promotion state change.** B2 still paused (BLOCKING via edge_trajectory) per `B2_V2_PERSIST3_UPDATE.md`.
**Branch:** `phase-1/ledger`
**Design ref:** `docs/research/B2_V2_COMPARISON_FRAMEWORK_DESIGN.md` (revision v2)

---

## TL;DR

Built a **read-only** B2 vs V2 head-to-head evaluation framework that
joins the two source_strategy buckets in `paper_shadow_log` on
`(as_of_date, instrument)` and produces an advisory verdict
(`V2_BETTER` / `B2_BETTER` / `INCONCLUSIVE`) plus confidence + readiness
labels. Surfaced via `/api/b2-v2/comparison` and a card on the Ops page.

Robustness extensions (revision v2): impact-weighted edge,
regime-conditioned metrics (STRESS / DIRECTIONAL / NEUTRAL), and a
downgrade-only tail-sensitivity guard.

---

## What Shipped

### Backend

| File | Type | Lines | Purpose |
|---|---|---|---|
| `apps/api/src/research/b2_v2_comparison.py` | NEW | ~430 | Pure analytics — extract_divergence, divergence_metrics, metrics_by_regime, tail_comparison, stability_check, verdict (with tail guard), compute_all |
| `apps/api/src/api/b2_v2_comparison.py` | NEW | ~150 | Read-only routes `GET /api/b2-v2/comparison` + `GET /api/b2-v2/timeline` |
| `apps/api/src/main.py` | EDIT (2 lines) | — | Registered router |
| `apps/api/tests/unit/test_b2_v2_comparison.py` | NEW | ~430 | 26 unit tests, all green (`0.09s`) |

### Frontend

| File | Type | Purpose |
|---|---|---|
| `apps/web/src/lib/b2v2/hooks.ts` | NEW | React Query hook `useB2vsV2Comparison` + full type definitions |
| `apps/web/src/components/ops/B2vsV2ComparisonCard.tsx` | NEW | Panel: verdict badge + confidence bar + divergence stats + edge composition + tail comparison + regime breakdown + stability |
| `apps/web/src/pages/Ops.tsx` | EDIT (2 lines) | Mount card below `EngineBTransitionCard` |

### Verification

- `pytest apps/api/tests/unit/test_b2_v2_comparison.py` → **26/26 pass** (0.09 s)
- `tsc --noEmit` (apps/web) → **clean**
- `python -c "from apps.api.src.main import app; ..."` → routes mounted at `/api/b2-v2/comparison`, `/api/b2-v2/timeline`

### Files NOT modified (verified)

- `apps/api/src/research/shadow_strategy.py`
- `apps/api/src/research/shadow_strategy_v2.py`
- `apps/api/src/research/engine_b_promotion.py`
- `apps/api/src/research/engine_b_router.py`
- `apps/api/src/research/engine_b_decision.py`
- `apps/api/src/research/engine_b_analytics.py`
- `apps/api/src/research/engine_b2.py`
- `apps/api/src/api/engine_b_transition.py`
- `apps/api/src/api/shadow.py`
- `scripts/run_shadow_strategy.py`
- DB schema (no migration created)

---

## How to Use

### Pull current verdict (CLI)

```bash
curl -s 'http://localhost:8000/api/b2-v2/comparison?days=365&instrument=SPY' | jq .verdict
```

Sample output shape:

```json
{
  "verdict": "INCONCLUSIVE",
  "confidence": 0.42,
  "tail_guard_triggered": false,
  "tail_guard_reason": null,
  "readiness": "NOT_READY",
  "base_verdict_before_guard": "INCONCLUSIVE",
  "base_confidence_before_guard": 0.42
}
```

### Render UI

Navigate to **Ops** page → scroll to "B2 vs V2 Comparison" card directly below the Engine B → B2 Migration card.

### Inspect raw timeline

```bash
curl -s 'http://localhost:8000/api/b2-v2/timeline?days=60&instrument=SPY' | jq '.rows[] | select(.divergence_class != null)'
```

---

## Frozen Thresholds

All thresholds are module-level constants in `b2_v2_comparison.py`. Any
change requires a revision-history entry in
`B2_V2_COMPARISON_FRAMEWORK_DESIGN.md`.

| Constant | Value | Purpose |
|---|---:|---|
| `VERDICT_EDGE_BPS_THRESHOLD` | 5.0 | Min edge for V2_BETTER / B2_BETTER |
| `VERDICT_CUM_DIFF_PCT_THRESHOLD` | 0.5 | Min cumulative diff for V2_BETTER (or −0.5 for B2_BETTER) |
| `VERDICT_P99_DELTA_BPS_THRESHOLD` | -10.0 | V2 p99 cannot be more than 10 bps deeper than B2 |
| `VERDICT_P99_DELTA_BPS_HARD` | -25.0 | Hard B2_BETTER trigger if V2 p99 ≥ 25 bps deeper |
| `TAIL_GUARD_EDGE_MIN_BPS` | 10.0 | Edge floor below which tail guard can fire |
| `TAIL_GUARD_CONFIDENCE_CAP` | 0.5 | Max confidence after guard triggers |
| `READINESS_STRONG_CONFIDENCE` | 0.7 | Min confidence for STRONG_CANDIDATE |
| `READINESS_REVIEW_CONFIDENCE` | 0.4 | Min confidence for REVIEW |
| `READINESS_STRONG_MIN_N` | 30 | Min divergent days for STRONG_CANDIDATE |
| `STABILITY_TREND_DEAD_ZONE_BPS` | 5.0 | ± band for STABLE trend label |
| `STABILITY_LAST_N_DAYS` | 30 | Window for last_30 vs prior_30 split |

---

## Verdict Pipeline (recap)

```
extract_divergence(rows)
        │
        ▼
divergence_metrics(div) ──► metrics_by_regime(div)
        │
        ▼
tail_comparison(rows)
        │
        ▼
stability_check(div)
        │
        ▼
base_verdict(metrics, tail, stability)         ← V2_BETTER | B2_BETTER | INCONCLUSIVE
        │
        ▼
apply_tail_guard                               ← downgrade-only, never upgrades
        │
        ▼
readiness                                      ← STRONG_CANDIDATE | REVIEW | NOT_READY
```

---

## Live Verdict Snapshot

> **Operator: fill this section after first call against live data.**

| Field | Value |
|---|---|
| as-of date | TBD |
| n input rows (joined) | TBD |
| n divergent rows | TBD |
| **verdict** | TBD |
| confidence | TBD |
| readiness | TBD |
| tail-sensitivity guard | TBD |
| impact-weighted edge | TBD |
| regime with strongest V2 edge | TBD |

---

## Next Steps

### Immediate (this week)

1. **Bring API up locally**, hit `/api/b2-v2/comparison`, capture the
   first verdict snapshot. Paste output into the "Live Verdict Snapshot"
   section above.
2. **Open Ops page** and verify the card renders without console errors
   against the running API.
3. **Spot-check a divergent day** by hand: pull a day from
   `/api/b2-v2/timeline` where `divergence_class` is set, eyeball
   against TradingView or a similar reference, confirm `b2_return` and
   `v2_return` match what would have been realized.

### Short term (next 2–4 weeks)

4. **Accumulate 30+ divergent days of OOS shadow data** before treating
   any verdict as actionable. The framework returns `INCONCLUSIVE` while
   `n < 10`; `STRONG_CANDIDATE` requires `n ≥ 30` AND `confidence ≥ 0.7`.
5. **Track verdict drift**: pull the bundle weekly, log to a flat file:
   `(date, verdict, confidence, readiness, tail_guard, n_div, edge_bps,
   cum_diff_pct, impact_weighted_edge)`. Look for stability — a verdict
   that flips weekly is not a verdict.
6. **Watch the regime breakdown**: persist3 was designed to fix
   single-close MA200 false stress. The expected payoff concentrates in
   `STRESS` regime days where B2 incorrectly stays out and V2 correctly
   stays in. If the regime breakdown shows STRESS edge ≈ 0 and
   DIRECTIONAL edge dominating, the V2 edge is incidental and the
   thesis is **not** validated.

### Medium term (only if STRONG_CANDIDATE sustains for ≥ 4 weeks)

7. **Operator review meeting** to decide whether to begin a V2 paper
   promotion. **This framework does not promote.** Promotion would go
   through a separate, future revision of `engine_b_promotion.py` with
   its own gates, kill-switches, and operator-approval workflow —
   modeled on the existing Engine B → B2 transition machinery, not on
   this advisory framework.
8. **Define V2 promotion gates** as a separate design doc. Reference
   this framework's verdict + readiness as one input among several
   (others: live PnL during partial promotion, kill-switch triggers,
   regime-stress live behavior, drawdown bounds).

### Maintenance

9. **Re-run unit tests** in CI on every PR touching
   `b2_v2_comparison.py` or `paper_shadow_log` schema.
10. **Update the design doc revision history** before changing any
    threshold constant. Thresholds without a documented revision
    rationale should be reverted on review.
11. **Watch for INNER JOIN coverage drift**: if V2 backfill ever falls
    behind B2 (or vice versa), the joined row count will quietly
    shrink. Add a dashboard tile if this becomes a recurring concern.

---

## Out of Scope (reminders)

- ❌ Promoting V2 to production
- ❌ Routing decisions (still 100 % B2 in production-shadow; live
  execution remains paused per the BLOCKING edge_trajectory verdict)
- ❌ Modifying B2 or V2 strategy logic
- ❌ Adjusting verdict thresholds without a documented revision

---

## References

- Design (this framework, v2): `docs/research/B2_V2_COMPARISON_FRAMEWORK_DESIGN.md`
- V2 strategy introduction: `docs/research/B2_V2_PERSIST3_UPDATE.md`
- Engine B promotion (production transition machinery, untouched here):
  `apps/api/src/research/engine_b_promotion.py`
- Source modules: `apps/api/src/research/b2_v2_comparison.py`,
  `apps/api/src/api/b2_v2_comparison.py`
- Tests: `apps/api/tests/unit/test_b2_v2_comparison.py`
- UI: `apps/web/src/components/ops/B2vsV2ComparisonCard.tsx`
