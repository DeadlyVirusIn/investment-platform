# Phase 2 — Backlog (not yet implemented)

Items deferred per user direction. Tracked here so they're not lost
between phases.

## Pattern freshness narrative

**Status**: backlog (per user direction in 2A approval message — "do
not implement freshness yet").

**Trigger**: when a `PatternObservation` was active (`observation_count
>= 5`) but its 60-day-window count drops below 5 due to behavior
change, surface a voiced narrative on the Me page:

> "I used to think you avoided earnings setups. I haven't seen that
> behavior in the last 30 days — could be you've changed your mind,
> could be I haven't shown you any earnings plays. Either way, I'm
> retiring this note."

**Implementation sketch** (when activated):
1. Patterns store gains `previous_observation_count: number` field
   capturing prior high-water mark.
2. `patternEngine.scanPatterns()` detects when current count <
   previous high-water minus N (e.g., dropped from 12 to 4 → flag
   as stale).
3. New `PatternObservation` field `staleness: 'fresh' | 'fading' |
   'retired_due_to_drift'`.
4. Me page renders a "Patterns I used to see" section showing notes
   with staleness != 'fresh' for the last 90 days, then retires them.
5. Voice templates per staleness tier.

**Why deferred**: requires accumulated data + Mentor Profile (2E)
context. Premature surfacing on fresh accounts.

**Where it sits in the roadmap**: Phase 2E mid-point or Phase 2F.
