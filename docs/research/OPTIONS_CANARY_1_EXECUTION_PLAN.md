# Canary-1 — One Real Options Lifecycle, End-to-End

**Date authored**: 2026-05-19
**Branch context**: `phase-1/ledger`
**Status**: PLAN ONLY — no implementation, no flag flips, no widening of scope
**Predecessor**: `OPTIONS_CHAIN_INGEST_RECOVERY_COMPLETE.md` (2026-05-19)

---

## Why this exists

We have:
- truthful chain telemetry (`options_chain_ingest_run`)
- stocks-side lifecycle operational
- wrapper-RC honesty enforced
- deployment-drift detection (md5 parity)
- HONEST-BANNER copy locked in UI
- dormant execution surface clearly labeled

What we **don't** have: a single, observed, deterministic options lifecycle
in production-shape paper. Until we run one and watch it close cleanly,
every Phase 1A / 1B claim is theoretical.

**Canary-1 is not a rollout.** It is the smallest, fastest, safest object
that proves the seven-stage lifecycle end-to-end:

```
proposal → fill → open → monitor → close → P&L → telemetry
```

Exactly one trade. One symbol. One strategy. One concurrent position.

If Canary-1 fires cleanly, we have data. If it stalls, we have evidence and
a clean rollback. Either outcome is more useful than continuing to wait.

---

## 1. Single-symbol scope

**Choice**: `SPY` (SPDR S&P 500 ETF Trust).

**Universe**: `["SPY"]` for canary lifecycle only. Chain ingest continues on
its current 5-symbol DEFAULT_UNIVERSE (already validated). The canary
proposal generator hard-filters to `symbol == "SPY"`.

**Justification**:

| Criterion | SPY | Alternatives considered |
|---|---|---|
| Options liquidity (avg daily volume) | ~5M contracts/day, highest in U.S. | QQQ ~2M; IWM ~1M; per-symbol equity options thinner |
| Bid/ask spread near ATM | typically $0.01–$0.05 | QQQ similar; equity names often $0.10+ |
| Strike granularity near ATM | $1 strikes within ±5% | most ETFs $0.50–$1; equities $1–$5 |
| Expiry density | Mon/Wed/Fri weeklies + monthlies | most names monthlies only |
| Already in chain ingest universe | yes (validated 2026-05-19) | n/a |
| Settlement | American-style on shares | acceptable: we never short, so no assignment exposure |
| Earnings risk | none (ETF) | single names carry binary-event risk we should not face on canary 1 |

SPY is the canonical "if it doesn't work here, it doesn't work anywhere"
options market. Any deviation from clean execution points at our system,
not the venue.

---

## 2. Single-strategy scope

**Choice**: `LONG_CALL_ATM_30DTE` — buy one ATM call on the nearest standard
monthly expiry between 25 and 45 calendar days out.

**Definition (deterministic, no ambiguity)**:

```
strategy_id        = "LONG_CALL_ATM_30DTE"
direction          = LONG
right              = CALL
n_contracts        = 1
contract_multiplier= 100
target_dte_min     = 25
target_dte_max     = 45
expiry_rule        = "first_standard_monthly_in_dte_window"
strike_rule        = "closest_to_underlying_spot_at_proposal_time"
```

**Why this and not anything else**:

| Property | Long call | Why we don't pick the alternative |
|---|---|---|
| Max loss | premium paid (bounded) | short premium → unbounded loss, assignment risk |
| Legs | 1 | spreads (2 legs) → leg-coordination + partial-fill failure modes |
| Assignment risk | none (long side) | short puts/calls → exercise + cash settlement edge cases |
| Greeks profile | clean directional delta ~0.50 | calendars/diagonals → vega + time skew complexity |
| Cash requirement | premium only | margin strategies → portfolio margin modelling not yet built |
| Failure surface | quote validity, expiry handling | multi-leg → 2× failure surface for nothing learned |

