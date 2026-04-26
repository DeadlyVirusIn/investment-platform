# B2 vs V2 Head-to-Head Evaluation Framework — Design

**Date:** 2026-04-25
**Revision:** v2 (adds robustness: impact-weighted edge, regime-conditioned metrics, tail-sensitivity guard)
**Author:** Claude (Opus 4.7)
**Status:** DESIGN — awaiting operator approval before implementation
**Related:** `B2_V2_PERSIST3_UPDATE.md` (V2 strategy introduction)

## Revision History

| Revision | Date | Change |
|---|---|---|
| v1 | 2026-04-25 | Initial 6-part framework |
| v2 | 2026-04-25 | + Impact-weighted edge, regime-conditioned metrics, tail-sensitivity guard, UI extensions. **No threshold changes. No execution / promotion changes.** |

---

## TL;DR

Build a **read-only** evaluation framework that objectively compares the
B2 production-shadow strategy (`tsmom_60_no_stress`) against the V2
research-shadow strategy (`tsmom_60_no_stress_v2_persist3`) using the
shadow-data already accumulating in `paper_shadow_log`.

The framework outputs a verdict (`V2_BETTER` / `B2_BETTER` /
`INCONCLUSIVE`), a confidence score, and a readiness label
(`NOT_READY` / `REVIEW` / `STRONG_CANDIDATE`). It is surfaced as a
panel on the Ops page.

**No production impact.** Pure SELECTs against `paper_shadow_log`. No
changes to B2 logic, V2 logic, promotion state, or routing. New module +
new endpoint + new UI card mounted under fresh prefix `/api/b2-v2`.

---

## Non-Goals (Hard Boundaries)

- **NOT** a promotion mechanism. Verdict is informational only — no
  state flip, no automatic routing change, no mode switch.
- **NOT** a backtest. Operates strictly on the live shadow log; no
  simulated trades, no synthetic regime relabeling.
- **NOT** a modification to B2 or V2. Both modules remain
  byte-unchanged. `engine_b_promotion.py`, `engine_b_router.py`,
  `engine_b_decision.py`, `shadow_strategy.py`, `shadow_strategy_v2.py`
  all UNTOUCHED.
- **NOT** a replacement for `engine_b_analytics.py`. That module
  compares Engine B vs B2 (within a single source_strategy row). This
  framework compares B2 vs V2 (across two source_strategy rows joined
  on date).

---

## Data Model

### Source

`paper_shadow_log` — primary key `(as_of_date, instrument, source_strategy)`.

| source_strategy | Role | Logic version |
|---|---|---|
| `tsmom_60_no_stress` | **B2** | `research_backfill_v1` (single-close MA200 stress) |
| `tsmom_60_no_stress_v2_persist3` | **V2** | `research_backfill_persist3_v1` (3-consecutive-close MA200 stress) |

### Comparison Join

```sql
SELECT
  b2.as_of_date,
  b2.instrument,
  b2.signal           AS b2_signal,
  v2.signal           AS v2_signal,
  b2.regime_label     AS b2_regime,
  v2.regime_label     AS v2_regime,
  b2.fwd_return_1d,
  b2.fwd_return_5d,
  b2.trend_score      AS b2_trend,
  v2.trend_score      AS v2_trend
FROM paper_shadow_log b2
INNER JOIN paper_shadow_log v2
  ON  b2.as_of_date  = v2.as_of_date
  AND b2.instrument  = v2.instrument
WHERE b2.source_strategy = 'tsmom_60_no_stress'
  AND v2.source_strategy = 'tsmom_60_no_stress_v2_persist3'
  AND b2.as_of_date >= :cutoff
ORDER BY b2.as_of_date ASC;
```

`fwd_return_1d` is identical across rows (same instrument + date), so
either side suffices. INNER JOIN drops dates where only one strategy
ran (early V2 days before backfill, or future dates not yet labeled).

---

## Architecture

### Layer 1 — Pure analytics module

