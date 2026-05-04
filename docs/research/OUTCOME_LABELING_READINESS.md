# Outcome Labeling Readiness — audit + future-phase plan

Read-only diagnostic of the path that converts closed paper-trade
activity into ML-ready labels. **No labels are fabricated by this
phase. No model training is invoked. No DB writes happen here.**

---

## TL;DR

| Question | Answer |
| --- | --- |
| Does the codebase already label `recommendation_outcome` rows? | **Yes** — `apps/worker/src/jobs/score_outcomes.py` exists and is registered in `apps/worker/src/jobs/registry.py` as `score_recommendation_outcomes`. |
| Why is `labeled_outcomes` currently 0? | All 63 `recommendation_outcome` rows are <30 days old (parent recommendations dated 2026-05-03). The labeler enforces `MIN_AGE_DAYS=30`, so labels naturally appear ~30 days after each rec was created. |
| Should we fabricate labels now? | **No.** Wait for organic outcomes. |
| Is anything missing for the existing labeler to fire? | A scheduled trigger. The labeler is a job module, not yet wired into the worker cron. |

---

## Lifecycle mapping (current state of truth)

```
[recommendation] ─generated─►   recommendation_engine.py
       │
       ├─stub────────────────►  recommendation_outcome
       │                        (price_at_recommendation set;
       │                         barrier_label/realized_*
       │                         left NULL — pending)
       │
[paper_trade] ─auto_trader────► paper_trade
                                paper_position
                                replay_recovery_manifest (if replay)

[T + 30d] ─score_outcomes────►  recommendation_outcome
                                (barrier_label, realized_30d_return,
                                 realized_90d_return,
                                 trend_regime, volatility_regime, ...)
                                — TRIPLE-BARRIER labeling, deterministic.

[ml_replay_decision/outcome]   — replay-only ML dataset path
                                 (separate from outcome labeling).
```

### Source-of-truth tables

| Table | Role |
| --- | --- |
| `recommendation` | recommendation rows, one per asset/account/decision. |
| `recommendation_outcome` | one row per recommendation, populated lazily; labels arrive when the score-outcomes job fires. |
| `paper_trade` | account-path executed trades (entries + exits). `realized_pnl` populated only on closing trades. |
| `paper_position` | open positions; closed via paper-execution path. |
| `replay_recovery_manifest` | provenance for replay-recovered rows (excluded from "live" by default). |
| `ml_replay_decision` / `ml_replay_outcome` | replay-only ML dataset; not used by the live labeler. |

---

## Exact condition that flips ML readiness to ready

`/api/ml/insights/readiness` returns `is_ready=true` iff
`labeled_trade_count >= 20`, where:

```sql
SELECT count(*) FROM recommendation_outcome
WHERE barrier_label IS NOT NULL
   OR realized_30d_return IS NOT NULL;
```

Today: `labeled_trade_count = 0`. Reason returned by the endpoint is
`"no_labeled_outcomes"` and `next_unlock_condition` is
`"Wait for trades to close and outcomes to be labeled."`.

The replay-only warning is also active because
`live_trade_count = 0` and `replay_trade_count = 18`:

```
"Current dataset is replay-derived; treat model metrics as recovery
 diagnostics."
```

---

## What works already

- `apps/worker/src/jobs/score_outcomes.py::score_recommendation_outcomes`
  - Reads recommendations with `generated_at <= now - 30d` and
    `recommendation_outcome.barrier_label IS NULL`.
  - Builds price series from `price_bar` and applies a
    triple-barrier label using `apps/api/src/domain/recommendations/outcome_labeling.py`.
  - Writes `barrier_label`, `realized_30d_return`,
    `realized_90d_return`, regime tags onto the existing
    `recommendation_outcome` row.
  - Deterministic, no randomness, no lookahead.
- `recommendation_engine.py:455` creates the stub
  `recommendation_outcome` row at recommendation time so the labeler
  has somewhere to write.

---

## What is missing — future-phase plan

### "Outcome Labeler Phase — converts closed trades into labels"

**Out of scope for this read-only phase. Documented for future
implementation.** No code changes here.

Required pieces (when we are ready):

1. **Scheduling.** Wire `score_recommendation_outcomes` into either
   `infra/docker/worker.crontab` or a new alembic-tracked scheduler
   table. Cadence: nightly. Idempotent — only updates rows whose
   `barrier_label IS NULL`.

2. **paper_trade ↔ recommendation linkage.** `paper_trade.recommendation_id`
   exists but is not always populated (replay rows have it null).
   Future labeler should:
   - Refuse to fabricate labels for replay-tagged trades. Replay
     rows already excluded by default in
     `/api/performance/paper/lifecycle` and
     `/api/ml/insights/readiness`.
   - When `recommendation_id` is null, leave the row unlabeled
     instead of guessing.

3. **paper_position closure pathway.** Currently no automated
   close-out exists. Required for organic exits:
   - A read-only daily check that flags positions whose triple-
     barrier window has elapsed.
   - A separate, opt-in execution path with explicit env
     confirmation (mirror of
     `OPTIONS_CHAIN_INGEST_CONFIRM=…`) before any trade closure
     is written. **Do not auto-close.**

4. **No-fabrication policy.**
   - The labeler must NEVER set `barrier_label` based on an
     extrapolated price.
   - It must NEVER write a label when `price_bar` data is missing
     for the entire triple-barrier window.
   - It must NEVER label replay-tagged rows alongside live ones
     without a separate flag (`source` column on the outcome row
     is a candidate addition).
   - All writes must be idempotent on the natural key
     `(recommendation_id)` already enforced by FK.

5. **Backfill diagnostics.**
   - `scripts/backfill_historical_labels.py` already exists for
     historical backfills; future phase should add a
     `--dry-run` default + env-confirmation gate before any
     `--commit` flips.

---

## No-fabrication policy (this phase + permanent)

- This phase introduces ZERO writes. All endpoints are GET.
- The lifecycle endpoint reports `current_stage="label_pending"`
  when an outcome row exists without a label — never fabricates a
  label to make the UI look complete.
- The readiness endpoint reports `is_ready=false` when labels are
  absent. Never spoofs a green light.
- Frontend cards have no buttons that could trigger labeling, model
  training, or trade execution.
- `ML_CAN_AFFECT_TRADES` remains pinned to `false`.

---

## Rollback (this phase only)

- Remove the `/lifecycle` function from
  `apps/api/src/api/performance_paper.py` (everything below the
  `Lifecycle status / current_stage vocabularies` divider).
- Remove the `/readiness` function from
  `apps/api/src/api/ml_insights.py` (everything below the readiness
  divider).
- Delete `apps/web/src/components/personal/TradeLifecycleCard.tsx`
  and `MLReadinessPanel.tsx`.
- Remove imports + JSX usage from `Performance.tsx` and `MLLab.tsx`.
- Delete `apps/api/tests/unit/test_lifecycle_readiness.py`.

No DB migrations, no scheduler entries, no fixtures involved.

---

## Tests added in this phase

`apps/api/tests/unit/test_lifecycle_readiness.py` — 27 tests.
