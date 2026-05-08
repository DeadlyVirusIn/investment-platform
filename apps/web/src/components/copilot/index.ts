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