`apps/api/src/research/b2_v2_comparison.py`

Pure functions over a list of joined dicts. No DB, no I/O, no globals.
Mirrors the `engine_b_analytics.py` shape for consistency.

```python
def extract_divergence(rows: list[dict]) -> list[dict]
def divergence_metrics(div_rows: list[dict]) -> dict
def tail_comparison(rows: list[dict]) -> dict
def stability_check(div_rows: list[dict]) -> dict
def verdict(metrics: dict, tail: dict, stability: dict) -> dict
def compute_all(rows: list[dict]) -> dict   # bundle
```

#### Part 1 — Divergence extraction

`extract_divergence(rows)` returns rows where `b2_signal != v2_signal`,
each tagged with:

| field | values |
|---|---|
| `divergence_class` | `B2_FLAT_V2_LONG` (V2 takes a trade B2 skips) or `B2_LONG_V2_FLAT` (V2 sits out a trade B2 takes) |
| `b2_return` | `fwd_return_1d` if B2=LONG else 0.0 |
| `v2_return` | `fwd_return_1d` if V2=LONG else 0.0 |
| `delta` | `v2_return − b2_return` (positive = V2 wins this day) |

Skip rows with `fwd_return_1d IS NULL` (recent days, not yet realized).

#### Part 2 — Divergence metrics

Computed only over divergent days:

| field | definition |
|---|---|
| `n_divergent_days` | count(div_rows) |
| `n_b2_flat_v2_long` | count where V2 took a trade B2 skipped |
| `n_b2_long_v2_flat` | count where V2 sat out a trade B2 took |
| `win_rate_v2_vs_b2_pct` | % days where `delta > 0` |
| `avg_return_diff_1d_bps` | mean(`delta`) × 10000 |
| `avg_return_diff_5d_bps` | mean(`v2_5d − b2_5d`) × 10000 (using `fwd_return_5d`) |
| `cumulative_return_diff_pct` | (∏(1+v2_ret) − ∏(1+b2_ret)) × 100 over divergent days |
| `avoided_losses_count` | days where B2=LONG, V2=FLAT, fwd_return_1d < 0 |
| `avoided_losses_avg_bps` | mean of avoided losses, in bps (positive number) |
| `new_losses_count` | days where B2=FLAT, V2=LONG, fwd_return_1d < 0 |
| `new_losses_avg_bps` | mean of new losses, in bps (positive number) |
| `impact_weighted_edge` | `sum(delta) / sum(abs(b2_return) + abs(v2_return))` — dimensionless. Quantifies edge per unit of total risk taken across both engines on divergent days. NaN if denominator == 0. |

**Why impact-weighted edge:** Raw `avg_return_diff_1d_bps` treats every
divergent day equally. A +5 bp edge built on 200 bp swings is far less
meaningful than the same edge built on 20 bp swings. The impact-weighted
metric normalizes for the magnitude of capital-at-risk. Reported
alongside (not replacing) the raw edge.

#### Part 2b — Regime-conditioned metrics

`metrics_by_regime`: divergence_metrics computed independently per
regime label, joined off the **B2 row's `regime_label`** (the
production-side regime view, since V2 disagreement is the variable
under study):

```python
metrics_by_regime = {
    "stress":      divergence_metrics([r for r in div if r["b2_regime"] == "STRESS"]),
    "directional": divergence_metrics([r for r in div if r["b2_regime"] == "DIRECTIONAL"]),
    "neutral":     divergence_metrics([r for r in div if r["b2_regime"] == "NEUTRAL"]),
}
```

Each bucket returns the full divergence_metrics dict (including
`impact_weighted_edge`). Empty buckets return the same nulls-shape as
`divergence_metrics([])`. **Top-level verdict thresholds unchanged** —
regime breakdown is reported, not used to flip the verdict.

#### Part 3 — Tail comparison

Computed over **all rows** (not divergence-only) using each engine's
realized 1d return (LONG → `fwd_return_1d`, FLAT → 0.0):

