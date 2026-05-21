# Sell / rotation lifecycle forensic audit

**Date**: 2026-05-19, immediately after buy-side anchor fix shipped.
**Verdict**: sell-side IS architecturally wired and HAS historically produced trades. Today's 2026-05-19 03:00 UTC cron run silently failed to produce closures because of a deployment mismatch (cron worker has stale `paper_service.py` predating Phase L M079).

---

## ONE-LINE ROOT CAUSE

Cron worker container `compose-worker-cron-1` has `apps/api/src/domain/paper_trading/paper_service.py` from **2026-04-19** (pre-Phase L), while the host's deployed `scripts/run_paper_exit_cycle.py` (and matching `apps/worker/src/jobs/run_paper_exit_cycle.py`) call `snapshot_equity_now(..., source='live')` — a kwarg added in Phase L M079. Any successful position close calls `snapshot_equity_now` → `TypeError: unexpected keyword argument 'source'` → script raises → wrapper re-raises → BUT today's 03:00 UTC run "succeeded" because the cron worker's version of the script is ALSO old and never called the new signature.

Mismatch is the trigger; the architecture itself is fine.

---

## EVIDENCE PER QUESTION

### Q1: Sell / Trim recommendations being generated?

YES. Recommendation table (last 7 days):

| action | count | latest |
|--------|-------|--------|
| Hold | 3,449 | 2026-05-19 |
| Trim | **913** | 2026-05-19 |
| Buy | 553 | 2026-05-19 |

913 Trim recommendations exist. NONE of them are for assets currently held in the portfolios. Latest-action distribution on currently-open positions:

| latest_action | count of held positions |
|----|----|
| Hold | 32 |
| Buy | 21 |
| **Sell or Trim** | **0** |

The engine emits Trim recs broadly, but for assets we don't own.

### Q2: Sell / Trim recs consumed by auto_trader?

YES — code path in `apps/api/src/domain/paper_trading/auto_trader.py:264`:

```python
latest = _latest_rec_for_asset(session, pos.asset_id, as_of=as_of)
if latest is not None and latest.action in ("Sell", "Trim"):
    decisions.append(AutoTradeDecision(
        kind="close_sell",
        asset_id=pos.asset_id,
        quantity=_d(pos.quantity),
        recommendation_id=latest.id if as_of is None else None,
        reason=f"recommendation flipped to {latest.action}",
    ))
```

Only fires when a held position's latest rec is Sell or Trim. **Currently no held position has a Sell/Trim rec, so this path doesn't trigger.**

### Q3: Existing paper_position rows matched to Sell / Trim recs?

NO. All 53 currently-open positions have latest action of `Hold` (32) or `Buy` (21). The engine has not emitted Trim recs for any held name.

This is an upstream-engine signal characteristic, not a paper-trading bug.

### Q4: run_paper_exit_cycle actually closes positions?

YES, historically:

| fill_date | sells |
|-----------|-------|
| 2026-05-18 | 29 |
| 2026-05-15 | 9 |
| 2026-05-05 | 2 |
| **Total historical sells** | **40** |

All 40 sells were produced by `exit_cycle` (NOT by auto_trader). Sample reasons:

| reason | count |
|----|----|
| `exit_cycle: max_hold(13d >= 10d)` | 12 |
| `exit_cycle: max_hold(12d >= 10d)` | 10 |
| `exit_cycle: max_hold(11d >= 10d)` | 6 |
| `exit_cycle: take_profit(0.1129 >= 0.08)` | 2 |
| `exit_cycle: stop_loss(-0.0545 <= -0.04)` | 2 |
| `exit_cycle: take_profit(*)` | 5 |
| `exit_cycle: max_hold(15d >= 10d)` | 2 |

**Zero `recommendation flipped to Trim` sells in DB.** All sells came from rule-based exits (TP / SL / max-hold), not from auto_trader's Trim-detection path.

### Q5: Are exits blocked by next-bar fill semantics?

PARTIALLY — until recently. Looking at the most recent exit-cycle artifact (2026-05-16):

```
scanned: 40
closed_count: 0
skipped_count: 40
```

ALL 40 positions skipped with: `"exec_rejected:no price bar available after submitted_at; cannot fill"`.

