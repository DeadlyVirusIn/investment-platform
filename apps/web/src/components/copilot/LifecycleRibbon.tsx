// UX-3D Phase A — Lifecycle Ribbon.
//
// One of the 5 signature elements (UX-3C §3a). 4 nodes, fixed shape:
//   Idea  →  Bought  →  Held  →  Closed
//
// Filled circle = happened. Open circle = not yet. NEVER more than
// 4 circles. NEVER tooltips, popovers, or charts inside. The ribbon
// is a closed component (UX-3D §11 risk register: "ribbon is 4
// circles + 4 dates. Closed component.").

import { LIFECYCLE_NODES } from "@/lib/copilot/copy";


export interface LifecycleRibbonNode {
  /** Whether this milestone has occurred. */
  filled: boolean;
  /** Display label below the dot — short, e.g. "Idea", "Bought",
   *  "Day 4 of 10", "Closed". Caller composes the suffix; this
   *  component only renders the line + dots. */
  label: string;
  /** Optional date string shown beneath the label, e.g. "May 2". */
  date?: string;
}


export interface LifecycleRibbonProps {
  /** Exactly 4 nodes. Order: idea → bought → held → closed. */
  nodes: [
    LifecycleRibbonNode, LifecycleRibbonNode,
    LifecycleRibbonNode, LifecycleRibbonNode,
  ];
  className?: string;
}


export default function LifecycleRibbon(
  { nodes, className }: LifecycleRibbonProps,
) {
  return (
    <div
      data-test="copilot-lifecycle-ribbon"
      className={className}
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 0,
        position: "relative",
        padding: "8px 0",
      }}
    >
      {/* Connecting line behind the dots. Single grey line; no */}
      {/* multi-color, no gradient, no pulse.                    */}
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          top: "calc(8px + 6px)",  // padding + half dot
          left: "12.5%",
          right: "12.5%",
          height: 1,
          background: "var(--copilot-dot-calm)",
          opacity: 0.35,
        }}
      />
      {nodes.map((n, i) => (
        <div
          key={i}
          data-test={`copilot-lifecycle-node-${i}`}
          data-filled={n.filled ? "true" : "false"}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            position: "relative",
            zIndex: 1,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              display: "inline-block",
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: n.filled
                ? "var(--copilot-dot-calm)"
                : "var(--copilot-page-bg)",
              border: `1.5px solid var(--copilot-dot-calm)`,
              marginBottom: 6,
            }}
          />
          <div
            style={{
              fontSize: "var(--copilot-type-12)",
              color: "var(--copilot-dot-calm)",
              textAlign: "center",
              lineHeight: 1.4,
            }}
          >
            {n.label}
          </div>
          {n.date && (
            <div
              style={{
                fontSize: "var(--copilot-type-12)",
                color: "var(--copilot-dot-calm)",
                opacity: 0.7,
                textAlign: "center",
              }}
            >
              {n.date}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}


// Re-export node labels so callers can compose lifecycle nodes
// without importing copy.ts directly. Helps lint scope.
export const LIFECYCLE_NODE_LABELS = LIFECYCLE_NODES;