| field | definition |
|---|---|
| `b2_p95_loss_bps` / `v2_p95_loss_bps` | 5th percentile of returns × 10000 |
| `b2_p99_loss_bps` / `v2_p99_loss_bps` | 1st percentile of returns × 10000 |
| `b2_worst_5_losses_bps` / `v2_worst_5_losses_bps` | bottom 5 returns each, sorted ascending |
| `tail_delta_p95_bps` / `tail_delta_p99_bps` | V2 − B2 (positive = V2 has shallower tail) |

#### Part 4 — Stability

Two slices:

| slice | window |
|---|---|
| `first_half` vs `second_half` | divergence_metrics on each half of the divergent date range |
| `last_30` vs `prior_30` | divergence_metrics on the trailing 30 days vs the 30 before |

For each slice the framework reports the edge (`avg_return_diff_1d_bps`)
and a `trend` label: `IMPROVING` (second > first by ≥ 5 bps),
`DECLINING` (≤ −5 bps), or `STABLE`.

#### Part 4b — Tail-sensitivity guard

A separate post-step that **may downgrade** the verdict by exactly one
level. **Never upgrades.** **Never modifies thresholds.** Inputs:

| input | source |
|---|---|
| `p99_worsens` | `tail["tail_delta_p99_bps"] < 0` (V2 p99 deeper than B2 p99) |
| `edge_improvement_small` | `metrics["avg_return_diff_1d_bps"] < TAIL_GUARD_EDGE_MIN_BPS` (default `10.0`) |

Rule:

```python
if p99_worsens and edge_improvement_small:
    if verdict == "V2_BETTER":
        verdict = "INCONCLUSIVE"
    elif verdict == "INCONCLUSIVE":
        verdict = "B2_BETTER"
    # else B2_BETTER stays B2_BETTER
    guard_triggered = True
    confidence = min(confidence, 0.5)
else:
    guard_triggered = False
```

Output dict gains:

| field | type |
|---|---|
| `tail_guard_triggered` | bool |
| `tail_guard_reason` | str (e.g. `"p99 worsens 12.3 bps; edge gain 4.1 bps < 10.0 threshold"`) or `None` |

`TAIL_GUARD_EDGE_MIN_BPS` lives as a module constant. Tunable in code,
never via API. Documented next to the existing verdict thresholds.

#### Part 5 — Verdict

```
def verdict(metrics, tail, stability) -> dict:
    edge_bps = metrics["avg_return_diff_1d_bps"]
    n        = metrics["n_divergent_days"]
    p99_d    = tail["tail_delta_p99_bps"]
    trend    = stability["last_30_vs_prior_30"]["trend"]
    cum_diff = metrics["cumulative_return_diff_pct"]
```

Verdict thresholds (operator-tunable, frozen at first cut):

| condition | verdict |
|---|---|
| `n < 10` OR `edge_bps` is NaN | `INCONCLUSIVE` |
| `edge_bps ≥ 5` AND `cum_diff ≥ 0.5%` AND `p99_d ≥ −10` | `V2_BETTER` |
| `edge_bps ≤ −5` OR `cum_diff ≤ −0.5%` OR `p99_d ≤ −25` | `B2_BETTER` |
| else | `INCONCLUSIVE` |

Confidence score (0–1):

```
confidence = clamp(0, 1,
    0.4 * normalize(n, 10, 60)               # sample size
  + 0.3 * sign_consistency(half1, half2)     # stable direction
  + 0.3 * (1 if trend in ("IMPROVING","STABLE") else 0)
)
```

Readiness:

| condition | readiness |
|---|---|
| `verdict == V2_BETTER` AND `confidence ≥ 0.7` AND `n ≥ 30` | `STRONG_CANDIDATE` |
| `verdict == V2_BETTER` AND `confidence ≥ 0.4` | `REVIEW` |
| else | `NOT_READY` |

