# Intraday Context Overlay — Architecture Proposal

> **Phase 16 (architecture-only).** Adds a 15-min delayed intraday
> context layer ON TOP OF the existing EOD-only recommendation
> pipeline. NOT yet implemented; this is the proposal that must be
> reviewed + approved before any code lands.
>
> **v1 design stance (operator decision, 2026-05-12):** intraday
> context is treated as **ephemeral observational state**, not durable
> trading state. v1 lives entirely in the api container's memory —
> no DB table, no migration, no retention cron. The §"Upgrade path
> to durable storage" section documents the conditions under which
> Phase 2+ would promote to a persisted schema.
>
> **Hard rules carried forward from the user's brief:**
> - No fake real-time
> - No high-frequency trading behavior
> - **No same-bar execution** (the `find_next_open()` T+1 rule stays)
> - No scheduler changes until approved
> - No live broker logic
> - Paper-only enforced
> - **No new persistent schema in v1** — overlay is in-memory only
>   until usefulness, threshold quality, UX noise level, and operator
>   trust are validated

---

## Pipeline anchors (audit findings)

The existing pipeline is strictly EOD. Key file:line references for every
integration question:

| Anchor | Location | Behavior |
|---|---|---|
| **Recommendation generation** | `apps/api/src/domain/recommendations/recommendation_engine.py:498` `run_for_account()` | Reads 400 days of `timeframe='1d'` daily bars via `load_series()`; cron 22:30 ET Mon–Fri |
| **Recommendation table writer (sole)** | `recommendation_engine.py:380-462` `persist()` | Single writer; idempotent on `(asset_id, model_version, snapshot_hash)` UNIQUE index |
| **Paper-trade fill rule** | `apps/api/src/domain/paper_trading/paper_execution.py:135-162` `find_next_open()` | `PriceBar.ts > after_ts` — strict next-bar T+1; **no same-bar execution path exists** |
| **Lookahead guard** | `apps/api/src/domain/features/stock_factor_engine.py:4-6` | `ts < datetime(as_of, 00:00, UTC)` prevents using today's bar in feature math |
| **Scheduler cron defs** | `scripts/seed_symbols.py:28-64` | ingest 22:00 → recs 22:30 → score 23:00 → paper 23:30, all Mon–Fri ET |
| **Conviction column** | `apps/api/src/db/models.py:315` `Recommendation.conviction` | 0–100 EQUITY_NUM; computed at generation time |
| **Regime fields** | `apps/api/src/db/models.py:383-385` `RecommendationOutcome.{trend,volatility,drawdown}_regime` | String(16); populated by score_outcomes.py:126 (overnight) |
| **Urgency column** | none | No `urgency` column exists today; would be additive |
| **Intraday code paths** | `packages/signal_schema/signal.py:17` `Timeframe = Literal["1d", "1h", "15m"]` | Type defined but unused; zero builders consume 1h/15m |
| **Annotation / "X changed" table** | none | No `recommendation_annotation` or `signal_event` table; would be additive |
| **Paper-only enforcement** | structural | No broker API integration anywhere; tables are `paper_*` only. Options have explicit `OPTIONS_PAPER_ONLY=true` flag |

The audit found **zero active intraday code paths**. The 15m/1h enum
value exists but nothing reads it. This means a clean greenfield for
the overlay — no legacy intraday surface to integrate with.

---

## 1. Proposed intraday feature set

The overlay computes a small set of qualitative + quantitative
signals from the existing market tape data plus per-symbol Polygon
snapshots. **Observational only — never written into the
recommendation feature vector.**

| Feature | Definition | Source | Update cadence |
|---|---|---|---|
| `intraday_change_pct` | `(price - prevDay.c) / prevDay.c * 100` | tape cache (already computed) | 90s |
| `vs_open_pct` | `(price - day.o) / day.o * 100` when day session started | Polygon snapshot `day` block | 90s |
| `vs_recommendation_entry_pct` | symbol price vs recommendation's `entry_reference_price` (added if not present) | derived | 90s |
| `vs_macro_drift_pct` | `intraday_change_pct(symbol) - intraday_change_pct(SPY)` | derived | 90s |
| `intraday_range_pct` | `(day.h - day.l) / day.o * 100` (intraday volatility proxy) | Polygon snapshot `day` block | 90s |
| `material_move_today` | boolean: `abs(intraday_change_pct) > 2 * symbol's 60d daily ATR%` | derived from intraday + EOD `price_bar` | 90s |
| `context_label` | qualitative bucket: `aligned` / `drift` / `stress` / `windfall` / `quiet` | rule-based from the four above | 90s |

