# Options Phase 1A / 1B activation — pre-implementation plan

**Status**: Plan only. NO code changes. NO flag flips. NO migrations.
**Date**: 2026-05-19, post-HONEST-BANNER cleanup.
**Goal**: avoid every category of stocks-side failure we recently surfaced:
- hidden structural blockers (anchor math)
- assumed functionality (deployment drift)
- silent-success jobs doing zero work (telemetry dishonesty)
- UI ahead of operational reality (PickModal placebo)

If we approach options the same casual way stocks were approached, we will rediscover the same bugs. This plan front-loads the hard problems.

---

## 0. EXISTING ASSETS (what we already have)

Before planning what to build, we inventory what's done. Do not re-build.

### Already shipped
- 16 DB tables with full multi-leg / Greeks / lifecycle schema
- 10 alembic migrations (047 → 077) applied to dev DB
- ORM models in `apps/api/src/db/models.py`
- 5 worker jobs registered in cron (2 stubs + 3 active research jobs)
- 9 API router files (~20 GET endpoints)
- 22 UI pages routed under `/options/*`
- HONEST-BANNER global cleanup (today)
- OPTIONS_STATE_CLASSIFICATION memo (today)
- Library functions exist for: `persist_option`, `transition_to_fill`, `transition_to_close`, `transition_to_expired`, `transition_to_assigned`
- Provider integration: Tradier sandbox active for chain ingest (but stale — see §4)
- Shadow eval observing decisions (7505 historical rows, dormant since 2026-05-13)
- Canary portfolio definition: `canary-spy-v1`, $2000 cash, SPY only, BULL_CALL_SPREAD only, 1 open max, $500/trade max risk, `active=false`

### Not yet shipped (the actual gap)
- Phase 1A body: `options_canary_promotion` worker job stub returns `{skipped: True}` 
- Phase 1B body: `options_lifecycle_check` worker job stub returns `{skipped: True}`
- Chain freshness guarantee (currently stale since 2026-05-13 — must fix BEFORE Phase 1A)
- Container deployment hygiene for options code
- Telemetry honesty for chain ingest (currently "success" with 0 new rows)
- UI rollout copy contract per phase

The plan covers the GAP, not the assets.

---

## 1. PHASE 1A — PROMOTION LIFECYCLE (candidate → proposal)

### Trigger
`options_canary_promotion` worker job. Cron `00 22 * * 1-5` ET. Already wired; body is stub.

### Pre-conditions (all must be TRUE or job exits cleanly)
1. `OPTIONS_ENABLED = true`
2. `OPTIONS_CANARY_ENABLED = true`
3. `options_paper_portfolio` row `canary-spy-v1` has `active = true`
4. **Fresh chain data exists** — `options_chain_snapshot` has rows with `snapshot_at_utc::date = today` (today, NOT historical)
5. **Today's shadow eval ran** — `options_shadow_decision_log` has rows for today

If any precondition fails, job returns `{skipped: True, reason: "<specific>"}` with named reason. NOT silent success.

### Step-by-step algorithm

```
1. Lookup canary portfolio (canary-spy-v1)
   - If active=false: skip with reason "canary_portfolio_inactive"
   - Read max_open_trades, max_capital_per_trade

2. Count current open trades for this portfolio
   - If open_count >= max_open_trades: skip with reason "portfolio_full"

3. Source today's shadow decisions
   - SELECT FROM options_shadow_decision_log
     WHERE DATE(created_at) = today
       AND would_trade = true
       AND underlying IN (OPTIONS_CANARY_UNIVERSE)  -- e.g. ('SPY')
       AND strategy_name = OPTIONS_CANARY_STRATEGY  -- 'BULL_CALL_SPREAD'
   - If empty: skip with reason "no_qualifying_shadow_decisions"

4. Apply DTE window filter
   - For each candidate, lookup proposed legs' min_expiry
   - DTE = (min_expiry - today).days
   - Keep if OPTIONS_CANARY_MIN_DTE <= DTE <= OPTIONS_CANARY_MAX_DTE  (default 21-45)
   - If empty: skip with reason "no_candidates_in_dte_window"

5. Rank by composite_score descending; take top 1 (max 1/day in Phase 1A)

6. Build leg specs from chain
   - For each leg (long call + short call for bull_call_spread):
     - Lookup most recent options_chain_snapshot for (underlying, expiry, strike, option_type)
     - If quote_age_seconds > OPTIONS_MAX_QUOTE_AGE_SECONDS (e.g. 600): reject
     - Capture bid, ask, mid, iv, delta, gamma, theta, vega
   - If ANY leg fails quote freshness: skip whole proposal with reason "stale_quotes_on_legs"

7. Compute proposed structure economics
   - net_debit = (long_leg.ask - short_leg.bid) × 100   [paper-accurate worst-case]
   - max_loss = net_debit
   - max_profit = (long_strike - short_strike) × 100 - net_debit
   - breakeven_lower = long_strike + (net_debit / 100)

8. Risk cap check
   - If net_debit > max_capital_per_trade: skip with reason "over_capital_cap"
   - If portfolio.cash_current < net_debit: skip with reason "insufficient_cash"

9. Compute proposal_hash for idempotency
   - hash(run_date, underlying, strategy_name, [(leg_idx, expiry, strike, option_type, side)])
   - If exists in options_paper_trade: skip with reason "duplicate_proposal_today"

10. Call persist_option.persist_option(...)
    - Creates options_paper_trade row with status='PROPOSED', proposal_hash set
    - Creates options_paper_trade_leg rows
    - DOES NOT decrement cash yet (cash debits at fill time, not proposal time)

11. Write options_execution_funnel row
    - portfolio_id, run_date, candidates_evaluated, candidates_after_dte,
      candidates_after_risk_cap, candidates_promoted, skip_reasons_json
```