We are not testing strategy alpha. We are testing the **lifecycle plumbing**.
The strategy must be the simplest object that exercises every stage.

---

## 3. Single-position scope

**Hard caps** (enforced in code, not policy):

```
max_open_positions      = 1
max_open_proposals      = 1
max_lifecycle_per_day   = 1
max_total_canary_trades = 1   ← THE killswitch
```

Implementation pattern:
- Proposal job's first action: count rows in `options_paper_position`
  WHERE `portfolio_id = canary-spy-v1` AND `status = OPEN`. If `>= 1`,
  return `{skipped: True, reason: "canary_at_capacity"}` and write
  telemetry.
- Proposal job's second action: count CLOSED rows for canary portfolio.
  If `>= 1`, return `{skipped: True, reason: "canary_complete"}`. This is
  the one-shot guarantee — Canary-1 fires exactly once over its lifetime.

After Canary-1 closes (cleanly or rolled back), the system returns to the
exact pre-canary state until a human reads the result and decides next
steps.

---

## 4. Deterministic fill semantics

**Anchor**: next-bar discipline (mirror of stocks-side fix in commit
`60cb834`).

```
T0 = proposal_generated_at
T1 = first chain_snapshot WHERE snapshot_at_utc > T0
     AND symbol      = SPY
     AND expiry      = chosen_expiry
     AND strike      = chosen_strike
     AND option_type = CALL
```

The fill is computed against **T1**, never T0. If no T1 snapshot exists
within `MAX_FILL_WAIT = 90 minutes`, the proposal expires with reason
`no_fill:chain_anchor_missing`.

**Pricing method** (closed enum):

```
fill_price = (bid + ask) / 2          ← mid
slippage_cents = 0                     ← canary; cost modelling deferred
commission_per_contract = $0.65        ← industry retail standard
entry_dollar_cost = fill_price * 100 * n_contracts
                  + commission_per_contract * n_contracts
```

**Quote validity gates** (all must pass; otherwise reject with named
reason):

| Gate | Threshold | Reject reason |
|---|---|---|
| `bid > 0`             | strict       | `pricing_invalid:bid_zero`     |
| `ask > 0`             | strict       | `pricing_invalid:ask_zero`     |
| `ask >= bid`          | strict       | `pricing_invalid:crossed`      |
| `(ask - bid) / mid`   | ≤ 0.05       | `pricing_invalid:spread_wide`  |
| `open_interest`       | ≥ 100        | `pricing_invalid:oi_thin`      |
| `last_trade_volume`   | ≥ 10         | `pricing_invalid:vol_thin`     |
| chain row age at T1   | ≤ 15 minutes | `stale_chain:snapshot_age`     |
| underlying spot known | non-null     | `pricing_invalid:spot_missing` |

**Bid / ask / mid decision**: mid only. We are not modelling fill
aggression; mid is the deterministic, replayable choice. Realistic slippage
modelling is a Phase 1B concern.

**Side note**: we deliberately do NOT trust `last_price` from the chain
row. `last_price` is whenever the last print occurred and can be minutes
stale even on liquid names. Mid of current bid/ask is the honest quote.

---

## 5. Exit semantics

**Exit triggers** (evaluated each monitor tick, in order, first hit wins):

| Trigger | Threshold | Exit reason enum |
|---|---|---|
| Take-profit  | unrealized P&L ≥ +50% of entry premium | `tp_hit`         |
| Stop-loss    | unrealized P&L ≤ -50% of entry premium | `sl_hit`         |
| Max-hold     | calendar age ≥ 14 days from open       | `max_hold`       |
| Expiry guard | DTE ≤ 1                                | `expiry_guard`   |

Numbers chosen to maximise probability of a clean exit during canary
window. Asymmetric P&L (calls cap unrealized loss at -100%) means the
+50/-50 bracket is symmetric in dollars, not in probability — that is
acceptable for plumbing validation.