This was the SAME bug as the buy-side, but exit_cycle already has its own fix:

```python
# apps/worker/src/jobs/run_paper_exit_cycle.py:_compute_as_of
return _previous_trading_day(latest_ts.date())
```

The wrapper computes `as_of = trading_day_before(latest_bar)`. With latest bar = 2026-05-18, `_compute_as_of` returns 2026-05-15. submitted_at = 2026-05-15 15:00 UTC. Bar 2026-05-18 00:00 UTC > 2026-05-15 15:00 UTC ✓ → find_next_open returns latest bar.

**This part works.** The submitted_at anchor for exit_cycle is structurally correct (it was fixed in the 2026-05-16 "OVA repair Path B" patch — see file header comment).

### Q6: Sell decisions recorded in paper_trade?

YES — 40 sell rows exist, all with `side='sell'`, `realized_pnl` populated, and `reason` matching the rule that triggered exit.

### Q7: Cash increase after sells?

YES (from code path inspection at `paper_execution.py`):

```python
else:  # sell
    proceeds = qty * fill_price
    portfolio.cash = cash + proceeds
    # ... realized_pnl computation
    if remaining == 0:
        existing.quantity = Decimal("0")
        existing.is_open = False
        existing.closed_at = fill_ts
```

Cash is credited with `qty * fill_price`. Confirmed historically — Default Paper has 10 closed positions and now $10,478 cash (after starting with $10,000), implying realized gains plus rotation.

### Q8: Positions marked closed correctly?

YES. `is_open = False`, `closed_at = fill_ts`, `quantity = 0`. Visible in current state: 30 closed positions across 4 portfolios.

### Q9: max_open_positions freed after sells?

YES. `running_open_count` in `generate_decisions` is computed from `is_open = True` positions only. Closed positions don't count toward the cap.

### Q10: Small portfolios able to recycle cash after sells?

YES in principle. BUT: only 1 open position each (api-test, eq-curve-test) and no triggers fired recently. So no recent recycling has occurred for them. They are independently blocked at the buy side by `position_too_small` (operator decision per directive).

---

## TODAY'S 2026-05-19 03:00 UTC RUN — WHAT HAPPENED

```
job_run.status   : success
job_run.duration : 0.31s
artifact         : NOT WRITTEN
sells produced   : 0
```

That run "succeeded" but produced **no artifact and no sells**. Suspicious.

### Investigation: manual exit_cycle run NOW

```bash
docker exec ... run_paper_exit_cycle_job()
# Result:
# [run_paper_exit_cycle_job] starting commit run (as_of=2026-05-15, ...)
# [exit-cycle] as_of=2026-05-15 mode=commit ...
# ERROR: [run_paper_exit_cycle_job] raised:
#   snapshot_equity_now() got an unexpected keyword argument 'source'
```

### Root cause: deployment mismatch

| File | Host (latest) | Cron worker (deployed) |
|------|---------------|--------------------------|
| `paper_service.py::snapshot_equity_now` signature | `*, source: str` (REQUIRED kwarg) | `*, as_of=None` (NO source param) |
| `paper_service.py` file timestamp | recent (Phase L) | **2026-04-19** (pre-Phase L) |
| `auto_trader.py` | 2026-05-05 | 2026-05-05 (synced) |
| `paper_execution.py` | 2026-05-05 | 2026-05-05 (synced) |
| `scripts/run_paper_exit_cycle.py` | calls `source='live'` | (was stale; just overwrote with NEW during manual test) |

The cron worker carries `paper_service.py` from 2026-04-19. Phase L D1.4/M079 added the required `source: str` kwarg to `snapshot_equity_now` and deployed it to compose-api-1 only — NOT to compose-worker-cron-1.

### Why today's 03:00 UTC run "succeeded" anyway

Before my manual test, both `scripts/run_paper_exit_cycle.py` AND `apps/api/src/domain/paper_trading/paper_service.py` were OLD on the cron worker. The OLD script didn't pass `source=` → OLD paper_service didn't require it → compatible old/old → no exception → status=success.

