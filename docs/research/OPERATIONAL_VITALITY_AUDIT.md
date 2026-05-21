# Operational Vitality Audit

**Date**: 2026-05-16
**Trigger**: Persistent "AI is cautious today" output reading as paralysis rather than discipline
**Methodology**: Two parallel forensic agents (code-side threshold inventory + DB-side 30-day metrics), evidence over philosophy
**Status**: Verdict reached. Tier-1 recommendations ready for implementation decision.

---

## Executive verdict

> **The system is over-constrained, not cautious. The architecture cannot trade itself out of a fully-deployed state. "AI is cautious today" is faithful UI reporting of structural paralysis, not disciplined intelligence.**

The evidence does not require interpretation. The numbers state it directly.

---

## Smoking guns (raw evidence)

| # | finding | number |
|---|---|---|
| 1 | Last paper trade executed | 2026-05-06 — 10 calendar days ago |
| 2 | Total trades in 30-day window | 44 |
| 3 | Days with zero actions in 30-day window | 26 of 31 (84%) |
| 4 | Recommendation → execution conversion | 0.5% (44 / 8,263) |
| 5 | Portfolio cash position | $536.76 of $117,869 NAV = 0.46% |
| 6 | Open positions | 40 — exceeds configured max_open=30 |
| 7 | Average position hold age | 16.5 days (against MaxHold=10d) |
| 8 | Positions held > 14 days | 40 / 40 = 100% |
| 9 | Buy recommendations at conviction ≥ 70 today | 0 of 115 |
| 10 | Trim recommendations at conviction ≥ 70 today | 195 of 196 |
| 11 | Today's dominant rejection reason | position_too_small = 68.2% |
| 12 | Today's second rejection reason | portfolio_full = 13.6% |
| 13 | Identical rejection counts on 5/15 + 5/16 | 220/150/30/20 both days |
| 14 | Intraday observations / day | ~10,000 captured |
| 15 | Intraday actions taken | 0 |
| 16 | Signal generation hours per 7-day window | 2 (07:00 + 08:00 UTC only) |
| 17 | Options shadow rejection rate (5/13) | 99.67% (7,470 / 7,495) |
| 18 | Options rejected as `top_n_capped` | 24.2% |
| 19 | Pipeline run telemetry entries (30d) | 0 |
| 20 | Shadow run telemetry entries (30d) | 0 |
| 21 | Files in codebase declaring "conservative defaults" | 15+ confirmed |

---

## Findings by section

### 1. Signal throughput + attrition waterfall

**Stock 30-day waterfall:**

```
Raw candidates       7,560  (avg 944/day, fired ~8 days of 30)
        ↓ 87.5% pass
Recommendations      8,263  (avg 826/day)
        ↓ 0.5% pass
Paper trades            44  (clustered in two bursts:
                             2026-04-27 to 04-30 = 40 trades
                             2026-05-05 to 05-06 =  4 trades
                             2026-05-07 to today =  0 trades)
```

The funnel is healthy through the recommendation stage. Catastrophic attrition occurs at the final execution gate — 99.5% of recommendations never become trades.

**Options pipeline (single day, 2026-05-13):**

```
Shadow candidates    7,495
        ↓ 0.33% pass
would_trade            25
        ↓ 0% (OPTIONS_ENABLED=false)
Paper trades            0
```

The `ranked_signal` table is empty. The intermediate stage is bypassed or never populated.

### 2. Threshold stack

**Stocks — 9-gate AND chain to execute a buy:**

```
action == "Buy"
  AND confidence >= 60                      (hardcoded, no env override)
  AND NOT already_held
  AND NOT pending_sell
  AND open_count < max_open (30)
  AND sizing_pct * equity >= min_notional   (floor: $50)
  AND sizing_pct * equity <= avail_cash     (ceiling: cash * 0.95)
  AND find_next_open_bar(asset) != NULL
  AND (alpha-rule shrink, advisory)
```

**Options — 17 gates stacked (9 shadow + 8 canary, currently dark).**
The canary configuration is intentionally micro: 1 slot, $500 max, SPY-only, BULL_CALL_SPREAD-only, DTE 21-45. Even if `OPTIONS_ENABLED=true` flipped, the canary scope is so narrow that volume would be functionally zero by design.

**Combinatorial failure modes observed:**

| failure | mechanism |
|---|---|
| Cash trap | max_open + sizing + min_notional combine to lock portfolio at near-full deployment with no recyclable cash |
| Age cliff | MaxHold=10d not honored (actual avg = 16.5d) — exit cycle either not firing or not closing |
| Confidence cliff | Hardcoded 60-floor + recommender outputs Buys clustered at 60-64 |
| Options choke | Shadow's 9 filters + canary's 8 filters = effectively zero throughput |

