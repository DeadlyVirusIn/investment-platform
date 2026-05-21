// Options Positions page — Phase C.
//
// Reads /api/options/positions/intelligence. Renders one
// OptionsPositionCard per open paper trade with the canonical
// AI trade-management payload. Empty state is calm and explicit
// when no positions exist.
//
// Grouping rule: cards are bucketed by guidance.action so the
// operator sees urgent actions first.
//   1. stop_loss + take_profit (decisive)
//   2. expiring + catalyst_caution (time-sensitive)
//   3. roll (proactive)
//   4. hold (passive)

import { useEffect, useState } from "react";

import OptionsPositionCard, {
  PositionIntelligencePayload,
} from "@/components/options/copilot/OptionsPositionCard";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";


interface PositionsResponse {
  count: number;
  message: string | null;
  guidance_legend: Record<string, string>;
  items: PositionIntelligencePayload[];
}


const GROUP_ORDER: Array<{
  key: string;
  label: string;
  description: string;
  actions: string[];
}> = [
  {
    key: "decisive",
    label: "Decisive action",
    description: "Stop-loss and take-profit signals. Close-now grade.",
    actions: ["stop_loss", "take_profit"],
  },
  {
    key: "time_sensitive",
    label: "Time-sensitive",
    description: "Expiry approaching or catalyst inside the DTE window.",
    actions: ["expiring", "catalyst_caution"],
  },
  {
    key: "proactive",
    label: "Proactive",
    description: "Rolling opportunities while still in profit.",
    actions: ["roll"],
  },
  {
    key: "holding",
    label: "Holding",
    description: "No action signal — theta + breakeven carry the thesis.",
    actions: ["hold", "review"],
  },
];


export default function OptionsPositionsPage() {
  const [resp, setResp] = useState<PositionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  // H-refine: hide empty group buckets by default. Toggle exposes them.
  const [showEmpty, setShowEmpty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/options/positions/intelligence")
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled) { setResp(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="opt-positions-page" data-test="options-positions-page">
      <OptionsOrientationCard surface="holdings" />

      <section className="opt-positions-banner">
        <div className="opt-positions-banner-row">
          <span className="opt-narrative-eyebrow">
            Holdings · AI trade management
          </span>
          <OptionsLiveStateChip />
        </div>
        <h1 className="opt-narrative-sentence">
          {resp && resp.count > 0
            ? `We're managing ${resp.count} open position${resp.count === 1 ? "" : "s"} right now.`
            : "No open paper positions today. We'll meet you here when one opens."}
        </h1>
        {resp && resp.count > 0 && (
          <p className="opt-narrative-supporting">
            Each card shows our read of thesis health, theta carry,
            IV environment, breakeven distance, and the single next
            action we'd recommend. We explain; we don't execute.
          </p>
        )}
      </section>

      {loading && (
        <div className="opt-caption-muted opt-positions-loading">
          Loading position intelligence…
        </div>
      )}

      {!loading && resp && resp.count === 0 && (
        <section className="opt-positions-empty"
                 data-test="opt-positions-empty">
          <h3 className="opt-positions-empty-title">No open positions right now</h3>
          <p className="opt-caption-muted">
            That's a quiet good. When a setup graduates from
            Opportunities into a paper position, we'll surface it
            here with a thesis read and a single next action.
          </p>
        </section>
      )}

      {!loading && resp && resp.count > 0 && (() => {
        const groupsWithItems = GROUP_ORDER.map(g => ({
          ...g,
          items: resp.items.filter(i => g.actions.includes(i.guidance.action)),
        }));
        const nonEmpty = groupsWithItems.filter(g => g.items.length > 0);
        const empty = groupsWithItems.filter(g => g.items.length === 0);
        const visible = showEmpty ? groupsWithItems : nonEmpty;
        return (
          <>
            {visible.map(group => (
              <section
                key={group.key}
                className="opt-positions-group"
                data-test={`opt-positions-group-${group.key}`}
              >
                <header className="opt-positions-group-header">
                  <h3 className="opt-positions-group-title">{group.label}</h3>
                  <span className="opt-positions-group-count">
                    {group.items.length} position{group.items.length === 1 ? "" : "s"}
                  </span>
                </header>
                <p className="opt-caption-muted">{group.description}</p>
                {group.items.length === 0 ? (
                  <div className="opt-positions-group-empty">
                    <span className="opt-caption-muted">
                      Nothing in this bucket right now.
                    </span>
                  </div>
                ) : (
                  <div className="opt-positions-cards">
                    {group.items.map(item => (
                      <OptionsPositionCard
                        key={item.trade_id}
                        item={item}
                        canaryEnabled={false} />
                    ))}
                  </div>
                )}
              </section>
            ))}
            {empty.length > 0 && (
              <button
                type="button"
                className="opt-lane-toggle"
                data-test="opt-positions-group-toggle"
                onClick={() => setShowEmpty(v => !v)}
              >
                {showEmpty
                  ? `Hide ${empty.length} empty bucket${empty.length === 1 ? "" : "s"}`
                  : `${empty.length} bucket${empty.length === 1 ? "" : "s"} empty · show all`}
              </button>
            )}
          </>
        );
      })()}
    </div>
  );
}