**Thresholds for `context_label` (initial draft, subject to tuning):**
- `aligned`   — `|vs_recommendation_entry_pct| < 0.5σ` AND `|vs_macro_drift_pct| < 0.5%`
- `drift`     — `|vs_recommendation_entry_pct| ∈ [0.5σ, 1.5σ]`
- `stress`    — `vs_recommendation_entry_pct < -1.5σ` AND position is open
- `windfall`  — `vs_recommendation_entry_pct > +1.5σ` AND position is open (drives "trim?" hint)
- `quiet`     — pre-market or post-market or absolute intraday change <0.2%

σ here is the symbol's 60-day daily-return standard deviation
(already computed by `feature_engine.py`).

---

## 2. Model input changes

**None.** This is the load-bearing decision of the proposal.

The recommendation generator (`recommendation_engine.run_for_account()`)
continues to consume only `timeframe='1d'` bars. The overlay is a
**sidecar** that reads the recommendation's outputs and decorates them
with observed intraday context. The `Recommendation` table gets zero
new columns.

Why this matters:
- Preserves `snapshot_hash` idempotency — re-running today's recs
  produces the same output regardless of intraday context drift.
- Keeps the lookahead guard in `stock_factor_engine.py:4-6` intact.
- Keeps walk-forward backtest fidelity (intraday data is not
  available historically for free, and mixing intraday-aware
  features into the model would invalidate the EOD backtest).
- Lets us turn the entire overlay off via a single feature flag
  without disturbing the recommendation pipeline.

---

## 3. UX changes

### Per-recommendation overlay (additive)

Each recommendation card in `/overview` / `/action-queue` / `/portfolio`
gets a single optional sub-line below the existing thesis text:

| `context_label` | Copy template | Example |
|---|---|---|
| `aligned` | *Today aligned · {symbol} {±%} vs morning thesis* | Today aligned · NVDA −0.3% vs morning thesis |
| `drift` | *Today drifting · {symbol} {±%}, watching* | Today drifting · QQQ +0.9%, watching |
| `stress` | *Today under stress · {symbol} {−%} vs entry · {vs_macro} vs SPY* | Today under stress · TSLA −2.4% vs entry · −1.1% vs SPY |
| `windfall` | *Today gained sharply · {symbol} +{%} · review trim* | Today gained sharply · NVDA +3.1% · review trim |
| `quiet` | (no sub-line rendered — recommendation card unchanged) | — |

Same calm institutional tone as existing copy. No emojis, no color
flash, italic, `var(--fg-3)`, font-size 11px. Always shows the
`15m delayed · Polygon` source qualifier on hover (tooltip).

### "Today changed because…" annotations (deferred)

Reuses the existing `overview_memory.ts` diff pattern. Only triggers
when:
1. The same recommendation was visible on the user's last visit, AND
2. The `context_label` has crossed a threshold since the last visit
   (e.g. `aligned` → `stress`), AND
3. The change happened today (UTC date matches).

Renders as a one-line callout above the recommendation card:
*"Since your last look: TSLA moved from aligned to under stress
(−2.4% vs entry)."*

Strict cap: max 3 such callouts per page render. Cards that haven't
crossed a threshold show no callout. This avoids "noisy terminal"
feel.

### Confidence / risk / urgency *display overlays*

The recommendation's stored `conviction` (0–100) stays unchanged. The
UI may render a **display-only** adjustment shown as a delta:
*"Conviction 78 · today's context −5 (stress signal)"*

The adjustment is a deterministic function of `context_label` and is
never persisted. Toggleable via the same feature flag.

**Urgency** is a NEW concept — there's no `urgency` column today.
Proposing to derive it on the fly in the UI from `(context_label,
days_since_recommendation, position_size)` rather than persisting.
Keeps the schema additive-free for the first cut.

---

## 4. Governance rules

Hard locks for the overlay layer:

1. **Intraday context NEVER writes to the `recommendation` table.**
   Sole writer remains `recommendation_engine.persist()`. Audited
   via the existing UNIQUE-index dedup at `models.py:315-330`.
