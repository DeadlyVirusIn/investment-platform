# historical_label Root Cause — Wave 3A.1 (2026-07-14)

## Verdict

**Category: writer never scheduled + source snapshots absent for history.**
Two independent causes, both proven:

1. `backfill_historical_labels` (`apps/api/src/domain/ml/backfill_service.py`)
   has **zero callers** anywhere in the codebase — no scheduler registry
   entry (`apps/worker/src/jobs/registry.py` has none), no CLI wiring, no
   API route. It is an on-demand rebuild artifact invoked manually during
   the BP8–BP27B alpha investigation era; its output rows lived in an
   earlier dev-database era and were never re-materialized in the current
   dev DB (rebuilt/cloned since). Nothing failed; nothing was truncated
   maliciously — the table was simply never populated here.
2. Even when invoked, the pipeline structurally requires **point-in-time
   `factor_snapshot` + `regime_snapshot` rows per as_of day** — and those
   exist only from **2026-04-22** (factor) / 2026-01-01 (regime) onward
   (the snapshot jobs are recent additions). Coverage before 2026-04-22 is
   permanently unavailable without recomputing features from present-day
   state, which the point-in-time rule forbids.

## Semantic audit (one row)

- decision timestamp = `as_of_date` (daily, business days);
- features = the stored `factor_snapshot` row for (asset, as_of_date) —
  **point-in-time stored, not recomputed** (safe); regime features from
  `regime_snapshot` (point-in-time, safe);
- target = triple-barrier over the NEXT 20 daily bars starting `as_of+1`:
  pt/sl = entry ± 2·realized_vol_20d·√(20/252); label +1 target-first,
  −1 stop-first, 0 timeout; entry = close at as_of;
- corporate actions: bars are provider-adjusted closes (split-only caveat
  from the Polygon-era fix applies to raw history);
- censoring: days without 20 forward bars are skipped by the pipeline
  (not mislabeled);
- engine_version stamps the scoring config
  (`stock_swing_v1:f9a7e0dc3cf3f74c`) — label policy is versioned by
  construction.

Feature point-in-time classification: price-derived/rolling/vol/liquidity
factors → **point-in-time safe** (stored snapshots); `sector_relative_rank`
→ safe WITHIN the snapshot window (stored), **current-state leakage risk**
if ever recomputed for older dates; fundamentals → not used; family
scores/confidence → recomputed by the pipeline from the stored factors
(deterministic function of point-in-time inputs — safe).

## Rebuild executed (dev only, backup first)

Via the ORIGINAL pipeline (no parallel implementation), 2026-04-22 →
2026-07-13 requested; pipeline self-limited to as_of ≤ 2026-06-17
(20-forward-bar requirement): **1,601 rows, 36 trading days, labels
+1/−1/0 = 789/462/350, actions Trim 1,307 / Buy 294**, engine_version
`stock_swing_v1:f9a7e0dc3cf3f74c`, built-in sanity validation OK.
Idempotent upsert; re-run reproduces the same rows. Rollback:
`DELETE FROM historical_label WHERE engine_version =
'stock_swing_v1:f9a7e0dc3cf3f74c'` (the table held zero other rows —
manifest in the evidence-unlock report).

## Trained-adapter gate verdict: **BLOCKED (temporal depth)**

36 trading days across 3 partial months ⇒ at most 2 usable monthly
evaluation folds (first period cannot train) — below the ≥4-fold gate;
294 Buy rows also thin. Point-in-time integrity PASSES within the window;
everything else is moot until snapshot history accumulates. **No LightGBM
adapter was built** — per the gate, reconstruction stops here honestly.

## Unlock path (forward-only)

The snapshot jobs (`compute_factor_snapshots`, `compute_regime_snapshot`)
are now scheduled and accumulate point-in-time features daily. Every ~21
trading days adds one monthly fold; the ≥4-fold gate is reachable around
**late 2026-08** (4 full months of snapshots), provided the label
pipeline is re-run periodically. Recommendation: wire
`backfill_historical_labels` as a weekly scheduled catch-up job (separate
approval — scheduler change).
