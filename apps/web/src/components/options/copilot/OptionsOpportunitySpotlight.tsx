// OptionsOpportunitySpotlight — Today-page top-conviction strip.
//
// Reads /api/options/opportunities (cross-lane top-N by composite
// score). Renders the canonical OptionsOpportunityCard so visual
// language matches the Opportunities lanes and any future surface
// that consumes the same payload.
//
// Empty state is honest: "No high-conviction setups today — the
// strategist is patient." The card watermark "shadow" + global
// live-state chip already convey paper-only framing; no extra
// disclaimer here.

import { useEffect, useState } from "react";

import OptionsOpportunityCard, {
  OpportunityPayload,
} from "./OptionsOpportunityCard";


interface OpportunitiesResponse {
  count: number;
  items: OpportunityPayload[];
}


export default function OptionsOpportunitySpotlight({
  limit = 3,
}: { limit?: number }) {
  const [items, setItems] = useState<OpportunityPayload[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/options/opportunities?limit=${limit}`)
      .then(r => r.ok ? r.json() : null)
      .then(j => {
        if (cancelled) return;
        const resp = j as OpportunitiesResponse | null;
        setItems(resp?.items ?? []);
        setLoading(false);
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [limit]);

  if (loading) {
    return (
      <section className="opt-spotlight opt-spotlight-loading"
               data-test="opt-spotlight">
        <div className="opt-caption-muted">
          Loading today's high-conviction setups…
        </div>
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="opt-spotlight opt-spotlight-empty"
               data-test="opt-spotlight">
        <header className="opt-spotlight-header">
          <h3 className="opt-spotlight-title">Today's opportunities</h3>
        </header>
        <p className="opt-caption-muted">
          Nothing crossed our conviction bar today. We're patient —
          better odds emerge when the tape lines up.
        </p>
      </section>
    );
  }

  // Phase J — single accent moment per page. The strongest composite
  // (≥ 0.75) earns the conviction gold stripe. If none qualify, no card
  // is decorated; the page reads calm without a manufactured anchor.
  const convictionId = (() => {
    const ranked = [...items]
      .filter(i => (i.composite_score ?? i.score ?? 0) >= 0.75)
      .sort((a, b) =>
        (b.composite_score ?? b.score ?? 0)
        - (a.composite_score ?? a.score ?? 0));
    return ranked[0]?.observation_id ?? null;
  })();

  return (
    <section className="opt-spotlight"
             data-test="opt-spotlight">
      <header className="opt-spotlight-header">
        <h3 className="opt-spotlight-title">Today's opportunities</h3>
        <span className="opt-caption-muted">
          Top {items.length} · ranked by composite score · read-only
        </span>
      </header>
      <div className="opt-spotlight-cards">
        {items.map(item => (
          <OptionsOpportunityCard
            key={String(item.observation_id)}
            item={item}
            canaryEnabled={false}
            conviction={item.observation_id === convictionId} />
        ))}
      </div>
    </section>
  );
}