2. **Intraday context NEVER triggers a paper trade.** The paper
   trade runner at `apps/worker/src/jobs/run_paper_trading.py:33`
   fires only on the 23:30 cron via `auto_trade_portfolio()`. No
   new caller paths.
3. **Intraday context NEVER influences sizing.** Position sizing
   stays in the EOD pipeline. The overlay's `vs_recommendation_entry_pct`
   is observational only.
4. **The `find_next_open()` next-bar fill rule is untouched.** The
   audit confirmed at `paper_execution.py:135-162` this is the
   authoritative no-same-bar gate. Any future intraday-trade
   proposal must explicitly justify weakening this; this proposal
   does not.
5. **Feature flag gate.** `INTRADAY_OVERLAY_ENABLED` env var, default
   `false`. When false, the new table is read-only (poller doesn't
   write), the API endpoint returns empty, and the UI doesn't render
   sub-lines. Single off-switch.
6. **Symbol allow-list.** Poller only fetches snapshots for symbols
   that match: (a) macro tape (`SPY`, `QQQ`, `DIA`), (b) symbols
   with at least one OPEN paper position, (c) symbols on today's
   active recommendation list. Reuse the existing universe-resolver
   in `recommendation_engine.py` to compute the set. Recomputed
   when the recommendation cron completes; cached otherwise.
7. **Polling cost cap.** Hard upper bound: 100 symbols. If the
   resolved set exceeds 100, the poller logs a warning, sorts by
   priority (open position > active rec > macro), and truncates.
8. **No scheduler changes.** This proposal adds only the existing
   market-tape poller's symbol set + a new derivation hook. No new
   cron, no new `JobSchedule` row, no change to the existing four
   jobs.

---

## 5. Execution rules

Spelled out explicitly to leave no ambiguity:

- Daily recommendation cron at 22:30 ET — **unchanged**
- Paper-trade cron at 23:30 ET — **unchanged**
- T+1 next-bar fill at `find_next_open()` — **unchanged**
- Snapshot-hash dedup at `_find_existing_by_snapshot()` — **unchanged**
- Lookahead guard `ts < as_of` — **unchanged**
- Intraday context derivation runs **only after the market-tape
  poller successfully refreshes** (already exists, 90s cadence).
  If the poller is unavailable, the overlay endpoint returns
  `stale: true` and the UI renders no sub-lines.
- No new write paths to `paper_trade`, `paper_position`,
  `recommendation`, or `recommendation_outcome` tables.