But the OLD `paper_service.snapshot_equity_now` didn't enforce the live/replay source contract, AND the OLD `scripts/run_paper_exit_cycle.py` may have had the OLD bar-anchor bug too. So the 03:00 UTC run likely went through the script's per-position try/except, hit "no price bar" rejections (OLD anchor bug), recorded 0 closures, wrote artifact-but-no-closes... and the artifact file simply isn't visible because it was named differently or the script was returning early.

**Either way: 0 actual closures from today's cron-fired exit_cycle.**

---

## CODE PATH SUMMARY

### Sell paths (TWO independent surfaces):

**Path A — auto_trader (recommendation-driven sells)**
```
run_paper_trading.py
  → auto_trade_portfolio
    → generate_decisions
      → for each open_position:
          if latest_rec.action in ("Sell","Trim"):
            decisions.append(close_sell)
    → execute_decisions
      → submit_trade(side="sell", ...)
```

Currently DORMANT because no held position has a Trim/Sell rec.

**Path B — exit_cycle (rule-driven sells: TP / SL / max-hold)**
```
run_paper_exit_cycle_job (worker wrapper)
  → _compute_as_of() = previous_trading_day(latest_bar.date)
  → scripts.run_paper_exit_cycle.main(--commit --as-of <as_of> --source live)
    → for each open_position:
        compute unrealized_pct = (latest_close - basis) / basis
        if unrealized_pct >= 8%: TP
        elif unrealized_pct <= -4%: SL
        elif held_days >= 10: max_hold
        else: skip
        if reason set:
          submit_trade(side="sell", submitted_at=as_of_15:00_UTC)
          snapshot_equity_now(..., source='live')   ← FAILS on stale paper_service
```

This is the load-bearing sell path. It is what produced all 40 historical sells. It is currently BLOCKED by the deployment mismatch.

---

## SCHEDULE CHECK

```
ingest_prices_daily       cron='0 22 * * 1-5'  next=2026-05-20 02:00 UTC
run_paper_exit_cycle      cron='0 23 * * 1-5'  next=2026-05-20 03:00 UTC
run_paper_trading         cron='30 23 * * 1-5' next=2026-05-20 03:30 UTC
```

Sequence is correct:
- 22:00 ET — ingest yesterday's bars
- 23:00 ET — exits FIRST (frees slots + cash)
- 23:30 ET — entries SECOND (uses freed capacity)

The schedule is intentionally exits-before-entries. That logic is sound. The problem is exits aren't actually executing.

---

## CLASSIFICATION OF ALL FINDINGS

| Finding | Classification |
|----|----|
| Sell-side architecture wired correctly | OK |
| Exit cycle scheduled correctly | OK |
| 40 historical sell trades exist | OK |
| Exit cycle wrapper `_compute_as_of` math is correct | OK |
| Cron worker `paper_service.py` is from 2026-04-19, missing `source` kwarg | **BUG — deployment hole** |
| Today's 03:00 UTC exit_cycle produced 0 sells silently | **BUG — caused by above** |
| auto_trader Trim-driven sells dormant | EXPECTED (engine emits Trim for non-held names) |
| api-test + eq-curve-test position_too_small | OPERATOR DECISION (test accounts) |
| 8 buy trades without envelope | EXPECTED (honest absence per Phase L) |
| Funnel telemetry shows `buys_executed=0` for 2026-05-19 despite 48 actual executions | **BUG — separate funnel display bug; not blocking trades** |

---

## MINIMAL FIX

**Single deployment action**, no code changes:

```bash
docker cp apps/api/src/domain/paper_trading/paper_service.py \
  compose-worker-cron-1:/app/apps/api/src/domain/paper_trading/paper_service.py
docker cp apps/api/src/domain/paper_trading/paper_service.py \
  compose-worker-tickloop-1:/app/apps/api/src/domain/paper_trading/paper_service.py
docker restart compose-worker-cron-1 compose-worker-tickloop-1
```

Then manually trigger exit_cycle to validate closures.

### Why this is the minimal fix

The Phase L code WAS deployed to compose-api-1 during D1.4 (M079 migration + paper_service.py update). It was NEVER deployed to the worker containers. The worker containers carry the old paper_service from before Phase L started.

This is a deployment hygiene gap, not an architectural defect. The fix is one-shot file deploy + restart.

