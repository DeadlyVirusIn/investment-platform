> **ARCHIVED 2026-07-09** — describes the pre-auth single-user Phase-0 design
> (2026-04); superseded by the rule-based agreement-scoring engine (LightGBM shadow-only) — see docs/research/MODEL_AND_DATA_FORENSICS.md.
> Kept for history; do not use for implementation.

# Recommendation Engine

## Actions (5-value enum)

| Action | Meaning |
|--------|---------|
| `STRONG_BUY` | High-conviction entry; all signal families align positively |
| `BUY` | Favourable risk/reward; majority of signals positive |
| `HOLD` | No clear edge; maintain current position if held |
| `REDUCE` | Adverse signals accumulating; trim but don't exit fully |
| `SELL` | Exit signal; majority of families negative or stop triggered |

---

## `enough_data` Gate

Before scoring, each symbol must pass the `enough_data` thresholds defined in
`engine.yaml`. A symbol that fails the gate receives action `HOLD` with
`enough_data: false` and a `tags: ["insufficient_history"]` annotation.

Typical thresholds (overridden per symbol type in `engine.yaml`):

| Signal Family | Min history required |
|---------------|---------------------|
| `trend_momentum` | 90 days |
| `valuation` | 1 full year + fundamentals |
| `volatility_risk` | 60 days |
| `macro_regime` | Always available (FRED) |
| `exposure` | 1 position snapshot |

---

## Signal Families & Weights

Weights are loaded from `packages/engine-config/engine.yaml` at worker startup.
Changing `engine.yaml` takes effect on the next recommendation run without a
code deploy.

| Family | Example signals |
|--------|----------------|
| `valuation` | P/E vs sector median, P/B, EV/EBITDA |
| `trend_momentum` | EMA crossover (20/50/200), RSI, MACD signal |
| `volatility_risk` | ATR/price, beta vs benchmark, max-drawdown |
| `macro_regime` | Yield curve slope, fed funds rate direction |
| `exposure` | Portfolio weight vs target, concentration risk |

---

## Scoring Process

```
for each symbol in watchlist ∪ portfolio:
    if not enough_data(symbol): emit HOLD(enough_data=False)
    signals = compute_signals(symbol, price_bars, fundamentals, macro)
    family_scores = {f: weighted_avg(signals[f], weights[f]) for f in families}
    composite = sum(family_scores[f] * weights.family_weights[f] for f in families)
    action = classify(composite, thresholds)
    tags = derive_tags(signals)
    emit Recommendation(symbol, action, composite, tags, engine_version)
```

All inputs (price bars, fundamentals, macro data) are snapshotted at the time
of the run — reproducibility is guaranteed by replaying the same snapshot.

---

## Reproducibility

Every `recommendation` row stores:

- `engine_version` — SHA of `engine.yaml` at run time
- `run_at` — timestamp
- `signal_snapshot_id` — FK to the signal snapshot row

Given the same snapshot + the same `engine.yaml` version, re-running the
engine produces identical output.

---

## `engine.yaml` Reference

See `packages/engine-config/engine.yaml`. The file is loaded by the worker
at startup. Hot-reload is not supported in Phase 0 — restart the worker
container after changes.

---

## Deferred: Options Signals

Options-specific signals (IV rank, put/call ratio, delta-hedging cost) are
listed in `engine.yaml` under `options_signals` with `enabled: false`.
Activate in a later phase when an options data source is wired up.