### 3. Almost-qualified analysis

Limited by data availability. No per-candidate score-to-threshold delta is stored.

What's recoverable:
- 0 of 115 Buy recommendations today reached conviction ≥ 70. 89 are in the 60-69 band — barely qualifying.
- 195 of 196 Trims are ≥ 70. Trim conviction is well above floor.

**Implication**: engine has high conviction in *exits* and low conviction in *entries*. Neither side is acting.

### 4. Temporal opportunity analysis

System is strictly EOD-batch:

- Candidate generation: 07:00 + 08:00 UTC only
- Recommendations: same batch window
- Auto-trader: fires once at 03:30 ET
- Exit cycle: 03:00 ET (30 min before entry)
- Intraday observations: ~10,000/day captured, used for **none** of the above

The infrastructure for intraday data exists; the infrastructure for intraday action does not.

### 5. Behavioral diversity (30 days)

**Stocks:**

| action | total | per active day |
|---|---|---|
| Buy executions | 44 | 8.8 |
| Sell executions | 0 | 0 |
| Trim executions | 0 | 0 |

Zero sells or trims executed in 30 days. Despite ~196 daily Trim recommendations at conviction 85.6.

**Options:**

| action | total |
|---|---|
| Opens | 0 |
| Closes | 0 |

Single PROPOSED canary trade from 2026-05-06, never filled.

Portfolio turnover: effectively zero.

### 6. Portfolio stagnation

- All 40 positions > 14 days old (100%)
- Avg hold = 16.5 days (violates MaxHold=10d)
- $111,453 cost basis on $117,869 NAV = 94.5% deployed
- $536.76 cash (0.46%)
- Last action = 2026-05-06 (10 days ago)
- 40 positions exceed the 30 configured max_open

The 10-day silence is structural deadlock, not caution.

### 7. Quantified "cautious today"

For 2026-05-16:

```
Total recommendations:    982
        ├── Buy:   115  (avg conv 60.6, 0 high-conviction)
        ├── Hold:  671  (avg conv 60.9, 123 high)
        └── Trim:  196  (avg conv 85.6, 195 high)

Auto-trader funnel:       220 buy-qualified candidates
Executed:                   0

Rejection breakdown:
        ├── position_too_small:  150  (68.2%)
        ├── portfolio_full:       30  (13.6%)
        ├── execution_failure:    20  ( 9.1%)
        └── (other):              20
```

UI message: *"AI is cautious today. No fresh Buy signals passed the engine's threshold."*

**Technically true but materially misleading.** No Buy signals passed the *execution* threshold. The engine *did* generate 115 Buy recommendations. They all died at the capital/inventory wall. UI claim implies conviction/quality threshold; reality is capital exhaustion.

### 8. Reality check vs sophisticated human trader

**A sophisticated human discretionary trader would NOT have produced zero actions for 10 days.**

1. 40 positions held 14+ days with no rebalancing — a human would have closed underperformers
2. 115 daily Buy recommendations being generated, none acted on — a human would have forced rotation or stopped the engine
3. Options canary with 0 trades and 1 stalled PROPOSED for 10 days — operator-absent behavior
4. Cash position $537 / $117k — no discretionary trader would let cash drift to 0.46%
5. Same exact rejection counts on consecutive days — telemetry bug or stuck state; human would have noticed within hours

The architecture **prevents** the actions a competent human would take.

### 9. Recommendations — low-risk operational fixes

#### Tier 1 — High-impact, low-risk

**R1. Fix the exit cycle (highest priority).**
MaxHold=10d should have produced ~40 close events in the last 10 days. Produced zero. Investigate `run_paper_exit_cycle.py`:
- Is the worker job scheduled?
- Is it actually running?
- Is the 10d threshold being checked against `opened_at` correctly?
- Is the close action actually writing to `paper_trade`?
- Are closes being silently rejected by a downstream gate?

**Single most consequential investigation.** If exit cycle ran correctly, ~40 positions would close, releasing $111k of cash, allowing 115 daily Buy recs to execute.

**R2. Surface recommendation→execution attrition in the funnel.**
Funnel shows decision-layer + execution-layer rejections (220 → 0). Does not show what happens between recommendation (~982/day) and buy-qualified candidates (220). Gap is ~762/day of vanished recommendations with no telemetry.

