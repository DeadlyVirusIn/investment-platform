// UX-2 Phase B — PositionStoryCard.
//
// Per-open-position storytelling card composed from Phase A
// primitives (DisclosureRow + LifecycleRibbon + ToneDot). Pure
// render — receives an ExecutedPosition + a PositionStory derived
// upstream by lib/copilot/derive.ts.
//
// Truthful fallbacks:
//   * Exit levels not yet computed for this position. See Decisions
//     for the raw inputs.
//   * Recovered-from-backup chip when source === "replay".
// NEVER invents targets, reasoning, confidence, or pricing.

import DisclosureRow from "./DisclosureRow";
import LifecycleRibbon, {
  LIFECYCLE_NODE_LABELS,
  type LifecycleRibbonNode,
} from "./LifecycleRibbon";
import { HOLDINGS_COPY } from "@/lib/copilot/copy";
import type { PositionStory } from "@/lib/copilot/derive";


export interface PositionStoryCardProps {
  story: PositionStory;
  /** Defaults to false; the parent (CopilotHoldings) opens the very
   *  first card on a fresh browser via the ux_seen_first_position
   *  onboarding flag. */
  defaultOpen?: boolean;
  className?: string;
}


export default function PositionStoryCard(
  { story, defaultOpen = false, className }: PositionStoryCardProps,
) {
  // Lifecycle ribbon nodes — Phase B has Idea date unknown for now,
  // Bought = opened_at, Held = "open", Closed = open circle.
  const nodes: [
    LifecycleRibbonNode, LifecycleRibbonNode,
    LifecycleRibbonNode, LifecycleRibbonNode,
  ] = [
    { filled: false, label: LIFECYCLE_NODE_LABELS.idea },
    {
      filled: true,
      label: LIFECYCLE_NODE_LABELS.bought,
      date: story.boughtOnLabel,
    },
    { filled: true, label: "Open" },
    { filled: false, label: LIFECYCLE_NODE_LABELS.exit },
  ];

  return (
    <article
      data-test="copilot-position-story-card"
      data-symbol={story.symbol}
      className={className}
      style={{
        paddingBlock: "var(--copilot-card-padding)",
        borderTop: "1px solid var(--copilot-ambient-tint)",
      }}
    >
      <DisclosureRow
        defaultOpen={defaultOpen}
        ariaLabel={`${story.symbol} position details`}
        glance={
          <span
            data-source={story.dataSource}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 12,
              fontSize: "var(--copilot-type-15)",
              fontWeight: 500,
            }}
          >
            <span
              data-test="copilot-position-symbol"
              style={{ minWidth: 56 }}
            >
              {story.symbol}
            </span>
            <span style={{ opacity: 0.85 }}>{story.glance}</span>
            {story.isRecovered && (
              <span
                title={HOLDINGS_COPY.recoveredTooltip}
                data-test="copilot-position-recovered"
                style={{
                  fontSize: "var(--copilot-type-12)",
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: "var(--copilot-dot-waiting)",
                  border: "1px solid var(--copilot-dot-waiting)",
                  borderRadius: 4,
                  padding: "1px 6px",
                  marginLeft: 4,
                }}
              >
                {HOLDINGS_COPY.recoveredChip}
              </span>
            )}
          </span>
        }
        detail={
          <div data-test="copilot-position-detail" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <p
              data-source={story.dataSource}
              style={{
                margin: 0,
                fontSize: "var(--copilot-type-15)",
                lineHeight: "var(--copilot-prose-line-height)",
                maxWidth: "var(--copilot-prose-max-width)",
              }}
            >
              {story.detail}
            </p>
            {/* Truthful fallback: exit levels are deterministic per */}
            {/* strategy template, but Phase B does not surface the   */}
            {/* per-position strategy reference. Render as            */}
            {/* not-yet-computed with link to Decisions for the raw   */}
            {/* inputs. NEVER invents targets.                        */}
            <p
              data-test="copilot-position-exits-not-computed"
              style={{
                margin: 0,
                fontSize: "var(--copilot-type-13)",
                opacity: 0.7,
                lineHeight: "var(--copilot-prose-line-height)",
                maxWidth: "var(--copilot-prose-max-width)",
              }}
            >
              {HOLDINGS_COPY.detailExitsNotComputed}
            </p>
            <LifecycleRibbon nodes={nodes} />
            <div
              style={{
                display: "flex",
                gap: 16,
                fontSize: "var(--copilot-type-13)",
                opacity: 0.7,
              }}
            >
              <a
                href="/decisions"
                style={{ color: "inherit", textDecoration: "underline" }}
                data-test="copilot-position-link-decisions"
              >
                {HOLDINGS_COPY.detailLinkDecisions} →
              </a>
              <a
                href="/alpha-lab"
                style={{ color: "inherit", textDecoration: "underline" }}
                data-test="copilot-position-link-alpha-lab"
              >
                {HOLDINGS_COPY.detailLinkAlphaLab} →
              </a>
              <a
                href="/portfolio?view=working"
                style={{ color: "inherit", textDecoration: "underline" }}
                data-test="copilot-position-link-working"
              >
                {HOLDINGS_COPY.detailLinkWorking} →
              </a>
            </div>
          </div>
        }
      />
    </article>
  );
}
