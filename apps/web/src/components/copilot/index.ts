// UX-3D Phase A — barrel re-exports for copilot primitives.
//
// Phase A ships the primitives only. NO page mounts these yet. The
// existing app continues to render exactly as it did before this
// commit; the new components are dead code until Phases B-F wire
// them up.

export { default as ToneDot } from "./ToneDot";
export type { ToneDotProps } from "./ToneDot";

export { default as DisclosureRow } from "./DisclosureRow";
export type { DisclosureRowProps } from "./DisclosureRow";

export { default as LifecycleRibbon, LIFECYCLE_NODE_LABELS } from "./LifecycleRibbon";
export type {
  LifecycleRibbonNode, LifecycleRibbonProps,
} from "./LifecycleRibbon";

export { default as QuietDay } from "./QuietDay";
export type { QuietDayProps } from "./QuietDay";

export { default as SituationalHero } from "./SituationalHero";
export type { SituationalHeroProps } from "./SituationalHero";

export { default as PositionStoryCard } from "./PositionStoryCard";
export type { PositionStoryCardProps } from "./PositionStoryCard";

// UX-5B Phase B-2 — Today (Overview) block primitives.
export { default as TodayLine } from "./TodayLine";
export type { TodayLineProps } from "./TodayLine";

export { default as HoldingsSummary } from "./HoldingsSummary";
export type { HoldingsSummaryProps } from "./HoldingsSummary";

export { default as IdeaCard } from "./IdeaCard";
export type { IdeaCardProps } from "./IdeaCard";

export { default as TodaysIdeas } from "./TodaysIdeas";
export type { TodaysIdeasProps } from "./TodaysIdeas";

export { default as WhatChangedBlock } from "./WhatChangedBlock";
export type { WhatChangedBlockProps } from "./WhatChangedBlock";

export { default as RiskLine } from "./RiskLine";
export type { RiskLineProps } from "./RiskLine";

export { default as WatchThisWeek } from "./WatchThisWeek";
export type { WatchThisWeekProps } from "./WatchThisWeek";

// UX-8B Phase 8B-1 — Portfolio Weather Room hero.
export { default as ConditionBlock } from "./ConditionBlock";
export type { ConditionBlockProps } from "./ConditionBlock";