**Max-hold horizon**: 14 days. Combined with `target_dte_min = 25`, this
guarantees we never reach DTE ≤ 11 inside max-hold, leaving comfortable
buffer for `expiry_guard` to be a true safety net rather than the primary
exit path.

**Expiration handling** (the dangerous edge):

If DTE reaches 1 before any other trigger fires, force-close at the next
chain mid using the same gates as entry. Reason: prevent assignment-shape
edge cases from sneaking in even on a long call. ITM long calls auto-exercise
on real exchanges at expiry, which would change accounting from "premium
P&L" to "stock-position" — out of scope.

**Lifecycle events written** (append-only, one row per state transition,
mirror of stocks-side pattern):

```
PROPOSED               — proposal generator
PROPOSAL_EXPIRED       — proposal aged out without fill
OPENED                 — fill executed
MONITORED              — each monitor tick; carries mid, unrealized P&L, DTE
CLOSED                 — exit executed; carries close_reason enum
MANUAL_OPERATOR_PAUSE  — operator-initiated freeze (see §6a)
MANUAL_OPERATOR_CLOSE  — operator-initiated force-close (see §6a)
```

**Close accounting** (deterministic):

```
exit_credit       = exit_mid * 100 * n_contracts
exit_commission   = commission_per_contract * n_contracts
realized_pnl      = exit_credit - exit_commission
                    - (entry_dollar_cost)
final_cash        = initial_cash - entry_dollar_cost + exit_credit
                    - exit_commission
```

Ledger row written under canary portfolio. Cash invariant:
`final_cash == initial_cash + realized_pnl` (modulo tiny float
rounding; assert to 4 dp).

---

## 6. Operational safeguards

Every safeguard below answers a specific failure mode we have already lived
through this week.

| Safeguard | Failure mode it prevents |
|---|---|
| Pre-flight md5 parity check (8 files × 3 containers) | deployment drift (we hit this twice on stocks + once on options) |
| Pre-flight alembic head check                        | migration drift; ORM-vs-DB column mismatch |
| Wrapper-RC honesty (all 5 lifecycle jobs return dict) | silent-success `None`-return bug |
| Per-invocation telemetry row in `options_canary_lifecycle_run` | dashboards diverging from reality |
| Chain freshness gate before any job runs              | acting on stale quotes |
| Hard `max_total_canary_trades = 1` guard in proposal job | unintended widening |
| Canary portfolio kept `active=false` until the **proposal job itself** flips it on its first successful pre-flight | "I forgot the flag was on" |
| Cash invariant assert in close job                    | silent accounting drift |

**Worker parity check** (concrete script, to be wired into pre-flight):

```
files = [
  apps/worker/src/jobs/options_chain_snapshot.py,
  apps/worker/src/jobs/options_canary_proposal.py,        ← new
  apps/worker/src/jobs/options_canary_lifecycle.py,       ← new
  apps/api/src/options/data/chain_ingest.py,
  apps/api/src/options/data_provider/tradier_adapter.py,
  apps/api/src/options/canary/engine.py,                  ← new
  apps/api/src/config/__init__.py,
  apps/api/src/db/models.py,
]
for each container in (cron, tickloop):
  for each file:
    host_md5 == container_md5  ASSERT
```

Any mismatch → pre-flight fails → canary stays dormant → loud log line.

**Migration parity check**: `alembic current` on each container must equal
host's `alembic heads` exactly. Mismatch → pre-flight fails.

**No silent-success paths**: every new job follows the wrapper-RC contract
from D2.3:

```
{skipped: True, reason: <enum>}     → tick_loop classifies status=skipped
{return_code: !=0, reason: <enum>}  → tick_loop classifies status=error
{return_code: 0, ...}               → tick_loop classifies status=success
```

---

## 6a. Operator escape-hatch — safety valve

A canary is, by design, the moment when "the cron just keeps running" is
the wrong default. We need a way for a human to **pause** or **close** the
lifecycle without editing rows, bypassing telemetry, or fighting automation.

