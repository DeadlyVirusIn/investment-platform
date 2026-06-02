// Today — Options lane. ALWAYS rendered (per product decision): users must
// always know options exists, even when stale/disabled/no setups.
//
// Phase A: the lane now leads with the best options setup (TodayOptionsHero),
// mirroring the stock hero, instead of pipeline telemetry (universe /
// engine-compatible / incompatible counts). Read-only. No trade controls.

import { TodayOptionsHero } from './TodayOptionsHero';

export function TodayOptionsLane() {
  return <TodayOptionsHero />;
}