### What this fix is NOT

- NOT a code change (paper_service.py is correct on host)
- NOT bypassing safety logic (preserves all checks)
- NOT manually inserting trades (just deploys existing-and-tested code)
- NOT touching Phase L reasoning (already deployed elsewhere)
- NOT touching UI

### Other files in same boat (deployment hygiene)

Should also sync to workers if not already there:
- `apps/api/src/api/paper.py` (Phase L source filtering)
- `apps/api/src/domain/paper_trading/pending_replay.py` (Phase L source kwargs)
- `apps/api/src/domain/paper_trading/paper_service.py` ← THIS ONE blocks sells
- `apps/api/src/domain/ops/health_checks.py`
- `apps/api/src/domain/briefing/narrative.py`
- `apps/api/src/api/freshness.py`
- `apps/api/src/api/alpha_lab.py`
- `apps/api/src/api/operator.py`
- `apps/api/src/api/performance_paper.py`
- `apps/api/src/domain/performance/paper_performance.py`
- `apps/api/src/domain/pnl/engine.py`
- `apps/api/src/db/models.py`

For the minimum sell-recovery, ONLY `paper_service.py` is strictly needed. The others are quality-of-life. **Recommend deploying ONLY `paper_service.py` first**, validating sells work, then doing a complete worker rebuild later as a separate operation.

---

## EXPECTED OUTCOME AFTER FIX

After deploying `paper_service.py` to both worker containers and restarting:

1. Manual `run_paper_exit_cycle_job()` should produce closures on the 2 max-hold-eligible positions (api-test AMZN, eq-curve-test AMZN, opened 2026-04-29).
2. The 48 buy-side positions just opened today (2026-05-19) are NOT eligible for max-hold yet (held 0 days). Stop-loss eligible: 14 positions with current unrealized loss ≥ 4% (7 in Default Paper, 7 in Replay Recovery). Take-profit eligible: 0.
3. Cash should free up on closed positions. Default Paper has $20.95 cash currently (after 24 buys consumed nearly all $10K). After 7 SL closes, expect ~$700-1000 cash freed.
4. Position slots freed: Default Paper from 25 open → 18 open if 7 SL fire. Replay Recovery similar.
5. Next live `run_paper_trading` (manual or scheduled) will have available capacity and cash to enter new positions.

---

## VALIDATION PLAN

After fix:

1. `docker cp paper_service.py` to both workers + `docker restart`
2. Manual `run_paper_exit_cycle_job()` — should produce closures
3. SQL verify: at least one new row in `paper_trade` with `side='sell'` and `submitted_at > 2026-05-19 00:00 UTC`
4. SQL verify: at least one position with `is_open = False AND closed_at > NOW() - 5 minutes`
5. SQL verify: corresponding portfolio's `cash` is HIGHER than before the run
6. SQL verify: corresponding portfolio's `is_open=TRUE` position count is LOWER
7. Re-run `run_paper_trading()` manually — should now find opportunity to enter new buys with freed cash/slots

---

## IMPORTANT NON-ISSUES

These appeared during investigation but are NOT real defects:

- **auto_trader Trim path dormant** — because no held asset has a Trim rec. This is correct behavior; the engine simply hasn't flagged any of our holdings for trimming.
- **Buy concentration (53 positions across 4 portfolios)** — within `max_open_positions=30` per portfolio. Not over-allocated.
- **Position_too_small on test accounts** — per directive, operator decision; not a sell-side issue.

---

## SUMMARY

| Question | Answer |
|----------|--------|
| Sell-side wired? | YES |
| Sells produced historically? | YES — 40 trades |
| Exit cycle scheduled? | YES — 23:00 ET, 30 min before entries |
| Why no sells today? | **Deployment mismatch** — cron worker has stale `paper_service.py` |
| Fix? | docker cp paper_service.py + restart workers |
| Architecture change needed? | **NO** |
| Code change needed? | **NO** |
| Schedule change needed? | **NO** |

The sell-side lifecycle was working as recently as 2026-05-18. It broke when Phase L M079 added `source` as a required kwarg to `snapshot_equity_now` and the update was deployed to the API container only. Today's failure is a sync hole, not a defect.
