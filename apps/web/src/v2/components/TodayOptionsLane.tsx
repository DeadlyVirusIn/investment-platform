// Today — Options lane. ALWAYS rendered (per product decision): users must
// always know options exists.
//
// Sprint M: the lane now uses the beginner-safe OptionsAdvancedSection
// (collapsed disclosure, beginner language, advanced-practice warning) instead
// of the trader-facing TodayOptionsHero, which leaked jargon (DTE/IV/etc.)
// onto a beginner surface. Read-only. No trade controls.

import { OptionsAdvancedSection } from './OptionsAdvancedSection';

export function TodayOptionsLane() {
  return <OptionsAdvancedSection />;
}
