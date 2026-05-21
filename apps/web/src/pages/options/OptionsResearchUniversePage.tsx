// Options Research universe page — Phase D.
//
// Grid of per-underlying cards. Each card links to the deep-dive
// /options/research/:symbol page. AI conviction layer behind the
// strategist; not a chain terminal.

import { useEffect, useState } from "react";

import OptionsResearchUnderlyingCard, {
  ResearchUniverseRow,
} from "@/components/options/copilot/OptionsResearchUnderlyingCard";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";


export default function OptionsResearchUniversePage() {
  const [rows, setRows] = useState<ResearchUniverseRow[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/options/research/universe")
      .then(r => r.ok ? r.json() : null)
      .then(j => {
        if (cancelled) return;
        setRows(j?.rows ?? []);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="opt-research-page" data-test="opt-research-page">
      <OptionsOrientationCard surface="research" />

      <section className="opt-research-banner">
        <div className="opt-research-banner-row">
          <span className="opt-research-eyebrow">
            Research · per-underlying conviction
          </span>
          <OptionsLiveStateChip />
        </div>
        <h1 className="opt-narrative-sentence">
          Here's how we're reading each underlying right now.
        </h1>
        <p className="opt-narrative-supporting">
          Pick a symbol for the full take — posture, premium
          environment, expected move, catalysts ahead, and the
          strategies that currently fit.
        </p>
      </section>

      {loading && (
        <div className="opt-caption-muted opt-research-loading">
          Loading universe…
        </div>
      )}

      {!loading && rows && rows.length === 0 && (
        <section className="opt-research-empty">
          <h3>No underlyings ingested yet</h3>
          <p className="opt-caption-muted">
            The Research surface needs at least one shadow observation
            or one calendar event for a symbol before it can compose
            a read. When the engine fires next, this page will fill in.
          </p>
        </section>
      )}

      {!loading && rows && rows.length > 0 && (
        <div className="opt-research-grid">
          {rows.map(row => (
            <OptionsResearchUnderlyingCard key={row.symbol} row={row} />
          ))}
        </div>
      )}
    </div>
  );
}
