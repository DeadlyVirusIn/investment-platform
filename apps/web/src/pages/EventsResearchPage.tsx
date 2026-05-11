// EventsResearchPage — Events & Catalysts.
// Catalysts explain WHY signals are changing.

import { useEffect, useState } from "react";

import MarketEvents from "@/components/portfolio/MarketEvents";
import { fetchPicks, type Pick } from "@/lib/picks/api";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";
import FetchError from "@/components/shell/FetchError";
import DensityToggle, {
  readInitialDensity, type Density,
} from "@/components/portfolio/DensityToggle";


export default function EventsResearchPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(true);
  // Phase 15a — Truth fix. Previously .catch(() => setLoading(false))
  // silently swallowed every fetch error, making a 500 indistinguishable
  // from a clean empty day. Surface a real FetchError instead.
  const [error, setError] = useState<Error | null>(null);
  const [density, setDensity] = useState<Density>(() => readInitialDensity());

  useEffect(() => {
    let cancelled = false;
    fetchPicks(50).then(rows => {
      if (cancelled) return;
      setPicks(rows);
      setLoading(false);
    }).catch((e: unknown) => {
      if (cancelled) return;
      setError(e instanceof Error ? e : new Error(String(e)));
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const symbols = picks.map(p => p.symbol).filter((s): s is string => !!s);

  const nowText = loading
    ? undefined
    : symbols.length === 0
      ? undefined
      : `${symbols.length} symbol${symbols.length === 1 ? "" : "s"} from active recommendations · SEC EDGAR feed live · provider news where keys configured.`;

  return (
    <div className="picks-root" data-test="events-research-page" data-density={density}>
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Events &amp; Catalysts</h1>
            <p className="picks-subtitle">
              SEC filings, news momentum, and earnings windows — the "why" behind signal changes
            </p>
          </div>
          <DensityToggle value={density} onChange={setDensity} />
        </header>

        <PageChapter pathname="/events" now={nowText} />

        {error && (
          <FetchError
            title="Could not load market events"
            message={error.message}
            onRetry={() => window.location.reload()}
          />
        )}

        {!error && <MarketEvents symbols={symbols} />}

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
