// Options Playbook library — Phase F.4.
//
// Lists every strategy playbook grouped by bias. Calm, calm-by-default
// strategist's library. Honest "stub" tag on entries without full
// educational content yet.

import { useEffect, useState } from "react";

import OptionsPlaybookCard, {
  PlaybookLibraryRow,
} from "@/components/options/copilot/OptionsPlaybookCard";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";


const BIAS_GROUPS: Array<{ key: string; label: string }> = [
  { key: "bullish",    label: "Bullish strategies" },
  { key: "bearish",    label: "Bearish strategies" },
  { key: "neutral",    label: "Neutral / income strategies" },
  { key: "event",      label: "Event-driven strategies" },
  { key: "developing", label: "Engine-internal" },
];


export default function OptionsPlaybookLibraryPage() {
  const [rows, setRows] = useState<PlaybookLibraryRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/options/playbooks")
      .then(r => r.ok ? r.json() : null)
      .then(j => {
        if (cancelled) return;
        setRows(j?.items ?? []);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="opt-playbook-page">
      {/* H.6 — first-visit orientation. */}
      <OptionsOrientationCard surface="learn" />

      <section className="opt-research-banner">
        <div className="opt-research-banner-row">
          <span className="opt-narrative-eyebrow">
            Learn · per-strategy playbooks
          </span>
          <OptionsLiveStateChip />
        </div>
        <h1 className="opt-narrative-sentence">
          One playbook per strategy. Open the one you want to
          understand.
        </h1>
        <p className="opt-narrative-supporting">
          Each playbook explains when the strategy fits, when it
          doesn't, how IV and theta behave, and what your beginner
          or advanced read should be.
        </p>
      </section>

      {loading && (
        <p className="opt-caption-muted">Loading playbooks…</p>
      )}

      {!loading && rows.length === 0 && (
        <section className="opt-playbook-empty">
          <h3>No playbooks seeded</h3>
          <p className="opt-caption-muted">
            options_strategy_playbook is empty. Run the seed migration
            to populate.
          </p>
        </section>
      )}

      {!loading && rows.length > 0 && BIAS_GROUPS.map(group => {
        const items = rows.filter(r => r.bias === group.key);
        if (items.length === 0) return null;
        return (
          <section
            key={group.key}
            className="opt-playbook-group"
            data-test={`opt-playbook-group-${group.key}`}
          >
            <header className="opt-playbook-group-header">
              <h3 className="opt-playbook-group-title">{group.label}</h3>
              <span className="opt-caption-muted">
                {items.length} playbook{items.length === 1 ? "" : "s"}
              </span>
            </header>
            <div className="opt-playbook-grid">
              {items.map(r => (
                <OptionsPlaybookCard key={r.rule_id} row={r} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
