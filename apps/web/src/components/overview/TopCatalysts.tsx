// Phase reliability/catalyst — minimal top-catalysts widget.
// 5-8 rows max, no news panel, compact policy chip per row.

import { useTopCatalysts } from "@/lib/catalysts/hooks";
import { Label } from "@/components/ui/primitives";
import type { CatalystSummary, TradePolicy } from "@/lib/catalysts/types";
import { cn } from "@/lib/cn";

export default function TopCatalysts() {
  const { data, isLoading, isError } = useTopCatalysts(8);
  const rows = data ?? [];

  return (
    <div
      className="u-card"
      style={{ padding: 0 }}
      title="Catalyst labels are event classifications only. They do not imply actions or portfolio adjustments."
    >
      <div className="flex items-center justify-between px-4 py-3
                        border-b border-b1">
        <div>
          <Label>Top catalysts</Label>
          <div className="u-caption-2 mt-0.5">
            Event classifications · upcoming events + news · free-tier providers
          </div>
        </div>
        {rows.some(r => r.has_earnings_soon) && (
          <span className="u-chip u-chip-warning">
            <span className="u-dot u-dot-warning u-dot-pulse" />
            earnings soon
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="px-4 py-4 u-caption-2 italic">loading…</div>
      ) : isError ? (
        <div className="px-4 py-4 u-caption-2 italic">
          catalyst feed unavailable
        </div>
      ) : rows.length === 0 ? (
        <div className="px-4 py-4 u-caption-2 italic">
          No event-impact entries to display.
        </div>
      ) : (
        <ul className="divide-y divide-b1">
          {rows.map(r => <Row key={r.symbol} c={r} />)}
        </ul>
      )}
    </div>
  );
}

function Row({ c }: { c: CatalystSummary }) {
  const top = c.headlines[0];
  const policyChip = policyChipTone(c.trade_policy);
  const daysText = c.has_earnings_soon && c.days_to_earnings !== null
    ? `earnings in ${c.days_to_earnings}d`
    : c.next_event
      ? `${c.next_event.kind} ${c.next_event.date}`
      : "no upcoming event";
  return (
    <li className="px-4 py-2.5 flex items-start gap-3">
      <div className="w-16 shrink-0">
        <div className="u-mono font-semibold text-fg">{c.symbol}</div>
        <div className="u-caption-2 mt-0.5">
          risk {(c.event_risk_score * 100).toFixed(0)}
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="u-caption text-fg-2 truncate">
          {top ? top.title : "no recent headlines"}
        </div>
        <div className="u-caption-2 mt-1 flex items-center gap-2">
          <span>{daysText}</span>
          {c.partial && <span className="u-chip u-chip-neutral">partial</span>}
        </div>
      </div>
      <span className={cn("u-chip shrink-0", policyChip.cls)}
            title={c.short_reason}>
        {policyChip.label}
      </span>
    </li>
  );
}

// Phase 11K.1 — neutralised label set. Codes communicate event-
// impact classification only; they do not imply actions or
// portfolio adjustments.
function policyChipTone(p: TradePolicy): { cls: string; label: string } {
  switch (p) {
    case "block_new_entry":       return { cls: "u-chip-neutral", label: "EVENT_IMPACT_HIGH" };
    case "require_confirmation":  return { cls: "u-chip-neutral", label: "EVENT_REQUIRES_REVIEW" };
    case "reduce_size":           return { cls: "u-chip-neutral", label: "EVENT_IMPACT_MODERATE" };
    case "watch_only":            return { cls: "u-chip-neutral", label: "EVENT_MONITOR" };
    case "neutral":
    default:                      return { cls: "u-chip-neutral", label: "NO_EVENT_SIGNAL" };
  }
}
