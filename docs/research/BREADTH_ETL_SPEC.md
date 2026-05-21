# Breadth ETL Specification

**Status**: Design specification — not implemented.
**Goal**: Provide a truthful breadth substrate so `breadth_broadening`
and `breadth_narrowing` canonical signals can fire in production.
**Non-goal**: Synthetic / heuristic breadth approximations. If real
data cannot be sourced, the signals remain dormant. See
`apps/api/src/reasoning/signal_extractor.py` — the dormancy is by
design.

---

## 1. Truthful definition

Breadth = **% of a defined benchmark universe trading above its own
50-day simple moving average**, computed daily from real price bars.

- Numerator: count of assets in universe where `close > SMA50(close)` on day `D`.
- Denominator: count of assets in universe that have ≥50 prior bars and a valid close on day `D`.
- Output: `pct_above_ma50: float ∈ [0, 1]`.

The "breadth regime" classification (already a column on
`regime_snapshot.breadth_regime`) is derived from `pct_above_ma50` using
fixed thresholds defined in `apps/api/src/domain/behavioral/breadth.py`:

- `pct >= 0.65` → `breadth_regime = 'bullish'`
- `pct <= 0.35` → `breadth_regime = 'bearish'`
- otherwise → `breadth_regime = 'neutral'`

The signal extractor must then map:
- `bullish` → `breadth_broadening`
- `bearish` → `breadth_narrowing`
- `neutral` → no breadth signal

This mapping is a one-line addition to the extractor and does NOT
require new vocabulary entries.

---

## 2. Universe definition

The benchmark universe is **the load-bearing decision** of this spec.
Wrong universe → noisy or misleading breadth.

### Candidate universes (in order of preference)

1. **SPY / S&P 500 constituents (recommended)** — broad-market signal,
   well understood, well-correlated to the regime concepts already in
   `regime_snapshot.market_trend`. Cost: requires a constituents
   feed.

2. **"AI's tradeable universe"** — all assets with at least one
   accepted CandidateIdea row in the last 90 days. Pros: matches what
   the engine actually trades. Cons: changes over time, breadth
   becomes self-referential.

3. **Top-1000 by avg dollar volume over trailing 60 days** — neutral
   to engine choices, larger sample, no constituent feed needed.
   Cons: composition drifts; harder to backfill historically.

**Recommendation**: option 3 for MVP. It's the only option that needs
zero new data feeds and produces a stable, replicable universe purely
from `price_bar`. Option 1 is the long-term goal once a constituents
feed is available.

---

## 3. Schema

### New table: `breadth_daily`

```sql
CREATE TABLE breadth_daily (
    as_of_date          DATE NOT NULL PRIMARY KEY,
    universe_definition TEXT NOT NULL,         -- e.g. 'top1000_dv60'
    universe_size       INTEGER NOT NULL,
    n_above_ma50        INTEGER NOT NULL,
    pct_above_ma50      NUMERIC(8,6) NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Existing column to populate

`regime_snapshot.breadth_regime VARCHAR(16)` — currently NULL across
all rows. Backfill from `breadth_daily.pct_above_ma50` using the
thresholds above.

---

## 4. Compute job

### Daily job: `compute_breadth_daily`

```text
schedule: 22:05 ET, Mon-Fri (immediately after ingest_prices_daily 22:00)
inputs : price_bar  (last 50 bars per asset)
outputs: breadth_daily (one row per as_of_date)
         regime_snapshot.breadth_regime  (backfilled for that date)
```

### Pseudocode

```python
def compute_breadth_daily(as_of: date) -> None:
    universe = _resolve_universe(as_of)
    above = 0
    total = 0
    for asset_id in universe:
        bars = fetch_last_n_bars(asset_id, as_of, n=51)
        if len(bars) < 51:
            continue
        close_today = bars[-1].close
        sma50 = mean(b.close for b in bars[-51:-1])
        if close_today > sma50:
            above += 1
        total += 1
    pct = above / total if total else 0
    insert breadth_daily(as_of_date, universe_definition, universe_size,
                        n_above_ma50, pct_above_ma50)
    update regime_snapshot
        set breadth_regime = bullish/bearish/neutral
        where as_of_date = as_of
```

### Backfill

One-time backfill over historical price_bar range. Idempotent: ON
CONFLICT (as_of_date) DO NOTHING. Estimated runtime: O(universe_size
× n_dates × O(1) bar window query) — for 1000 assets × 500 days, ~10
minutes single-threaded.

---

## 5. Integration with reasoning pipeline

Zero changes required to:
- skeleton catalog
- envelope contract
- renderer
- audit / observability

Single change to **signal extractor** (`apps/api/src/reasoning/signal_extractor.py`):

```python
# inside extract_signals, after macro_* signal logic:
breadth = regime.get("breadth_regime") if isinstance(regime, dict) else None
if breadth == "bullish":
    active.add("breadth_broadening")
elif breadth == "bearish":
    active.add("breadth_narrowing")
```

That's it. The reserved `BREADTH_THRUST_ENTRY` skeleton rule activates
automatically (already in `skeleton_selector.RULES`).

---

## 6. Acceptance criteria

A backfill is considered correct when:

1. `breadth_daily` has a row for every trading day in the backfill range
2. `pct_above_ma50` is monotonically valid (∈ [0, 1])
3. `regime_snapshot.breadth_regime` is populated (non-NULL) for every
   day with a corresponding `breadth_daily` row
4. Spot-check: market-crash dates (if any in range) show
   `pct_above_ma50 < 0.35`; rally dates show `> 0.65`
5. Re-running the daily job is idempotent (no row inflation)
6. After backfill, the existing replay over 2026-04 to 2026-05 trade
   range produces envelopes that now include `breadth_*` signals where
   appropriate. The new snapshot fixture for `BREADTH_THRUST_ENTRY`
   gets pinned in `test_reasoning_envelope_snapshots.py`.

---

## 7. Truthfulness guard

If the universe resolution fails (no bars / insufficient history /
ETL error), the daily job must:
- log a warning
- NOT insert a row in `breadth_daily`
- NOT update `regime_snapshot.breadth_regime`

Honest absence preserves over fabricated coverage. The reasoning
pipeline already respects NULL breadth as "no signal" — no further
guard needed.

---

## 8. Estimated effort

- Schema migration: 0.5 hour
- Compute job + idempotence: 3-4 hours
- Backfill script + dry-run: 2 hours
- Extractor patch + snapshot fixture: 1 hour
- Operational validation (1 day of live run + spot-check): 1 day

**Total**: ~1 day focused work.

---

## 9. Out of scope (explicitly)

- New skeleton or vocabulary entries
- Time-series breadth derivatives (rate-of-change, divergence)
- Sector-level breadth
- Multi-universe breadth signals
- Any prose generation
- Any UI surface

These can be future extensions only after the primary breadth signal
has been observed in production for at least one full quarter.
