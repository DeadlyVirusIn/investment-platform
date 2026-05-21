# Substrate Expansion Reassessment — Day 10

**Decision**: Continue **DEFER** on all substrate expansion.
**Date**: 2026-05-18
**Sample basis**: 2004-rec full-universe walk (D10.1); D9.2 baseline; live cron readiness confirmed (D10.0).

## Bottom line

The reasoning system is currently doing exactly what it should. Adding
substrate would not produce a proportional truthfulness gain at this
stage.

## Indicators that justify deferral

1. **Deterministic stability at 20× scale**: 2004 recs walked twice,
   zero hash drift.
2. **Compressed truth-density preserved**: only 5 distinct
   envelope_hashes from 2004 input contexts. The system collapses
   identical canonical content into the same hash; that compression
   is correct.
3. **Honest-absence frequency increases at scale (6% → 14%
   no_skeleton_match)**: the system refuses more, not less, as the
   universe widens. That is the right direction.
4. **Truthful skeleton emergence**: `momentum_breakout` appeared in
   the distribution only when the sell-side (Trim) universe joined.
   No new skeleton was hand-coded; existing rules fired correctly.
5. **Marker density bounded**: avg 0.57/envelope, max 2 (cap 3). No
   pile-on under volume.

## Substrate gaps the system is currently REFUSING to fabricate

| Substrate | State | Refusal posture |
|-----------|-------|---------------------|
| Breadth (advance/decline) | NULL across all rows | Day 5 / Day 9 defer |
| earnings_event table | empty (0 rows) | Day 6 / Day 7 — no provider keys |
| earnings_proximity_days column | NULL across 1008 rows | Day 9 / Day 10 — engine explicitly leaves NULL until earnings feed ships |
| Yahoo earnings backfill | needs lxml, not installed | Day 7 |
| Finnhub/FMP/AlphaVantage backfill | keys empty | Day 7 |

All five refusals are **operationally consistent** — same posture
applied independently across 6 days of investigation. Pattern is now
operational culture, not one-time enforcement (per Day 10 directive).

## What would actually move the needle

In priority order:

1. **A real earnings ingestion feed** — would unlock
   `catalyst_proximate_earnings` honestly through TWO independent
   paths (earnings_event AND earnings_proximity_days). Effort:
   external (need provider key OR lxml install). Reward: directly
   activates a dormant skeleton path.

2. **Observe 2026-05-19 live cron firing** — the first
   telemetry-enabled live envelope generation. We need this data
   point before any architectural decisions about live-vs-replay
   parity. Effort: wait ~26h. Reward: confirms behavior under
   real cron cadence.

3. **Sell-side skeleton review** — D10.1 surfaced 861
   `momentum_breakout` envelopes on sell side, nearly all firing
   `counter_trend` (Trim into macro_tailwind). Is that the truthful
   semantic? Operator review of 5-10 randomly sampled envelopes
   would validate calibration. Effort: 30min review. Reward:
   ground-truth check before scaling further.

## What would NOT move the needle

| Investment | Why deferred |
|------------|---------------|
| Breadth ETL implementation | Would add skeleton/marker firing but no new truthful semantic shape today |
| New skeletons | Existing 6 cover observable engine behavior; one (BREADTH_THRUST_ENTRY) dormant, one only-options reachable, no genuine gap |
| New vocabulary entries | Marker firing already truthful and bounded |
| Prose sophistication | Renderer outputs are stable; users haven't even seen Decision Detail yet |
| UI work | No Decision Detail UI surface exists; building one is downstream of substrate maturity |
| Threshold tuning | Calibration validated at 20× scale (D10.3) — no signal needs adjustment |

## Recommended Day 11 priorities (only if requested)

1. Wait for 2026-05-19 03:30 UTC live cron and observe telemetry
2. Sample 5-10 sell-side `momentum_breakout` envelopes for operator
   semantic review
3. If earnings provider key becomes available: activate earnings ETL
4. Otherwise: hold position. The reasoning system is currently
   winning by not adding more.

## Most important framing

> The reasoning system became more expressive because the engine
> genuinely saw more — not because narration became "smarter."
> (User directive, Day 9 acceptance)

That principle is now structurally proven at 20× scale. The right move
is to leave the architecture alone and let upstream evidence quality
catch up.