### Failure classification (named skip reasons)

Every job-exit path must emit ONE of these reasons (no `"unknown"`):

| Code | Meaning |
|------|---------|
| `canary_disabled` | OPTIONS_CANARY_ENABLED=false |
| `master_disabled` | OPTIONS_ENABLED=false |
| `canary_portfolio_inactive` | `active=false` on portfolio row |
| `no_fresh_chain_data` | No chain rows for today (PROTECTS against stale-chain promotion) |
| `no_shadow_decisions_today` | shadow_eval hasn't run or produced no decisions |
| `no_qualifying_shadow_decisions` | shadow rows exist but none match universe/strategy |
| `no_candidates_in_dte_window` | DTE filter eliminated all |
| `stale_quotes_on_legs` | Specific legs have quote_age > threshold |
| `portfolio_full` | open_count >= max_open_trades |
| `over_capital_cap` | net_debit > max_capital_per_trade |
| `insufficient_cash` | portfolio.cash_current < net_debit |
| `duplicate_proposal_today` | proposal_hash collision |
| `provider_error:<type>` | Tradier API error, network, etc. |
| `internal_error:<exception_class>` | Catchall, but MUST include class name |

This explicit classification prevents "success with 0 work" pattern.

### Telemetry contract

- ONE row in `options_execution_funnel` per (portfolio_id, run_date) — even on skip
- Row includes per-stage skip counts
- `job_run.status` reflects actual work: 'success' = work done OR explicit skip with reason; 'error' = exception
- Wrapper-RC honesty: returning `{skipped: True}` already classifies as 'skipped' in tick_loop (D2.3 work)

### What NOT to build in Phase 1A
- Multi-strategy support (only BULL_CALL_SPREAD)
- Multi-day proposals
- Multi-leg beyond 2-leg spreads
- Cross-asset hedging
- ML-driven candidate scoring (already forbidden by `OPTIONS_ML_CAN_AFFECT_TRADES=false`)

### Estimated effort
~2-3 focused days of implementation + testing.

---

## 2. PHASE 1B — FILL LIFECYCLE (PROPOSED → OPEN)

### Trigger
`options_lifecycle_check` morning pass. Cron `30 13 * * 1-5` ET. Already wired; body is stub.