**If a future phase proposes intraday paper-trade triggers**, it
must pass a separate review covering:
- Updated dedup story (snapshot_hash isn't keyed on intraday data)
- Updated next-bar rule (the audit confirmed no same-bar code path
  exists; an intraday trade would need one — major review)
- Updated walk-forward backtest (currently EOD-only)
- Updated paper-only governance (currently structural; would need
  an explicit env-flag analog to `OPTIONS_PAPER_ONLY=true`)

This proposal does **not** ask for any of that.

---

## 6. Cache / storage plan — v1 ephemeral

**v1 stores nothing in the database.** Intraday context is
observational, not durable trading state. Until usefulness +
threshold quality + UX noise level + operator trust are validated,
persistence is over-investment. The overlay lives entirely in the
api container's memory and rebuilds on every poll cycle.

### In-memory cache (the only storage in v1)

Extend the existing `api/market.py` module with a second cache
parallel to `_cache: _Cache` (the tape cache):

```python
@dataclass
class _OverlayEntry:
    recommendation_id: str
    symbol: str
    context: dict          # the derived context dict (see §1)
    derived_at: float      # epoch seconds (server clock when we wrote)
    quote_ts: float | None # source-reported delayed ts
    source: str            # "polygon"
    delay_minutes: int     # 15

# Keyed by recommendation_id. Latest entry per recommendation only —
# overwritten each cycle. No history.
_overlay_cache: dict[str, _OverlayEntry] = {}
```

**Cache properties:**
- **Latest snapshot only** — no history kept; each cycle overwrites
  the prior entry. The "Today changed because…" diff (deferred to
  Phase E) cannot be implemented until we promote to durable
  storage in Phase 2+.
- **Lifetime = api container lifetime.** On restart, the cache is
  empty until the first poll cycle (~90s) repopulates it. The UI
  shows no sub-lines during that window. Acceptable for ephemeral
  observational context.
- **Bounded size.** ~50 entries steady-state (one per active
  recommendation in the symbol allow-list). At 200B/entry, ~10 KB
  total — irrelevant for memory.
- **Stale gating identical to the tape cache.** If the poller falls
  more than `STALE_AFTER_SECONDS` (300s) behind, the read endpoint
  returns empty.

### Poller integration (single new call site)

When the existing tape `_poll_once` completes successfully, it now
also:
1. Computes the active symbol allow-list (resolver — see §4 rule 6)
2. (existing) Calls Polygon for the full set
3. (existing) Writes the tape cache
4. **NEW**: Calls `derive_intraday_context_for_active_recommendations()`
5. **NEW**: Replaces `_overlay_cache` with the freshly derived dict
   (full overwrite, no merge)

Step 4 is the only new code path. Step 5 is a single dict assignment.
**No migration. No retention cron. No schema change.**

### Read path

Two new endpoints, both read `_overlay_cache` directly:
- `GET /api/recommendations/{recommendation_id}/intraday-context` — latest entry, or 404 if not in cache
- `GET /api/recommendations/intraday-context?symbols=NVDA,QQQ` — bulk lookup by symbol set, returns latest entry per match

Both endpoints read the in-memory dict only — no upstream call,
no derivation on the request path. p95 latency under 5 ms (no DB
hit).

### What the v1 ephemeral cache CANNOT do

Honest enumeration of the deliberate v1 trade-offs:
- No history → no diff annotations ("Today changed because…" is
  Phase E, gated on Phase 2 storage)
- No restart durability → first 90s after a deploy show no sub-lines
- No backfill → if Polygon outage clears, sub-lines reappear only
  after the next successful poll
- No cross-process sharing → with one api container we don't care;
  if we ever scale horizontally, every container would derive
  independently (acceptable since output is deterministic given
  the same tape input)
- No threshold-tuning history → can't run "what would label
  distribution have looked like with threshold X" analyses without
  re-running the derivation against a stored tape archive (also
  unstored in v1)

These limits are the **point** of v1 — they force the operator to
decide whether the feature is worth durable infrastructure before we
build it.

---

## 7. Rollout plan

Five phases. Each gated on the previous phase passing operator review.

### Phase A — derivation layer (2 h, ephemeral)
1. New `_overlay_cache: dict[str, _OverlayEntry]` in `api/market.py`
2. Expand `MACRO_TAPE_SYMBOLS` to a resolver `resolve_active_overlay_symbols()` that returns macro + paper-holdings symbols
3. New `derive_intraday_context()` pure function (testable in isolation)
4. Wire the derivation into `_poll_once` after the tape UPSERT (single new call site, single dict reassign)
5. UNIT tests for the derivation function (no IT test needed — no DB write)
6. Feature flag `INTRADAY_OVERLAY_ENABLED=false` ships first
7. **NO migration. NO retention cron. NO schema change.**

### Phase B — read API (1 h)
8. `GET /api/recommendations/{id}/intraday-context` (reads `_overlay_cache`)
9. `GET /api/recommendations/intraday-context?symbols=...` (reads `_overlay_cache`)
10. curl verification against live in-memory cache

### Phase C — UX (3 h)
11. `RecommendationCard` extended with `<IntradayContextLine />` sub-component
12. Renders only when feature flag on AND entry exists AND `context_label != "quiet"`
13. Light + dark mode parity
14. Mobile-safe (sub-line wraps under 360px viewport)
15. Hover tooltip shows the `15m delayed · polygon` source qualifier

### Phase D — operator review + flag flip (15 min)
16. Operator runs through `/portfolio` with flag on
17. Verifies tone, threshold sanity, no terminal feel
18. Flag flip to `INTRADAY_OVERLAY_ENABLED=true` in compose

### Phase E — Phase 2 promotion gate (review only, no code)
After Phase D + a few weeks of operator use, decide whether to
promote to durable storage (see §"Upgrade path" below). Gate
question: *did the ephemeral overlay deliver enough operator value
that the persistence overhead is justified?*

If YES → schedule Phase 2 (migration + diff annotations).
If NO → keep v1 forever, or remove it cleanly (single-flag rollback).

**Total v1 dev: ~6 h spread across 2 sessions.** No scheduler change.
No execution change. No model change. **No migration.** Feature flag
means rollback is one env-var flip and a poller no-op.

---

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Noise**: 15-min prices oscillate; threshold tuning could spam "stress" labels | Threshold uses 60-day daily σ, not absolute %. Quiet bucket is default. Per-page diff cap of 3 (Phase E) |
| 2 | **Macro drag**: `vs_macro_drift_pct` could mask genuine alpha | Surface as observation, never write to conviction. Operator can disable the macro-drift line independently |
| 3 | **Polling cost creep**: symbol allow-list grows silently | Hard 100-symbol cap with truncation warning. Logged every cycle. Alert when cap is hit |
| 4 | **Stale during volatile RTH**: 90s cadence may feel laggy | Can tighten to 60s with zero cost (Starter unlimited). Held until measured |
| 5 | **UI cognitive load**: overlay turns calm pages into Bloomberg-lite | `quiet` bucket renders nothing. Sub-line is single-line italic `var(--fg-3)`. Per-page diff cap. Feature flag for emergency disable |
| 6 | **Architecture creep**: pressure to "just make intraday trades" once data is visible | Section 5 governance locks. Any intraday trade proposal restarts the audit + review loop |
| 7 | **Polygon outage**: tape cache `stale: true` for hours | Overlay endpoint returns empty; UI renders no sub-lines. Identical to today's no-overlay state |
| 8 | **Symbol absence in Polygon Stocks Starter** (less liquid names, ADRs, OTC) | Derivation gracefully skips symbols Polygon doesn't return. Per-row source column shows when a symbol is missing |
| 9 | **Threshold drift over time** as σ regime changes | Re-derivation reads σ from the live 60-day window; auto-adjusts. Operator can review label distributions in a future Ops panel |
| 10 | **Backtest invalidation** if intraday somehow leaks into model | Section 2 lock: zero new columns on `recommendation` table. Walk-forward backtest path doesn't read `recommendation_intraday_context` |

---

## 9. Minimal first implementation — ephemeral

The smallest defensible cut that lands honest, observable value
without breaking anything **and without committing to durable
infrastructure**:

1. **`_overlay_cache: dict[str, _OverlayEntry]`** added to `api/market.py` (parallel to existing `_cache`)
2. **Symbol resolver** — `resolve_active_overlay_symbols()` returning macro + open-paper-positions (skip active-rec for v1)
3. **Derivation function** — `derive_intraday_context(recommendation, snapshot, sigma)` returning the entry dict; uses 4 of the 7 features for v1 (`intraday_change_pct`, `vs_recommendation_entry_pct`, `vs_macro_drift_pct`, `context_label`); omit `vs_open_pct`, `intraday_range_pct`, `material_move_today`
4. **Poller hook** — single new call + dict reassign in `_poll_once` after the existing tape cache write
5. **Endpoint** — `GET /api/recommendations/{id}/intraday-context` only (skip bulk for v1)
6. **UI** — `IntradayContextLine` on recommendation cards in `/portfolio` ONLY (not `/overview` yet); renders 3 of the 5 labels (`stress`, `drift`, `aligned`; `windfall` and `quiet`-as-render deferred)
7. **Feature flag** — `INTRADAY_OVERLAY_ENABLED=false` shipped; flip after Phase D review
8. **NO migration, NO new table, NO retention cron**
9. **NO** confidence/urgency overlays in v1
10. **NO** "Today changed because…" diffs in v1 (requires history → Phase 2)
11. **NO** sizing impact, no execution impact, no scheduler change

**Total v1 dev: ~6 h.** Ships an honest, observable, governance-safe
first surface that the operator can iterate on **with zero durable
state risk**. Everything else (windfall, the two omitted features,
conviction overlay, diff annotations, overview integration,
persistence) is gated on operator review of the v1 output.

---

## Upgrade path to durable storage (Phase 2+)

This section documents the migration path from the v1 ephemeral
cache to a durable table, **only if Phase D operator review
concludes the overlay is worth the persistence overhead.**

### Triggers that justify Phase 2

Promote to durable storage if and only if at least ONE of these is
true after a few weeks of v1 use:

1. **Operator wants "Today changed because…" diff annotations.**
   Diffs require comparing the current `context_label` against the
   prior session's — impossible without history.
2. **Operator wants threshold-tuning analysis.** Questions like
   "what would the label distribution look like with σ × 1.5 as
   the stress threshold?" require a stored archive of derivations
   to back-test against.
3. **Operator wants intraday context to influence sizing or
   execution.** This requires a durable audit trail per the
   existing `paper_trade` provenance model. (Restarts the §4
   governance review — not auto-approved by promoting storage.)
4. **Multi-container scaling.** If the api ever scales horizontally,
   each container would derive independently from the same tape
   input. Output is deterministic so this is acceptable, BUT a
   shared store removes the per-container memory cost and lets a
   reader hit any container.

### Phase 2 minimum: persist + diff

The lightest Phase 2 that unlocks the diff annotation feature:

| Step | Action | Notes |
|---|---|---|
| 1 | Migration `06X_recommendation_intraday_context.sql` | Schema in §6 of the v1 doc (now in this doc's git history); add `derived_at` column |
| 2 | Poller writes a NEW row per cycle (no UPDATE) | INSERT-only; 7-day retention via daily cron |
| 3 | Endpoint adds `?since=<iso>` filter | Returns rows newer than `since` for the diff annotation |
| 4 | Frontend `overview_memory.ts` extended to track last-seen `context_label` per rec | 3-per-page diff cap |
| 5 | Daily prune cron `prune_recommendation_intraday_context` | Scheduled at 22:00 ET piggybacking the existing ingest job (no new cron) |

**Phase 2 dev: ~5 h.** Diff annotations + threshold-tuning history
in one pass.

### What does NOT migrate from v1

- The in-memory `_overlay_cache` is removed; the read endpoint
  switches to reading the table. Allowed brief inconsistency
  during the rollover (~1 cycle of empty results immediately
  after the switch).
- The `derive_intraday_context()` pure function is **untouched** —
  same signature, same output. v1 → Phase 2 changes only the
  storage layer, not the derivation.
- The feature flag stays — Phase 2 still ships under
  `INTRADAY_OVERLAY_ENABLED`.

### Anti-promotion clauses (when to NOT migrate)

Stay on v1 ephemeral if:
- Operator finds the overlay noisy / low-signal during review
- Threshold tuning never settles (σ-based formula needs further work)
- Diff annotations are not desired (some operators may prefer the
  always-current observational tone over change-tracking)
- The team's other priorities push intraday work down the list —
  v1 can run indefinitely with zero maintenance overhead

In any of these cases, the cleanest path is to flip
`INTRADAY_OVERLAY_ENABLED=false` and let the v1 code path go dormant
(or remove it in a follow-up cleanup commit). No data to drop, no
table to deprecate, no migration to write.

---

## Validation gates before approval

1. Operator reviews this doc and approves the per-section locks
   (Section 4 governance + Section 5 execution especially).
2. Operator confirms the **v1 ephemeral scope** in §9 — none of the
   items in the "NO" list should sneak in. Particularly:
   - No migration
   - No new table
   - No retention cron
   - No diff annotations (require history → Phase 2)
3. Operator approves the threshold draft in §1 (σ-based thresholds
   are sensitive; deserve direct review).
4. Operator approves the new env var name `INTRADAY_OVERLAY_ENABLED`.
5. Operator acknowledges the v1 trade-offs documented at the end of
   §6 ("What the v1 ephemeral cache CANNOT do") — these are the
   deliberate cost of ephemerality.

---

## Sources

- Pipeline audit findings, this document §"Pipeline anchors" (2026-05-12)
- `docs/research/MARKET_QUOTE_PROVIDER_EVAL.md` — Polygon Stocks Starter integration spec
- `apps/api/src/domain/recommendations/recommendation_engine.py` — recommendation generator
- `apps/api/src/domain/paper_trading/paper_execution.py` — next-bar fill rule
- `scripts/seed_symbols.py` — cron schedule defs
- `apps/api/src/db/models.py` — Recommendation, RecommendationOutcome, Alert schemas

---

*Document originated 2026-05-12 ~09:00 ET as Phase 16 intraday
context overlay architecture proposal. NOT yet implemented. Requires
operator approval + per-phase validation gates before any code lands.*
