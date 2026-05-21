// Options Journal unified page — Phase E.
//
// Vertical timeline of strategist memory:
//   * shadow observations
//   * candidate emissions
//   * proposed/filled/closed trades
//   * lifecycle events
//
// Filter rail (type + underlying), honest empty state, drawer
// for per-trade thesis evolution.

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import OptionsJournalEntry, {
  JournalEntryPayload,
} from "@/components/options/copilot/OptionsJournalEntry";
import OptionsThesisEvolutionDrawer from
  "@/components/options/copilot/OptionsThesisEvolutionDrawer";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";


interface TimelineResponse {
  count: number;
  lookback_days: number;
  known_entry_types: string[];
  items: JournalEntryPayload[];
}


const TYPE_GROUPS: Array<{ label: string; types: string[] }> = [
  { label: "All", types: [] },
  { label: "Decisions", types: ["candidate_emitted", "trade_proposed"] },
  { label: "Lifecycle", types: [
    "lifecycle_filled", "lifecycle_closed", "lifecycle_expired",
    "lifecycle_assigned", "lifecycle_force_closed",
  ]},
  { label: "Flags", types: [
    "lifecycle_pin_risk", "lifecycle_early_assign_risk",
    "lifecycle_expiring_flagged",
  ]},
  { label: "Shadow", types: ["shadow_observation"] },
];


export default function OptionsJournalUnifiedPage() {
  const [params, setParams] = useSearchParams();
  const filterUnderlying = params.get("underlying") || "";
  const filterGroup = params.get("group") || "All";

  const [resp, setResp] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [drawerTradeId, setDrawerTradeId] = useState<number | null>(null);

  const activeTypes = useMemo(() => {
    const g = TYPE_GROUPS.find(x => x.label === filterGroup);
    return g?.types ?? [];
  }, [filterGroup]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = new URLSearchParams({ limit: "200", lookback_days: "30" });
    if (filterUnderlying) qs.set("underlying", filterUnderlying);
    activeTypes.forEach(t => qs.append("entry_type", t));
    fetch(`/api/options/journal/timeline?${qs.toString()}`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled) { setResp(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filterUnderlying, activeTypes.join(",")]);  // eslint-disable-line react-hooks/exhaustive-deps

  const items = resp?.items ?? [];
  const groupLabels = TYPE_GROUPS.map(g => g.label);

  return (
    <div className="opt-journal-page" data-test="opt-journal-page">
      <OptionsOrientationCard surface="journal" />

      <section className="opt-research-banner">
        <div className="opt-research-banner-row">
          <span className="opt-narrative-eyebrow">
            Journal · the strategist's memory
          </span>
          <OptionsLiveStateChip />
        </div>
        <h1 className="opt-narrative-sentence">
          {items.length > 0
            ? `Here's everything we noticed in the last ${resp?.lookback_days ?? 30} days.`
            : "We've been quiet lately. That's often the right answer."}
        </h1>
        {items.length > 0 && (
          <p className="opt-narrative-supporting">
            Idea → conviction → management → outcome. Pick any entry
            to see the thinking that led to it or the consequences
            that followed.
          </p>
        )}
      </section>

      {/* Filters */}
      <section className="opt-journal-filter-rail">
        <div className="opt-journal-filter-group">
          <span className="opt-journal-filter-label">Type</span>
          {groupLabels.map(label => (
            <button
              key={label}
              type="button"
              className={
                "opt-action-pill"
                + (filterGroup === label ? " opt-action-pill-active" : "")
              }
              onClick={() => {
                const np = new URLSearchParams(params);
                np.set("group", label);
                setParams(np, { replace: true });
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="opt-journal-filter-group">
          <span className="opt-journal-filter-label">Underlying</span>
          <input
            type="text"
            value={filterUnderlying}
            placeholder="all"
            onChange={e => {
              const v = e.target.value.toUpperCase().slice(0, 12);
              const np = new URLSearchParams(params);
              if (v) np.set("underlying", v);
              else np.delete("underlying");
              setParams(np, { replace: true });
            }}
            className="opt-journal-filter-input"
          />
        </div>
      </section>

      {loading && (
        <p className="opt-caption-muted">Loading timeline…</p>
      )}

      {!loading && items.length === 0 && (
        <section className="opt-journal-empty">
          <h3>Nothing to remember from this window</h3>
          <p className="opt-caption-muted">
            We've been quiet here. As the engine notices setups,
            interprets them, and trades land lifecycle events, the
            story will unfold on this page.
          </p>
        </section>
      )}

      {!loading && items.length > 0 && (
        <section className="opt-journal-timeline" data-test="opt-journal-timeline">
          {items.map(item => (
            <OptionsJournalEntry
              key={item.entry_id}
              item={item}
              onOpenEvolution={(tid) => setDrawerTradeId(tid)}
            />
          ))}
        </section>
      )}

      <OptionsThesisEvolutionDrawer
        open={drawerTradeId !== null}
        tradeId={drawerTradeId}
        onClose={() => setDrawerTradeId(null)} />
    </div>
  );
}