### Pre-conditions
1. Same OPTIONS_ENABLED / OPTIONS_CANARY_ENABLED checks as Phase 1A
2. At least one PROPOSED row exists in `options_paper_trade` with `opened_at::date < today`
3. **Fresh chain data exists for today** (snapshot_at_utc::date = today, strictly greater than proposal's opened_at::date — this is the next-bar discipline)

### Next-bar discipline (analog to stocks-side anchor fix)

**CRITICAL** — this is where stocks went wrong. Restate the rule explicitly:

A proposal made on day D with `opened_at::date = D` MUST fill against a chain snapshot with `snapshot_at_utc::date > D`.

If today is D+1 and today's chain exists, fill at today's chain quotes.
If today is D+1 and today's chain DOES NOT exist, **DO NOT FILL**. Return skip with reason `next_bar_chain_unavailable`.

This prevents the stocks "today 15:00 UTC > tomorrow 00:00 UTC" math error — phrased differently for options because chain timestamps are intraday (snapshot_at_utc could be e.g. today 17:47 UTC), not start-of-day. The rule is **strictly greater date**, not strictly greater timestamp.

### Step-by-step algorithm

```
For each PROPOSED trade where opened_at::date < today:

  1. Lookup latest chain snapshots for each leg (most recent by snapshot_at_utc)
     - If ANY leg has no snapshot: skip with reason "leg_chain_missing"
     - If ANY leg's snapshot_at_utc::date <= opened_at::date: skip with reason 
       "next_bar_chain_unavailable"

  2. Recompute fill prices using DEFAULT_FILL_MODEL ('mid_plus_25_pct_spread')
     - For long leg: fill_price = ask - 0.25*(ask - bid)  [favorable to us; conservative]
       Actually: fill_price = mid + 0.25*spread  for BUY side
     - For short leg: fill_price = mid - 0.25*spread  for SELL side (we collect less premium)
     - net_debit_actual = (long.fill - short.fill) × 100
     - If net_debit_actual > 1.10 × proposal's entry_credit_dollars: skip with 
       reason "fill_price_drift" (slippage too high)

  3. Multi-leg atomicity
     - Both legs fill OR neither
     - If we cannot get both fresh quotes, neither fills

  4. Cash check at fill time
     - If portfolio.cash_current < net_debit_actual: 
       skip with reason "insufficient_cash_at_fill"

  5. Begin DB transaction
     - INSERT options_paper_position (portfolio_id, trade_id, capital_reserved, 
       opened_at=now())
     - UPDATE options_paper_trade SET status='OPEN', entry_credit_dollars=net_debit_actual
     - UPDATE options_paper_portfolio SET cash_current = cash_current - net_debit_actual
     - UPDATE options_paper_trade_leg SET entry_bid=..., entry_ask=..., entry_mid=...,
       entry_iv=..., entry_delta=..., etc. (capture fill-time Greeks)
     - INSERT options_trade_lifecycle_event (trade_id, kind='filled', 
       snapshot_id=<chain_snapshot_id>, payload_json={fill_prices, slippage_pct, ...})
     - COMMIT

  6. On exception: rollback, skip with reason "fill_exception:<class>"
```

### Spread / multi-leg handling

- Bull call spread = 2 legs: long lower-strike call + short higher-strike call
- BOTH legs are paper-atomic — either both record entry quotes or neither
- Cash debit is the NET (long.fill_debit - short.fill_credit) × 100 × qty
- Position represents the SPREAD, not individual legs (capital_reserved = max_loss)

### Cash accounting (paper, deterministic)

```
At fill:    cash_current -= net_debit × 100 × qty   (debit for long debit spread)
At close:   cash_current += exit_credit × 100 × qty  (credit for unwinding)
At expiry:  cash_current += intrinsic_value_at_expiry × 100 × qty
At assign:  cash_current += assignment_payoff (per assignment-precedence rule)
```

Capital reserved is tracked separately (in `options_paper_position.capital_reserved`) so we know "how much is committed" vs "how much is in pure cash."

### Failure classification (named skip reasons)

| Code | Meaning |
|------|---------|
| `leg_chain_missing` | One of the legs has no chain snapshot at all |
| `next_bar_chain_unavailable` | Chain exists but only on/before opened_at date |
| `fill_price_drift` | Fill economics worse than 110% of proposal entry |
| `insufficient_cash_at_fill` | Cash dropped between proposal and fill |
| `fill_exception:<class>` | DB error, integrity violation, etc. |

### Telemetry contract
- Each PROPOSED trade processed produces a row outcome (filled/skipped) logged to the same `options_execution_funnel` table OR a new `options_fill_funnel` table
- `options_trade_lifecycle_event` is the audit chain — every status transition logs here

### Estimated effort
~3-4 focused days. Most complex piece: the multi-leg atomicity + cash accounting + slippage model interplay.

---

## 3. CLOSE LIFECYCLE (OPEN → CLOSED / EXPIRED / ASSIGNED)

### Trigger
`options_lifecycle_check` afternoon pass + scheduled expiry check at OPEX time.

Could run as the SAME cron job (afternoon pass at e.g. 15:30 ET) or split — TBD during implementation.

### Step-by-step

```
For each OPEN trade:

  1. Lookup latest chain snapshot for each leg
     - If ANY leg has no fresh snapshot: skip with reason 
       "close_chain_unavailable" (do not force close on stale data)

  2. Compute current spread mid
     - long_current = (long_bid + long_ask) / 2
     - short_current = (short_bid + short_ask) / 2
     - spread_mid_current = (long_current - short_current) × 100
     - unrealized_pct = (spread_mid_current - entry_credit_dollars) / entry_credit_dollars

  3. Evaluate exit rules in order:
     a. EXPIRY: if any leg expires today → goto expiry handler
     b. TAKE_PROFIT: unrealized_pct >= OPTIONS_TARGET_PCT (e.g. 0.50)
        → close with reason 'target_hit'
     c. STOP_LOSS: unrealized_pct <= -OPTIONS_STOP_PCT (e.g. -0.50)
        → close with reason 'stop_hit'
     d. DTE_STOP: min(leg.expiry - today).days <= OPTIONS_TIME_STOP_DTE (e.g. 7)
        → close with reason 'time_stop'
     e. None triggered → skip with reason 'no_rule_triggered'

  4. If closing:
     - Compute exit prices using fill model (mid + 25% spread, OPPOSITE direction)
     - Begin transaction
     - UPDATE options_paper_trade SET status='CLOSED', closed_at=now(),
       exit_debit_dollars=..., realized_pnl_dollars=...
     - UPDATE options_paper_position SET closed_at=now(), released_capital=...
     - UPDATE options_paper_portfolio SET cash_current += exit_credit
     - INSERT options_trade_lifecycle_event (kind='closed', payload with exit details)
     - COMMIT
```

### Expiry handler

```
At expiry (last trading day of options or earlier):

  Compute intrinsic_value for each leg at the underlying's closing price:
    CALL intrinsic = max(0, underlying_close - strike)
    PUT  intrinsic = max(0, strike - underlying_close)

  For BULL_CALL_SPREAD specifically:
    Both OTM → spread expires worthless. Realized = -entry_debit.
    Long ITM, short OTM → long exercises for (underlying_close - long_strike).
    Both ITM → max profit = (short_strike - long_strike) - entry_debit.

  Multi-leg assignment precedence (if a short leg is ITM):
    - SHORT call ITM → assignment risk. For paper, treat as auto-assigned:
      we deliver underlying at strike, receive strike × 100 in cash.
      Net effect for spread: capped payoff per max_profit calculation.

  Insert options_expiration_event (or options_assignment_event)
  Transition trade to status='EXPIRED' or 'ASSIGNED'
```

### Reconciliation rules
- Realized P&L written ONCE per trade, at terminal transition
- `options_paper_portfolio.cash_current` updates ATOMICALLY with status transition (same transaction)
- `options_paper_position.closed_at` set ATOMICALLY (no orphan open positions)
- `options_trade_lifecycle_event` row written for every state change

### Failure classification

| Code | Meaning |
|------|---------|
| `close_chain_unavailable` | Cannot get fresh quote to evaluate |
| `close_exception:<class>` | DB error during close transaction |
| Lifecycle terminal states | `closed`, `expired`, `assigned` |
| Lifecycle skipped | `no_rule_triggered` |

### Estimated effort
~3-4 focused days. Most complex: expiry / assignment precedence.

---

## 4. CHAIN-DATA INTEGRITY (BLOCKER — must resolve BEFORE Phase 1A)

### Current state (evidence from audit)

- `options_chain_snapshot`: 6561 rows, ALL `snapshot_at_utc = 2026-05-13 17:47:27 UTC`
- Single point-in-time snapshot from Tradier sandbox
- Cron `options_chain_snapshot` runs daily, last run 2026-05-19 01:30 UTC, status='success', duration 74 sec
- **No new rows since 2026-05-13.** Cron silently produces zero new data.

### Hypotheses (need investigation BEFORE Phase 1A)

1. **Tradier sandbox returns same snapshot** — sandbox accounts may be rate-limited or return a fixed historical point
2. **INSERT ON CONFLICT DO NOTHING dedup** — same chain values dedup'd against existing rows (natural key on snapshot_at_utc + underlying + expiry + strike + option_type)
3. **Provider auth expired** — credentials silently rejected after 7 days
4. **Universe empty** — `DEFAULT_UNIVERSE` no longer matches subscription tier
5. **Silent per-symbol exceptions** — ingest catches per-symbol errors and continues; overall job reports success

### Required investigation steps (NOT yet performed)

1. Read `apps/api/src/options/data/chain_ingest.py::ingest_universe` to understand its error handling
2. Manually call Tradier sandbox API and see what it returns
3. Inspect logs from the 2026-05-19 01:30 UTC chain_snapshot run for per-symbol exceptions
4. Check `OPTIONS_CHAIN_INGEST_*` env vars vs config defaults
5. Verify network egress from worker container reaches Tradier

### Freshness guarantee (proposed contract)

After investigation + fix, the contract must be:

- Chain snapshot job inserts rows with `snapshot_at_utc::date = today` on every successful trading-day run
- If 0 new rows are inserted: job MUST return `{skipped: True, reason: "no_new_chain_rows", detail: "<why>"}` — NOT `{status: success}`
- New telemetry: `options_chain_ingest_run` table with per-run row count + error details

### Stale-chain detection

Both Phase 1A (promotion) and Phase 1B (fill) must check chain freshness as a HARD precondition:

```python
def assert_fresh_chain_for_today(session) -> None:
    latest = session.execute(
        text("SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot")
    ).scalar()
    today_utc = dt.datetime.now(dt.timezone.utc).date()
    if latest is None or latest.date() < today_utc:
        raise StaleChainError(
            f"latest chain snapshot is {latest}; today is {today_utc}. "
            f"Phase 1A/1B refuse to operate on stale chain data."
        )
```

This refuses to silently skip — it raises, surfaces, and forces operator attention.

### Cron honesty (mirrors stocks wrapper-RC honesty work, D2.3)

The chain ingest wrapper must classify accurately:
- Inserted N>0 rows: `success`
- 0 rows because no new data exists upstream: `skipped` with reason
- Exception: `error` with traceback

Currently it ALWAYS returns success regardless of work done.

### Telemetry requirements

New table proposal: `options_chain_ingest_run`

```sql
CREATE TABLE options_chain_ingest_run (
    id              bigint PRIMARY KEY,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz,
    provider        text NOT NULL,
    universe        text[] NOT NULL,
    rows_inserted   integer NOT NULL,
    rows_deduplicated integer NOT NULL,
    rows_failed     integer NOT NULL,
    provider_errors jsonb,
    duration_sec    numeric(8,3),
    classification  text NOT NULL  -- 'success' | 'no_new_data' | 'error'
);
```

This is the analog of `envelope_generation_run` from the stocks side. Telemetry-of-truth.

### Estimated effort (chain integrity work alone)
~1-2 days to investigate + fix + add telemetry. Should land BEFORE Phase 1A begins.

---

## 5. DEPLOYMENT DISCIPLINE (prevent stocks-style drift)

### Lesson from stocks (forensic record)

On 2026-05-19 we discovered `paper_service.py` and `models.py` were stale on worker containers since 2026-04-19. Phase L D1.4 deployed them to compose-api-1 but NEVER to compose-worker-cron-1 or compose-worker-tickloop-1. Exit cycle was broken for ~3 weeks; the cron reported `status=success` because the OLD script didn't call the NEW signature.

We will not repeat this.

### File manifest for Phase 1A activation

ANY of these touched MUST be deployed to all 3 containers before flag-flip:

**New/modified worker code:**
- `apps/worker/src/jobs/options_canary_promotion.py` — body replaces stub
- `apps/worker/src/jobs/options_lifecycle_check.py` — body replaces stub (Phase 1B)

**Library functions called by new bodies:**
- `apps/api/src/options/persist_option.py`
- `apps/api/src/options/lifecycle.py`
- `apps/api/src/options/data/chain_ingest.py` (for chain freshness fix)

**ORM/schema:**
- `apps/api/src/db/models.py` — if any new columns added
- New migrations for `options_chain_ingest_run` table

**Config:**
- `apps/api/src/config/__init__.py` — if new OPTIONS_* settings added

### Pre-flag-flip checklist

Before EITHER `OPTIONS_ENABLED=true` OR `OPTIONS_CANARY_ENABLED=true`:

- [ ] All files in manifest deployed to `compose-api-1`
- [ ] All files in manifest deployed to `compose-worker-cron-1`
- [ ] All files in manifest deployed to `compose-worker-tickloop-1`
- [ ] All migrations applied (`alembic current` matches expected head)
- [ ] Container-parity check passes: each file's md5 matches host
- [ ] Worker containers restarted
- [ ] Restart logs show no import-error / no DB-schema-mismatch
- [ ] Manual run of new code in isolation (not yet flag-gated) confirms no exceptions

### Container-parity check (proposed script)

```bash
# infra/ops/check_container_parity.sh
manifest=(
  apps/worker/src/jobs/options_canary_promotion.py
  apps/worker/src/jobs/options_lifecycle_check.py
  apps/api/src/options/persist_option.py
  apps/api/src/options/lifecycle.py
  apps/api/src/options/data/chain_ingest.py
  apps/api/src/db/models.py
)
containers=(compose-api-1 compose-worker-cron-1 compose-worker-tickloop-1)
for f in "${manifest[@]}"; do
  host_md5=$(md5sum "$f" | cut -d' ' -f1)
  for c in "${containers[@]}"; do
    container_md5=$(docker exec "$c" md5sum "/app/$f" | cut -d' ' -f1)
    [ "$host_md5" = "$container_md5" ] || echo "DRIFT: $c missing $f"
  done
done
```

Run BEFORE every flag flip. Run weekly as a cron health check.

### Migration coupling rule

Any options migration MUST be applied to the DB BEFORE the code that references its new columns is deployed. Specifically:

1. Write migration
2. Apply migration via `alembic upgrade head` against dev DB
3. Verify column exists
4. ONLY THEN deploy code that imports the new column
5. Restart containers
6. Verify code can import + DB roundtrip works

This sequencing was violated during stocks-side (M079 → models.py was deployed before workers got the file). We enforce it explicitly for options.

### CI lint extension (proposed)

Add `infra/ci/constitutional_checklist/container_parity_lint.py` that ensures the manifest list in source matches what's actually deployed. Run in CI on every PR touching the manifest files.

### Estimated effort
~0.5 days to write parity script + CI hook. Standalone work, can land BEFORE Phase 1A.

---

## 6. VALIDATION LADDER (gated progression)

Each step must PASS before the next is attempted. No skipping.

### Level 0 — Chain integrity (prereq)
- [ ] Investigation memo for stale chain published (per §4)
- [ ] `options_chain_ingest_run` telemetry table added + populated
- [ ] Chain snapshot job classifies honestly (`skipped` on no-new-data)
- [ ] At least 3 consecutive days of fresh chain data ingested
- [ ] Stale-chain detection raises in Phase 1A precondition check

**Gate**: cannot proceed to Level 1 until 3 consecutive trading days of fresh chain data.

### Level 1 — Single proposal end-to-end
- [ ] Phase 1A body shipped
- [ ] Deploy manifest confirmed across 3 containers
- [ ] Flag `OPTIONS_ENABLED=true`, `OPTIONS_CANARY_ENABLED=true`, canary portfolio `active=true`
- [ ] Manual run of `options_canary_promotion`
- [ ] **EXPECTED RESULT**: 1 row in `options_paper_trade` with `status='PROPOSED'`, 1 row in `options_paper_trade_leg`(s), 1 row in `options_execution_funnel`, NO change to `cash_current`, NO row in `options_paper_position`

**Gate**: actual matches expected exactly. If anything differs, investigate.

### Level 2 — Single fill end-to-end
- [ ] Phase 1B morning pass body shipped (NOT close logic yet)
- [ ] Deploy manifest confirmed
- [ ] Wait for next-bar chain to arrive (next day's chain data ingested)
- [ ] Manual run of `options_lifecycle_check` morning pass
- [ ] **EXPECTED RESULT**: trade transitions PROPOSED→OPEN, 1 row in `options_paper_position`, 1 row in `options_trade_lifecycle_event` with kind='filled', `cash_current` decremented by net_debit, leg rows updated with entry quotes + Greeks

**Gate**: position counts and cash math reconcile exactly.

### Level 3 — Position holds across day
- [ ] Wait 1 day
- [ ] Re-run `options_lifecycle_check`
- [ ] If no exit rule triggered: trade remains OPEN; **EXPECTED**: skip with reason 'no_rule_triggered'

**Gate**: no spurious transitions, no double-execution.

### Level 4 — Single close end-to-end
- [ ] Phase 1B afternoon pass + close logic shipped
- [ ] Either wait for TP/SL trigger OR force-close via `--force-close-all` operator override
- [ ] Manual run
- [ ] **EXPECTED RESULT**: trade transitions OPEN→CLOSED, `realized_pnl_dollars` set, `cash_current` credited, `options_paper_position.closed_at` set, lifecycle event kind='closed' written

**Gate**: P&L math reconciles, cash + position + trade row all consistent in same transaction.

### Level 5 — One expiry cycle
- [ ] Wait for an OPEN trade to approach expiry
- [ ] Manual run of expiry handler
- [ ] **EXPECTED**: trade transitions to EXPIRED with correct intrinsic-value payoff, `options_expiration_event` row written

**Gate**: payoff math matches intrinsic value computation. Cash reflects correct outcome.

### Level 6 — One assignment cycle (if a short leg expires ITM)
- [ ] Same as Level 5 but with short-leg ITM
- [ ] **EXPECTED**: trade transitions to ASSIGNED, assignment precedence rule applied, `options_assignment_event` row written

### Level 7 — Phase L envelope attachment
- [ ] Phase L reasoning envelopes attach to options trades
- [ ] `reasoning_audit` source='live' with `asset_class='options'`
- [ ] Skeleton: `IV_COMPRESSION_SETUP` reachable

**Gate**: envelope hash deterministic; matches an equivalent existing fixture if one exists.

### Level 8 — Canary observation period
- [ ] 4-6 weeks of daily canary runs
- [ ] Per-day funnel telemetry monitored
- [ ] No economic anomalies (e.g. negative cash, position cap violated)
- [ ] No silent skips with reason `internal_error:*`
- [ ] Realized P&L distribution falls within expected range for BULL_CALL_SPREAD

**Gate**: operator review approves broadening.

### Level 9 — Broader activation
- [ ] Expand universe beyond SPY
- [ ] Expand strategy beyond BULL_CALL_SPREAD
- [ ] Raise daily promotion cap from 1 to N
- [ ] Add additional portfolios

Out of scope for this plan. Decision after Level 8 only.

---

## 7. UI TRUTH CONTRACT DURING ROLLOUT

The banner copy must change in lockstep with operational state. Defined phases:

### Phase 0 — current state (post-HONEST-BANNER)

**Banner**: "Options lifecycle is currently dormant"
**Body**: "These pages show research, candidates, and observation surfaces. No simulated options trades are running — no fills, no closes, no P&L. The execution path is intentionally unshipped pending Phase 1A / 1B activation."

State markers:
- `OPTIONS_ENABLED=false`
- canary portfolio `active=false`

### Phase 1A canary armed (Level 1 passes)

**Banner**: "Options canary armed — proposals only"
**Body**: "A single-portfolio canary now generates one strategy proposal per trading day (SPY only, BULL_CALL_SPREAD only). Proposals are recorded but not yet filled. No cash is debited until Phase 1B activates fills."

State markers:
- `OPTIONS_ENABLED=true`
- `OPTIONS_CANARY_ENABLED=true`
- canary portfolio `active=true`
- Phase 1B body still stub

### Phase 1B fill-enabled (Level 2-4 pass)

**Banner**: "Options canary executing — single-portfolio paper fills"
**Body**: "Proposals now fill against next-bar chain data and close on take-profit / stop-loss / time-stop rules. SPY only, BULL_CALL_SPREAD only, 1 open at a time, $500 max per trade. Real paper P&L is recorded."

State markers:
- All flags as above
- Lifecycle bodies shipped
- At least 1 successful fill+close cycle observed

### Post-canary observation (Level 8 passes)

**Banner**: "Options canary observation — 6 weeks complete, evaluating broader activation"
**Body**: "The canary has run end-to-end for 6 weeks. Operator review is in progress."

### Broader activation (Level 9)

**Banner removed** or replaced with the parity-with-stocks banner that says nothing special (options is just another paper-trading surface).

### Banner state machine

```
[Phase 0: dormant]
   ↓ Level 1 passes
[Phase 1A: armed]
   ↓ Levels 2-4 pass
[Phase 1B: executing]
   ↓ Level 8 passes
[Post-observation]
   ↓ operator decision
[Broader: parity]
```

Each transition is a UI copy commit. ONE FILE: `apps/web/src/components/options/OptionsPaperOnlyBanner.tsx`. The transition happens AS the corresponding operational state is achieved. UI never leads operational reality.

### Implementation prerequisite for UI

A new backend endpoint: `GET /api/v2/options/lifecycle-state` returning one of `{dormant, armed, executing, observation, broad}`. UI banner reads this rather than hard-coding the copy. Same pattern as the Phase L truth-banner endpoint planned for UI-2.

This means Phase 1A also requires:
- Backend state endpoint
- Frontend conditional banner rendering

~1 day additional effort but tightly coupled to truth contract.

---

## 8. PREVENTING ANTI-PATTERNS (lessons from stocks)

Cross-cutting principles to bake into the implementation:

### 8.1 No silent success
Every `{"skipped": True}` return MUST include a named reason from a closed enum. No `"unknown"`. No `"other"`. If we don't know the reason, that's a bug.

### 8.2 Telemetry-of-truth
Each job writes a row to a telemetry table whose schema mirrors the job's responsibilities. The cron `status='success'` is necessary but not sufficient — the telemetry row must also reflect actual work.

### 8.3 Atomic transitions
All state changes (trade.status, position.is_open, portfolio.cash_current, lifecycle event) happen in ONE DB transaction. No half-written states.

### 8.4 Preconditions raise, not skip
For hard-required preconditions (chain freshness, valid portfolio config), the job RAISES with a clear message. Soft preconditions (no candidates today) skip with a named reason.

### 8.5 Deploy parity
Container-parity script runs in CI. New file = new manifest entry = new parity check.

### 8.6 Fill anchor explicit
The next-bar rule is a load-bearing invariant. Add a CI lint analogous to `resolver_anchor_lint.py`:

```python
# infra/ci/constitutional_checklist/options_fill_anchor_lint.py
# Verifies options_lifecycle_check.py uses
# `snapshot_at_utc::date > opened_at::date` (NOT `>=`, NOT `>` on
# raw timestamps, NOT same-day fills).
```

### 8.7 No UI without backend state
UI banner reads from backend state endpoint. Banner copy cannot drift from operational reality.

### 8.8 Honest absence
If a query returns no rows, the UI says so plainly. Don't fabricate. Don't substitute a "computed" state.

---

## 9. WORK BREAKDOWN (recommended sequence)

In dependency order:

| Phase | Item | Effort | Blocks |
|-------|------|--------|--------|
| Prep | Chain ingestion investigation + fix + telemetry | 1-2d | EVERYTHING |
| Prep | Container parity script + CI hook | 0.5d | flag flip |
| Prep | Options fill-anchor lint script | 0.5d | flag flip |
| Prep | Backend lifecycle-state endpoint | 0.5d | UI |
| 1A | `options_canary_promotion` body | 2-3d | Level 1 |
| 1A | Validation Level 1 | 0.5d | next |
| 1A→1B | UI banner state machine + conditional render | 0.5d | parallel |
| 1B | `options_lifecycle_check` morning fill pass | 2-3d | Level 2 |
| 1B | Validation Level 2 | 0.5d | next |
| 1B | Afternoon close pass + expiry handler | 2-3d | Level 4-5 |
| 1B | Validation Levels 3-7 | 1-2d | observation |
| Obs | Canary observation period | 4-6 weeks | broader |

**Estimated effort to reach Level 4 (one full cycle observed)**: ~10-15 focused days of implementation across all areas, then 4-6 weeks of canary observation.

**Critical path**: chain integrity fix BEFORE anything else.

---

## 10. WHAT THIS PLAN DELIBERATELY DEFERS

To prevent scope creep during activation:

- Multi-strategy support (only BULL_CALL_SPREAD in canary)
- Multi-portfolio support (only canary-spy-v1)
- Cross-asset hedging (none)
- ML scoring of options proposals (`OPTIONS_ML_CAN_AFFECT_TRADES=false` enforced)
- Real-time execution (no intraday; daily decision cadence)
- Greeks-based portfolio risk aggregation (per-trade only)
- Implied volatility surface modeling (use individual quotes)
- Provider redundancy (Tradier sandbox only)
- Live-money trading path (`OPTIONS_PAPER_ONLY=true` enforced)
- Options-specific Phase L vocabulary expansion (use existing skeleton when applicable)
- UI redesign of options surface (banner-only changes per state)

Any of these can be added in Phase 2+ AFTER canary observation completes.

---

## 11. NEXT DELIVERABLE (when this plan is approved)

Single decision needed from operator:

**Do we authorize beginning chain integrity investigation (Prep phase)?**

If yes:
- Read `chain_ingest.py` end-to-end (read-only)
- Probe Tradier sandbox manually
- Document why no rows since 2026-05-13
- Propose minimal fix
- Re-engage with that fix proposal

If no:
- Plan stays on file
- Options remains in HONEST-BANNER dormant state
- No code change

---

## CLOSING NOTE

The stocks-side experience taught us four things:
1. Bugs hide in places where success looks like success
2. Deployment drift compounds silently
3. UI ahead of operational reality erodes trust
4. Anchor math is load-bearing and easy to get wrong

This plan front-loads all four into the activation sequence. Chain integrity is the analog of the bar-anchor bug. Container parity is the analog of the paper_service.py drift. UI banner state machine is the analog of honest-absence. Named skip reasons are the analog of wrapper-RC honesty.

If we implement this plan in this order, with these gates, we will not repeat stocks' mistakes. We will instead surface options' specific failure modes early, before any user is misled.

No code today. Awaiting authorization to begin chain integrity investigation as the first concrete step.