Add to `paper_execution_funnel`:
- `recs_generated`
- `recs_filtered_by_confidence`
- `recs_filtered_by_already_held`
- `recs_passed_to_execution`

**R3. Add intraday refresh cadence.**
Schedule `compute_daily_features` and `generate_stock_candidates` to fire mid-session (e.g., 13:00 ET = 17:00 UTC) in addition to the EOD batch. Unlocks the 10,000 daily intraday observations that currently dead-end.

#### Tier 2 — Medium-impact, requires alignment

**R4. Make hardcoded confidence floor config-driven.**
`buy_confidence_threshold = 60` is hardcoded with no env override. Today: 89 of 115 Buy recs in the 60-69 band — all hugging the floor. Floor needs to be configurable + instrumented.

**R5. Replace static `max_open_positions=30` with dynamic slot policy.**
Possible: "max 30 OR allocated ≥ 95% NAV, whichever first" + "release slot when position is in trim recommendation for 2 consecutive days."

**R6. Remove or relax `OPTIONS_SHADOW_TOP_N=5`.**
24.2% of options rejections are `top_n_capped`. Genuinely qualified contracts being thrown away due to artificial cap. Raise to 15-20.

**R7. Enforce funnel-stuck monitoring.**
Identical funnel counts on consecutive days should trigger an alert. Daily check: "if today's funnel == yesterday's funnel within ±5%, flag for review."

#### Tier 3 — Larger architectural changes (defer)

**R8. Build active rotation layer.**
When portfolio is 95%+ deployed AND high-conviction Buys exist AND high-conviction Trims on held positions, programmatically close lowest-conviction Trim holdings to fund highest-conviction Buys. Requires explicit policy approval.

**R9. Wire intraday observations into intraday execution.**
Build lightweight intraday loop that examines latest observation deltas and flags positions whose thesis has materially changed since the EOD recommendation.

**R10. Replace OPTIONS_CANARY single-strategy single-symbol cap with tiered canary.**
Tier-A (SPY + BULL_CALL_SPREAD, 1 slot, $500) — current.
Tier-B (top-5 underlyings, 3 strategies, 3 slots, $200 each).
Tier-C (full universe, all strategies, 5 slots, $100 each).
Same total capital ($1,500); distributed across more diverse trades.

#### What NOT to do

- Do not turn off governance. All recommendations stay paper-only. OPTIONS_ENABLED stays false until explicit decision.
- Do not remove the funnel. It's the only visibility we have. Need *more* funnel telemetry, not less.
- Do not change recommendation engine outputs. Don't lower conviction calibration; issue is downstream of the recommender.
- Do not increase `max_open_positions` beyond 30. Adding slots without solving rotation makes the problem worse.

---

## Open investigations (not resolved by this audit)

1. **Why are there 40 open positions when max_open=30?** Either positions were opened before the cap was set, or the cap is checked only on entry not maintained.

2. **Why is `ranked_signal` empty?** Either bypassed, deprecated, or never wired.

3. **Why is `pipeline_run` empty?** Either telemetry was removed, never wired, or instrumentation is on a different table.

4. **Why are 5/15 and 5/16 funnel numbers identical?** Possible: deterministic replay, synthetic aggregation, identical engine state, or funnel job writing the same row both days.

5. **Why has no exit fired in 10 days?** Highest priority code investigation per R1.

---

## Decision required before any implementation

The recommendations above are **proposed**, not approved. Each Tier 1 item touches live engine behavior and must be explicitly authorized.

Sequencing proposal:

1. **First**: investigate R1 (exit cycle) — read-only diagnostic, no system change
2. **If R1 reveals the bug**: fix exit cycle, re-run for 1 cycle, observe whether the system recovers naturally
3. **If R1 alone doesn't recover**: layer R2 (funnel telemetry expansion) — additive observability, no behavior change
4. **If still constrained**: R3 (intraday refresh) — behavior change, requires approval

Tier 2 and Tier 3 are paused until Tier 1 effects are observed.

---

## Source agents

This report consolidates findings from two forensic agents run on 2026-05-16:

- **Code-side**: every gate in stocks + options pipeline, scheduler cadence, config values, recent changes
- **Data-side**: 30-day signal throughput, rejection histograms, portfolio state, action counts, temporal patterns, almost-qualified scores, staleness metrics, today's exact composition

Full agent outputs preserved in conversation history.

---

## R1 forensic investigation — root cause identified

**Investigation date**: 2026-05-16 (same-day follow-up to initial audit)
**Conclusion**: The exit cycle is NOT broken at the scheduling layer. The bug is at the `submit_trade` next-bar guard layer. The exit cycle correctly identifies all 40 eligible positions, correctly invokes `submit_trade` for each, and `submit_trade` rejects 100% of them with the same error.