Verdict pipeline order is fixed: **base verdict → tail-sensitivity
guard → readiness**. The guard runs after the base verdict and before
readiness is computed, so a guard-triggered downgrade also tightens the
readiness label.

**Decision authority remains with the operator.** Readiness label is a
recommendation, not a trigger.

---

### Layer 2 — Read-only API

`apps/api/src/api/b2_v2_comparison.py`

```
GET /api/b2-v2/comparison?days=365&instrument=SPY
```

Returns the bundle from `compute_all`. Read-only. No POST. No PUT.
Registered in `apps/api/src/main.py` alongside other read-only routers.

```
GET /api/b2-v2/timeline?days=365&instrument=SPY
```

Returns the joined per-day rows for charting (subset of cols: date,
b2_signal, v2_signal, divergence_class, fwd_return_1d, b2_return,
v2_return, delta).

---

### Layer 3 — UI

| File | Role |
|---|---|
| `apps/web/src/lib/b2v2/hooks.ts` | React Query hook `useB2vsV2Comparison(days)` |
| `apps/web/src/components/ops/B2vsV2ComparisonCard.tsx` | Panel |
| `apps/web/src/pages/Ops.tsx` | Mount card below `EngineBTransitionCard` |

Card sections:

1. **Verdict badge** — V2_BETTER (green) / B2_BETTER (red) / INCONCLUSIVE (gray) + confidence bar + readiness pill. If `tail_guard_triggered`, show amber **"Tail-Sensitivity Guard"** chip next to the badge with the `tail_guard_reason` as a tooltip.
2. **Divergence stats** — n_divergent_days, win_rate, edge_1d_bps, edge_5d_bps, **impact_weighted_edge** (formatted as a ratio, e.g. `+0.083`), cumulative_diff_pct.
3. **Edge composition** — avoided_losses (count, avg bps) vs new_losses (count, avg bps).
4. **Tail comparison** — p95 / p99 / worst-5 side-by-side mini table (B2 col, V2 col, delta col). Highlight `tail_delta_p99_bps` cell in amber if guard triggered.
5. **Regime breakdown** — three-row table: STRESS / DIRECTIONAL / NEUTRAL × cols `n_days`, `win_rate`, `edge_bps`, `impact_weighted_edge`. Empty buckets show `—`.
6. **Stability** — first_half vs second_half edge + last_30 vs prior_30 edge with trend pill.

No actions. No buttons. No "promote" CTA. No regime-toggle that mutates state.

---

## Tests

`apps/api/tests/unit/test_b2_v2_comparison.py`

Fixture-driven, deterministic. Same shape as `test_engine_b_analytics.py`:

| test | what it checks |
|---|---|
| `test_extract_divergence_classifies_directions` | B2_FLAT_V2_LONG and B2_LONG_V2_FLAT correctly tagged |
| `test_extract_divergence_skips_unrealized` | rows with `fwd_return_1d IS NULL` excluded |
| `test_extract_divergence_skips_agreement` | b2 == v2 days excluded |
| `test_divergence_metrics_known_inputs` | hand-computed expected values |
| `test_divergence_metrics_empty` | returns nulls, no exceptions |
| `test_tail_comparison_known_inputs` | p95 / p99 / worst-5 against fixed series |
| `test_stability_check_first_vs_second` | trend label boundaries (5 bps) |
| `test_verdict_v2_better` | passes all V2_BETTER conditions |
| `test_verdict_b2_better` | edge or tail trigger flips verdict |
| `test_verdict_inconclusive_small_n` | `n < 10` short-circuits |
| `test_verdict_confidence_bounds` | confidence ∈ [0, 1] |
| `test_impact_weighted_edge_known_inputs` | hand-computed against fixed deltas |
| `test_impact_weighted_edge_zero_denominator` | both engines FLAT every divergent day → NaN, no ZeroDivisionError |
| `test_metrics_by_regime_partitions_correctly` | each row appears in exactly one bucket; sum of `n_divergent_days` across buckets == top-level `n_divergent_days` |
| `test_metrics_by_regime_empty_bucket` | NEUTRAL with no divergence → null-shape dict, no exceptions |
| `test_tail_guard_downgrades_v2_better_to_inconclusive` | small edge + worse p99 → downgrade applied |
| `test_tail_guard_does_not_upgrade` | B2_BETTER stays B2_BETTER even if p99 better |
| `test_tail_guard_no_trigger_when_edge_large` | edge ≥ TAIL_GUARD_EDGE_MIN_BPS → guard skipped |
| `test_tail_guard_no_trigger_when_p99_better` | V2 p99 shallower → guard skipped |
| `test_verdict_pipeline_order` | base verdict → guard → readiness; downgrade tightens readiness |

