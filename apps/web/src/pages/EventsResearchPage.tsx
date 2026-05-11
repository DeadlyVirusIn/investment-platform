// EventsResearchPage — Events & Catalysts.
// Catalysts explain WHY signals are changing.

import { useEffect, useState } from "react";

import MarketEvents from "@/components/portfolio/MarketEvents";
import { fetchPicks, type Pick } from "@/lib/picks/api";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";


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

  const nowText = loading
    ? undefined
    : symbols.length === 0
      ? undefined
      : `${symbols.length} symbol${symbols.length === 1 ? "" : "s"} from active recommendations · SEC EDGAR feed live · provider news where keys configured.`;

  return (
    <div className="picks-root" data-test="events-research-page" data-density="cozy">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Events &amp; Catalysts</h1>
            <p className="picks-subtitle">
              SEC filings, news momentum, and earnings windows — the "why" behind signal changes
            </p>
          </div>
        </header>

        <PageChapter pathname="/events" now={nowText} />

        <MarketEvents symbols={symbols} />

        <NextStepCard
          pathname="/events"
          rationale={
            symbols.length > 0
              ? `Map these catalysts to the ${symbols.length} live signal${symbols.length === 1 ? "" : "s"}.`
              : undefined
          }
        />

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>
    </div>
  );
}