### Evidence chain

**Layer 1 — Scheduling: WORKING**

```sql
SELECT name, cron_expr, enabled, last_run_at FROM job_schedule WHERE name='run_paper_exit_cycle';
-- name: run_paper_exit_cycle
-- cron_expr: 0 23 * * 1-5  (interpreted in ET → 03:00 UTC next day)
-- enabled: true
-- last_run_at: 2026-05-16 03:00:10
```

Tick-loop scheduler is alive. Job is registered. Cron interpretation is correct. Last fire was today at 03:00 UTC.

**Layer 2 — Job execution: WORKING**

```sql
SELECT status, started_at, duration_seconds FROM job_run jr
JOIN job_schedule j ON jr.job_schedule_id=j.id
WHERE j.name='run_paper_exit_cycle' ORDER BY started_at DESC;
-- 2026-05-16 03:00:10 | success | 0.075s
-- 2026-05-15 03:00:26 | success | 0.100s
```

Status marked success on both fires. **Duration of 75-100ms is the giveaway** — script enters main, identifies positions, attempts closes, all rejected before any DB write, returns 0, wrapper marks success.

**Layer 3 — Eligibility check: WORKING**

Artifact `artifacts/paper_exit_cycle/exit_cycle_2026-05-16.json`:

```json
{
  "mode": "commit",
  "scanned": 40,
  "closed_count": 0,
  "skipped_count": 40,
  "closed": [],
  "skipped": [
    {
      "symbol": "AMZN",
      "reason": "exec_rejected:no price bar available after submitted_at; cannot fill",
      "rule": "max_hold(12d >= 10d)"
    },
    ... (40 identical rejection entries)
  ]
}
```

Eligibility logic is correct. All 40 positions correctly flagged for `max_hold` rule. The script is doing exactly what it was designed to do.

**Layer 4 — `submit_trade` fill guard: REJECTING ALL ATTEMPTS**

The script sets:

```python
submitted_at = dt.datetime.combine(
    as_of, dt.time(15, 0), tzinfo=dt.timezone.utc,
)
```

For a fire on 2026-05-16 at 03:00 UTC, `as_of` resolves to `2026-05-16` and `submitted_at` to `2026-05-16 15:00 UTC`.

`submit_trade` then calls `find_next_open` which requires:

```sql
SELECT * FROM price_bar
WHERE asset_id = :a AND ts > :submitted_at
ORDER BY ts ASC LIMIT 1
```

The latest price_bar for any asset is 2026-05-15 EOD. The exit cycle requires a bar `ts > 2026-05-16 15:00 UTC` — which would be the NEXT trading day's close, which hasn't been ingested yet.

Every fill request fails. The script catches `PaperTradeRejected` (line 308), records the rejection in the `skipped` artifact, and continues. Script exits with code 0 after writing the artifact. Wrapper marks job_run.status='success'.

**Layer 5 — Telemetry: SILENT FAILURE**

The wrapper at `apps/worker/src/jobs/run_paper_exit_cycle.py:53` swallows the result:

```python
try:
    rc = await asyncio.to_thread(_exit.main, ["--commit"])
except SystemExit as e:
    rc = int(e.code) if isinstance(e.code, int) else 1
except Exception as exc:
    logger.error(...)
    raise
finally:
    os.environ.pop(_exit.CONFIRM_ENV, None)
return {"return_code": rc}
```

The wrapper returns `{"return_code": rc}` but the tick-loop's `_execute_job` (in `apps/worker/src/scheduler/tick_loop.py:81`) calls `await job_fn()` without inspecting the return value. Any non-exception result is treated as success.

**Net effect**: 40 rejected closes per day, zero positions actually exit, every fire logged as success.

### Why this has happened for at least 11 days

The artifact directory shows:

```
exit_cycle_2026-05-04.json   ← manual operator run (per agent inventory)
exit_cycle_2026-05-06.json   ← manual operator run
exit_cycle_2026-05-14.json   ← (job_run shows no entry; possibly different fire path or manual)
exit_cycle_2026-05-15.json   ← scheduled fire — 100% rejected
exit_cycle_2026-05-16.json   ← scheduled fire — 100% rejected
```

The scheduled exit cycle only became active recently (5/15). Before then it didn't fire automatically. So:
- Before ~5/15: exit cycle didn't run → MaxHold not enforced
- After 5/15: exit cycle runs but rejects 100% due to fill guard → MaxHold still not enforced

