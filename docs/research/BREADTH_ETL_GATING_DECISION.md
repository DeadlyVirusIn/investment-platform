# Breadth ETL Gating Decision (Day 9)

**Decision**: **DEFER** breadth ETL implementation.
**Date**: 2026-05-18

## Why DEFER, not GO

The Day 9 evidence-engineering work proved a stronger principle than I
expected:

**The reasoning system already produces truthful diversity from the
real evidence we have today.**

Day 8/9 measured:
- 98 real Buy recs walked through enriched bridge
- 92 envelopes generated (93.9% coverage)
- 4 distinct hashes — driven by REAL signal heterogeneity
- 2 distinct skeletons firing (regime_aligned + mean_reversion) — by truthful selection
- 2 markers firing (counter_trend + crowded_trade) — by truthful calibration
- 6 honest skips — by correct refusal

There is **no coverage gap that breadth would fill in a way that
matters today**. The single skeleton breadth would unlock —
`BREADTH_THRUST_ENTRY` — is structurally a special case of
`REGIME_ALIGNED_CONTINUATION` with additional confirmation. It would
add MORE marker firing, not more skeleton diversity.

## What breadth would actually add

1. A breadth_broadening / breadth_narrowing signal flag in the
   extractor.
2. A new skeleton (BREADTH_THRUST_ENTRY) activation path that
   currently dormant.
3. Marker firing potential — `crowded_trade` could fire under
   different conditions.

But:
- We already have macro_tailwind / macro_headwind capturing regime
  direction
- We already have momentum_3w_positive / momentum_3w_negative capturing
  participation
- Adding breadth signals layered on top creates marker noise risk
  (more signals → more marker triggers → less frugal)

## What's actually limiting reasoning quality today

1. ~~Breadth substrate~~ — would add coverage, but coverage isn't the
   limit
2. **Earnings substrate (still empty)** — would unlock real
   CATALYST_ANTICIPATION on individual names, currently dormant
3. **Operator review of mean_reversion firings** — D9.2 showed 24%
   of Buys are routed to mean_reversion_pullback. Is that the AI's
   genuine read? Or is the residual_momentum threshold too sensitive?
4. **Live cron observation** — 2026-05-19 will be the first
   telemetry-enabled live fire. Need to observe it before adding
   complexity.

## Reconsider when

Breadth ETL becomes the right move when ONE of these is true:

- An operator reviewing the marker output asks "where's breadth?"
- The mean_reversion firing rate stops being explainable by
  residual_momentum alone
- We add a benchmark universe definition for OTHER reasons (e.g., a
  market-context surface) and breadth comes free
- The spec from D7.3 is implemented as part of larger ETL/universe
  work, not standalone

## Honest constraint

The breadth substrate gap is **not what's holding back reasoning
quality today**. Wiring it would be additive complexity without
proportional truthfulness gain. Refusing to ship code for its own sake
is the right move.

The Day 9 mandate said:
> "breadth ETL only if evidence quality remains high"

Evidence quality is high. We don't need it.

## Carry forward

Spec from `docs/research/BREADTH_ETL_SPEC.md` remains valid. Estimated
~1 day effort. Untouched until reactivated.
