// FilterBar — tabs above grid for filtering picks client-side.

import type { PicksFilter } from "@/lib/picks/copilot";
import { FILTER_LABELS } from "@/lib/picks/copilot";
import type { Pick, PickAction } from "@/lib/picks/api";


export interface FilterBarProps {
  picks: Pick[];
  active: PicksFilter;
  onChange: (filter: PicksFilter) => void;
}


export default function FilterBar({ picks, active, onChange }: FilterBarProps) {
  // Counts per action filter
  const counts: Record<PickAction, number> = { buy: 0, sell: 0, trim: 0, hold: 0 };
  let highConfCount = 0;
  for (const p of picks) {
    const a = p.adjusted_action ?? p.action;
    counts[a] = (counts[a] ?? 0) + 1;
    const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
    const pct = c > 1 ? c : c * 100;
    if (pct >= 70) highConfCount += 1;
  }

  const filters: Array<{ key: PicksFilter; count?: number }> = [
    { key: "all", count: picks.length },
    { key: "buy", count: counts.buy },
    { key: "hold", count: counts.hold },
    { key: "trim", count: counts.trim },
    { key: "sell", count: counts.sell },
    { key: "high-confidence", count: highConfCount },
    { key: "freshest" },
    { key: "highest-risk" },
  ];

  return (
    <div className="picks-filter-bar" data-test="picks-filter-bar" role="tablist">
      {filters.map(f => (
        <button
          key={f.key}
          type="button"
          role="tab"
          aria-selected={active === f.key}
          className="picks-filter-tab"
          data-active={active === f.key ? "true" : "false"}
          data-action={f.key === "buy" || f.key === "sell" || f.key === "trim" || f.key === "hold" ? f.key : ""}
          onClick={() => onChange(f.key)}
        >
          <span>{FILTER_LABELS[f.key]}</span>
          {f.count !== undefined && (
            <span className="picks-filter-count">{f.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