Two append-only events exist solely for operator use:

### `MANUAL_OPERATOR_PAUSE`

| Property | Value |
|---|---|
| Trigger        | operator-only |
| Effect         | sets canary portfolio `active = false`; next scheduled lifecycle tick observes paused state and writes `{skipped: True, reason: "manual_pause"}` |
| Position state | position remains OPEN; no force-close, no accounting mutation |
| Reversibility  | reversible only by a subsequent operator action (no automated resume) |

Required payload (all fields mandatory; row rejected at insert if missing):

```
operator_id          TEXT NOT NULL    -- human identifier, e.g. "kunal"
operator_reason      TEXT NOT NULL    -- free-text incident context, ≥ 20 chars
incident_ref         TEXT             -- optional ticket / log link
referenced_event_id  BIGINT           -- optional pointer to last good event
inserted_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `MANUAL_OPERATOR_CLOSE`

| Property | Value |
|---|---|
| Trigger        | operator-only, **only** when position is OPEN |
| Effect         | force-close at last known chain mid using the standard quote-validity gates; lifecycle CLOSED event written with reason `manual_operator_close`; cash reconciliation runs identically to automated close |
| Position state | OPEN → CLOSED |
| Reversibility  | none (append-only; the CLOSED event is the truth) |

Required payload: same as `MANUAL_OPERATOR_PAUSE`, plus:

```
mid_used                 NUMERIC NOT NULL    -- echoed for audit
chain_snapshot_at_utc    TIMESTAMPTZ NOT NULL
chain_snapshot_age_sec   INTEGER NOT NULL    -- can exceed 15-min gate; logged
quote_gates_overridden   TEXT[]              -- list of gates the operator chose to bypass, if any
```

`quote_gates_overridden` is the **only** mechanism by which the canary
quote-validity gates can be bypassed, and only by an operator, and only
under audit. Every overridden gate is named explicitly in the row — no
hidden waivers.

### Hard constraints on both events

| Constraint | Enforcement |
|---|---|
| Append-only — never mutate historical rows | DB-level: no UPDATE/DELETE on `options_trade_lifecycle_event` (existing); enforced by absence of UPDATE/DELETE code paths and grant model |
| Operator identity captured                 | `operator_id` NOT NULL; row rejected if absent |
| Operator reason captured                   | `operator_reason` NOT NULL, length ≥ 20 chars |
| Cannot be inserted by any scheduled job    | DB CHECK on inserter context OR application-level guard: writes go through a dedicated `operator_event.py` module not imported by any `apps/worker/src/jobs/*` file; CI lint enforces |
| Telemetry preserved                        | each operator action also writes one row to `options_canary_lifecycle_run` with `classification='operator_action'` and `error_summary` carrying the payload |
| Failure evidence preserved                 | operator events never delete or supersede F1–F7 rows; both coexist in the append-only log |
| No automatic resume                        | there is no `MANUAL_OPERATOR_RESUME` event; restart is a deliberate human re-enable of the portfolio `active` flag plus a recorded reasoning entry |

### Invocation surface (operator-only)

Out of scope for code in this plan, but the contract is:

- A CLI / admin endpoint that asks the operator interactively for
  `operator_id` and `operator_reason`, refuses to proceed without both,
  and writes the lifecycle row + the telemetry row in a single transaction.
- No GET / no curl-friendly shape. The intent is friction.
- Logged at INFO with the full payload (redacted only for credentials, of
  which there are none in the payload by design).

### Use cases (illustrative, not exhaustive)

- Stuck lifecycle — F4 fired but operator wants to inspect before
  force-close → `PAUSE`, investigate, then either resume by re-enabling
  the portfolio or commit with `MANUAL_OPERATOR_CLOSE`.
- Stale chain investigation — chain ingest looks suspicious but not yet
  failing → `PAUSE` while we audit.
- Telemetry mismatch — F7 fires → `PAUSE` until root-cause is known.
- Incident response — anything off, regardless of code symptom → `PAUSE`
  is always safe.
- Manual close to avoid unsafe automated cleanup — DTE-edge or pricing
  edge cases where the operator wants to choose the exit explicitly.

### Explicitly out of scope for operator events

- Routine exits. TP / SL / max-hold / expiry-guard are automated. Using
  the operator close path for a routine exit is a process violation, not
  a code error.
- Reopening a closed position. CLOSED is terminal.
- Editing past lifecycle rows. Append-only is non-negotiable.

---

## 7. Validation ladder — checkpoints

Each checkpoint is a queryable assertion in the database. Order is strict;
each gates the next.

| # | Checkpoint | Source of truth | Pass condition |
|---|---|---|---|
| C0 | Pre-flight green | log line `canary_preflight_ok=true` from proposal job | md5 + alembic + chain-freshness all pass |
| C1 | Proposal generated | `options_paper_trade` | exactly 1 row WHERE portfolio=canary-spy-v1 AND status=PROPOSED |
| C2 | Chain row available for proposed contract | `options_chain_snapshot` | row WHERE matches (symbol, expiry, strike, type) AND snapshot_at_utc > proposal_at |
| C3 | Fill succeeds | `options_trade_lifecycle_event` | row WHERE event=OPENED AND trade_id=<proposal_trade_id> |
| C4 | Position opens, cash debited | `options_paper_position` + portfolio ledger | exactly 1 row WHERE status=OPEN; ledger entry matches `entry_dollar_cost` to 2 dp |
| C5 | Lifecycle monitored | `options_trade_lifecycle_event` | ≥ 1 row WHERE event=MONITORED per scheduled lifecycle tick after C3 |
| C6 | Exit fires | `options_trade_lifecycle_event` | row WHERE event=CLOSED AND reason ∈ {tp_hit, sl_hit, max_hold, expiry_guard, manual_operator_close} |
| C7 | Cash reconciles | portfolio ledger | invariant `final_cash == initial_cash + realized_pnl` (4 dp) |
| C8 | Telemetry written every invocation | `options_canary_lifecycle_run` | row count > `job_run` row count for canary jobs (because manual + scheduled both write here) |
| C9 | UI truth state verified | OptionsPaperTradesPage + OptionsCanaryStatus | HONEST-BANNER copy unchanged; canary widget shows 1/1; lifecycle visible in trades view; no forbidden phrases (CI lint green) |

Canary-1 is declared `COMPLETE` only when C0..C9 all pass and a human has
read the result.

---

## 8. Failure classifications — predefined

Closed enum. The canary lifecycle jobs may return only one of these
failure reasons:

| Code | Trigger | Action |
|---|---|---|
| `F1_stale_chain`          | chain age > 15 min at fill or monitor | pause canary; capture last good chain row id |
| `F2_no_fill`              | no T1 snapshot within `MAX_FILL_WAIT`  | proposal expires; canary remains dormant; no position opened |
| `F3_pricing_invalid`      | any quote-validity gate fails          | proposal expires (same as F2) |
| `F4_lifecycle_stall`      | OPEN > max_hold + 1 day, no MONITORED  | force-close at last known mid; capture stall window |
| `F5_expiry_edge`          | OPEN at DTE = 0 (should have exited at DTE=1) | force-close; flag as canary-failed even if P&L OK |
| `F6_deployment_drift`     | md5 mismatch in pre-flight             | proposal job refuses to run; loud error; nothing changes |
| `F7_telemetry_mismatch`   | telemetry row count ≠ job_run count after window | pause canary; investigate before any further fire |

Each failure writes:
- `options_canary_lifecycle_run` row with `classification='error'` and
  `error_summary={code: F#, details: ...}`
- log line at ERROR level with same payload
- (if applicable) lifecycle event with reason matching the F-code

No failure path mutates the canary portfolio's `active` flag back to true.
Recovery is human-initiated.

---

## 9. Rollback posture

**On any F1–F7 firing OR operator-initiated `MANUAL_OPERATOR_PAUSE`**:

| State | Behavior |
|---|---|
| Canary portfolio `active`        | set to `false` |
| Canary proposal job              | continues to schedule but immediately skips with reason `canary_paused` |
| Canary lifecycle job             | continues to monitor existing open position (if any) until force-close or human intervention |
| Stocks-side execution            | UNAFFECTED — hard isolation via `OPTIONS_*` flags |
| Chain ingest                     | UNAFFECTED — independent of canary state |
| UI                               | HONEST-BANNER copy unchanged; canary widget shows paused + F-code; no rationale-style prose |
| Forbidden-phrase lint            | continues to enforce |
| `options_paper_trade` rows       | preserved; append-only chain intact |
| `options_canary_lifecycle_run`   | preserved; the error row IS the evidence |

**Evidence captured on failure**:

1. The telemetry row (F-code + details JSONB; or `operator_action` if
   operator-initiated)
2. Last successful lifecycle event
3. Last chain snapshot referenced
4. Frozen position state (if any)
5. Pre-flight log lines
6. For operator events: `operator_id`, `operator_reason`, `incident_ref`,
   and any `quote_gates_overridden`

This is enough to either resume manually or write a post-mortem without
re-running anything. Append-only auditing means we cannot lose state by
trying to debug it.

**Resume semantics** (after PAUSE or F-code firing):

There is no automated resume. To return the canary to running state, an
operator must:

1. Read the full evidence chain.
2. Decide whether to (a) operator-close the position, (b) leave it paused
   indefinitely, or (c) re-enable the portfolio for continued automated
   monitoring.
3. Re-enable, if chosen, is a deliberate human action recorded as a
   reasoning audit entry — not a lifecycle event. The next scheduled
   lifecycle tick then resumes normally.

Friction is the feature here.

---

## What this plan does NOT do

- No flag flip. `OPTIONS_ENABLED` and `OPTIONS_CANARY_ENABLED` remain
  `false` throughout planning.
- No paper option trade created.
- No code written. Three new modules are *named* in this plan
  (`options_canary_proposal.py`, `options_canary_lifecycle.py`,
  `options/canary/engine.py`); none exist yet.
- No new migrations applied. The `options_canary_lifecycle_run` table is
  *specified* here, not yet created.
- No UI change. HONEST-BANNER and OptionsCanaryStatus are touched only when
  the canary actually fires.
- No discussion of Phase 1A scaling. Canary-1 is one trade. After it
  closes, the next decision is a separate document.

---

## Approval gates before any code is written

In order:

1. **Plan accepted** — this document approved as-is or with concrete
   redlines.
2. **Migration approved** — `090_options_canary_lifecycle_run` reviewed
   before being authored.
3. **Module skeletons approved** — function signatures and return-shape
   contracts for the three new files, before any logic is written.
4. **Pre-flight script approved** — md5 + alembic + chain-freshness check
   reviewed before being wired into the proposal job.
5. **Dry-run on paper-paper** — proposal-only run with execution
   short-circuit, verifying C0 + C1 + C2 fire correctly. Still no fill.
6. **Single live fire** — full lifecycle. Watched.

Only after gate 5 passes do flags flip. Only after gate 6 produces a clean
`CLOSED` event and `realized_pnl` reconciles do we call Canary-1
complete.

---

## Decision now requested

Approve / redline this plan. On approval, the next concrete action is
gate 2 — author and review the telemetry migration. Nothing further moves
until that is also approved.

---

## Revision history

| Date | Change |
|---|---|
| 2026-05-19 (initial) | Plan authored |
| 2026-05-19 (rev 1)   | Added §6a operator escape-hatch: `MANUAL_OPERATOR_PAUSE` and `MANUAL_OPERATOR_CLOSE` append-only events; updated §5 event list, C6 checkpoint, §9 rollback evidence + resume semantics |