The same outcome (zero closes) produced by two different failure mechanisms in two different windows.

### The `submitted_at` design choice — analysis

The script's choice to set `submitted_at = today at 15:00 UTC` was intentional. The comment in the script states (line 13-14):

> "fills only against a price_bar with `ts > submitted_at`. Same-bar exits are forbidden."

The intent: exits should always fill against the **next** bar, not the bar that exists when the decision is made. This prevents the script from using same-day close prices as fills (which would create lookahead bias in backtests / replay scenarios).

That design works for `auto_trader`-driven exits (which fire at 03:30 UTC and fill against the next available bar, which is today's intraday or close). But for the exit cycle running at 03:00 UTC with `submitted_at = today 15:00 UTC`, the required `price_bar` doesn't exist yet because the trading day hasn't happened.

The `auto_trader`-style submitted_at advances the timestamp far enough into the future that today's close (when ingested) will satisfy the `ts > submitted_at` predicate. But for the exit cycle, the assumption that "today's close exists at 03:00 UTC" is false — today's close happens at 21:00 UTC, 18 hours later.

### The fix space (not yet recommended — for decision)

**Fix option A — set `submitted_at` to prior day**

```python
submitted_at = dt.datetime.combine(
    as_of - dt.timedelta(days=1), dt.time(15, 0), tzinfo=dt.timezone.utc,
)
```

The exit decision is based on yesterday's close (as already done via `_latest_close`). Setting `submitted_at` to yesterday at 15:00 UTC means `find_next_open` will resolve to **today's** close bar (when ingested ~21:00 UTC) or the most recent EOD.

But this changes the temporal semantics: exits would fill against the close after the decision was made, which is "next-bar" but in the EOD model.

**Fix option B — schedule the exit cycle AFTER `ingest_prices_daily` runs**

Currently both fire on 5/15 and 5/16 windows. If we ensure exit cycle runs after the new day's bars are ingested (i.e., at ~22:00 ET = 02:00 UTC after the bar ingestion at 02:00 UTC), the latest bar will be available and the next-bar guard can resolve.

Actually checking job_schedule:
```
ingest_prices_daily   cron: 0 22 * * 1-5    → ET 22:00 = UTC 02:00 next day
run_paper_exit_cycle  cron: 0 23 * * 1-5    → ET 23:00 = UTC 03:00 next day
```

So ingest fires at UTC 02:00 and exit fires at UTC 03:00, one hour later. The bars SHOULD be available. **But the exit cycle sets `submitted_at = today 15:00 UTC` which is 12+ hours in the future relative to the bar that just ingested.** The ingested bar has `ts = today 00:00 UTC` (typical price_bar timestamping for daily EOD bars), so even with the bar present, `today 00:00 > today 15:00` is false.

This means the bar timestamping convention is also part of the problem. The system stores daily bars at midnight UTC, but the exit cycle's `submitted_at` is mid-day UTC. The temporal model is inconsistent between these two components.

**Fix option C — change the `submit_trade` next-bar predicate**

Allow same-day fills against the most recent bar for exit-cycle-originated trades. This would require a flag/parameter on `submit_trade` and a relaxation of the lookahead-bias guard.

**Fix option D — change `submitted_at` to a date-only comparison**

Cast both sides to date and compare. Allows today's bar to satisfy "today or later." Subtle semantics change.

### Recommendation discipline

Before any fix lands, this needs:
1. Explicit decision on which fix option (each has different tradeoffs around lookahead-bias prevention, paper-trading integrity, replay correctness)
2. Backtest of the change against historical replay scenarios
3. A confirmation that the funnel telemetry will correctly reflect the new fill behavior

**Do not patch directly.** This is a load-bearing temporal-semantics decision.

### Cascade of consequences from this single bug

Because the exit cycle silently rejects 100% of closes:

1. No positions ever close on age/TP/SL → portfolio fills to max_open
2. Portfolio at 99.5% deployment → no cash for new buys
3. Daily Buy recs (~115) all hit `position_too_small` or `portfolio_full` → 0 executions
4. UI sees `counts.buy === 0 && counts.sell === 0` → renders "AI is cautious today"
5. User interprets the message as discipline → trust erodes when it persists

**Single root cause. Five-layer cascade.** Fix the root, the cascade resolves.

---

## Standing locks

- Phase K creative-direction work is paused
- No CSS, no UI changes, no Phase K artifact production until R1 path completes
- Current J-rev1 frontend state held
- **No fix applied yet to the exit cycle** — fix-option decision required from operator