No DB. No async. No fixtures with random seed.

---

## Files Added / Modified

| File | Type | Purpose |
|---|---|---|
| `docs/research/B2_V2_COMPARISON_FRAMEWORK_DESIGN.md` | NEW | This doc |
| `docs/research/B2_V2_COMPARISON_RESULTS.md` | NEW | Live results template (filled by operator after first run) |
| `apps/api/src/research/b2_v2_comparison.py` | NEW | Pure analytics |
| `apps/api/src/api/b2_v2_comparison.py` | NEW | Read-only routes |
| `apps/api/src/main.py` | EDIT (add router only) | Register router |
| `apps/api/tests/unit/test_b2_v2_comparison.py` | NEW | Unit tests |
| `apps/web/src/lib/b2v2/hooks.ts` | NEW | React Query hooks |
| `apps/web/src/components/ops/B2vsV2ComparisonCard.tsx` | NEW | UI card |
| `apps/web/src/pages/Ops.tsx` | EDIT (add card mount) | Mount card |

**Files NOT modified** (verify after implementation):

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
- Any DB migration

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Verdict misread as a trigger | Card UX has no actions, only labels; doc emphasizes operator-only authority |
| Small-n false positives | `INCONCLUSIVE` short-circuit at `n < 10`; readiness gates require `n ≥ 30` |
| Tail metric noise on small windows | All percentiles computed over full window, not divergence subset |
| API surface drift | Fresh prefix `/api/b2-v2` — never collides with `/api/engine-b` or `/api/shadow` |
| Backfill gap (V2 backfilled separately from B2) | INNER JOIN drops mismatched days — confirms apples-to-apples comparison |
| Impact-weighted edge division-by-zero | Explicit guard returning NaN; test enforces |
| Regime bucket double-count | Single `b2_regime` source, partitions are exclusive; test enforces sum-equality with top-level |
| Tail guard accidentally upgrading | Guard implementation is one-way (downgrade-only); test enforces |
| Threshold drift across reviews | `TAIL_GUARD_EDGE_MIN_BPS` and verdict thresholds frozen as module-level constants; revision history must accompany any change |

---

## Acceptance Criteria

1. `pytest apps/api/tests/unit/test_b2_v2_comparison.py` — all green.
2. `GET /api/b2-v2/comparison?days=365` returns a populated bundle with verdict.
3. Ops page renders B2 vs V2 card without console errors.
4. Grep for B2/V2 module byte-equality (`git diff --stat` shows no
   touch on the "NOT modified" list).
5. `git grep "promot\|route\|cutover" apps/api/src/research/b2_v2_comparison.py apps/api/src/api/b2_v2_comparison.py` returns no execution-affecting matches.

---

## Next Steps (after approval)

1. Operator approves this design doc (reply with explicit `approved`).
2. Implement Layer 1 (analytics) + tests; run pytest.
3. Implement Layer 2 (API); smoke-test with `curl`.
4. Implement Layer 3 (UI); render on Ops page.
5. Fill `B2_V2_COMPARISON_RESULTS.md` with the first observed verdict.
6. Operator reviews verdict over 2–4 weeks of additional shadow data.
7. **Separate decision** (out of scope for this framework): if and when
   to promote V2 — handled by `engine_b_promotion.py`, never by this
   framework.
