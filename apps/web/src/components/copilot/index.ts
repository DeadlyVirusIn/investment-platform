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

// UX-9 Phase 9A/9B — AI Command Center primitives.
export { default as HeroCard } from "./HeroCard";
export type {
  HeroCardProps, PositionWeight, PositionHue, HeroMiniObject,
} from "./HeroCard";

export { default as IntelligenceGrid, SLOT_ORDER } from "./IntelligenceGrid";
export type {
  IntelligenceGridProps, SlotData, SlotName,
} from "./IntelligenceGrid";

export { default as Sparkline } from "./Sparkline";

// UX-10 Phase 10A/10B/10C — Conviction Engine primitives.
export { default as VerbPill } from "./VerbPill";
export type { VerbPillProps } from "./VerbPill";

export { default as TierGlyph } from "./TierGlyph";
export type { TierGlyphProps } from "./TierGlyph";

export { default as FreshnessChip } from "./FreshnessChip";
export type { FreshnessChipProps } from "./FreshnessChip";

export { default as ActionCard } from "./ActionCard";
export type { ActionCardProps } from "./ActionCard";

export { default as OptionsStructureCard } from "./OptionsStructureCard";
export type { OptionsStructureData, OptionsIntent } from "./OptionsStructureCard";

export { default as ConvictionHero } from "./ConvictionHero";
export type { ConvictionHeroProps } from "./ConvictionHero";

// UX-11 Phase 11A/11B/11C — Interactive AI Copilot Layer.
export { default as ConvictionTile } from "./ConvictionTile";
export type { ConvictionTileProps } from "./ConvictionTile";

export { default as AIReadHero } from "./AIReadHero";
export type { AIReadHeroProps } from "./AIReadHero";

export { default as ReasoningDrawer } from "./ReasoningDrawer";
export type { ReasoningDrawerProps } from "./ReasoningDrawer";

// UX-13 living environment visual hypothesis.
export { default as AIRead13 } from "./AIRead13";
export type { AIRead13Props } from "./AIRead13";

export { default as VerbGlyph } from "./VerbGlyph";
export type { VerbGlyphProps } from "./VerbGlyph";

export { default as RoomSolo } from "./RoomSolo";
export type { RoomSoloProps } from "./RoomSolo";

export { default as RoomDuet } from "./RoomDuet";
export type { RoomDuetProps } from "./RoomDuet";

export { default as RoomField } from "./RoomField";
export type { RoomFieldProps } from "./RoomField";

// UX-13 transformation pass — typographic blocks (replace ConvictionTile chrome).
export { default as HeroBlock } from "./HeroBlock";
export type { HeroBlockProps } from "./HeroBlock";

export { default as SubBlock } from "./SubBlock";
export type { SubBlockProps } from "./SubBlock";
