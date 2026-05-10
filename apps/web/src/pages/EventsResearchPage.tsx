// EventsResearchPage — full Market Events & Catalysts grid.

import { useEffect, useState } from "react";

import MarketEvents from "@/components/portfolio/MarketEvents";
import { fetchPicks, type Pick } from "@/lib/picks/api";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";


export default function EventsResearchPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchPicks(50).then(rows => {
      if (cancelled) return;
      setPicks(rows);
      setLoading(false);
    }).catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const symbols = picks.map(p => p.symbol).filter((s): s is string => !!s);

  return (
    <div className="picks-root" data-test="events-research-page" data-density="cozy">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Events &amp; Research</h1>
            <p className="picks-subtitle">
              {loading
                ? "Loading…"
                : `News, SEC filings, earnings, and catalysts for ${symbols.length} tracked ${symbols.length === 1 ? "symbol" : "symbols"}`}
            </p>
          </div>
        </header>

        <MarketEvents symbols={symbols} />

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>
    </div>
  );
}
