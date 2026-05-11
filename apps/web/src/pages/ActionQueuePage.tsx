// ActionQueuePage — full grouped recommendation cards + filters.
// Extracted from the legacy Overview composition (Phase 11A).

import { useEffect, useMemo, useState } from "react";

import PickModal from "@/components/picks/PickModal";
import FilterBar from "@/components/picks/FilterBar";
import ActionQueue from "@/components/picks/ActionQueue";
import HealthRail from "@/components/portfolio/HealthRail";
import DensityToggle, {
  readInitialDensity, type Density,
} from "@/components/portfolio/DensityToggle";

import {
  fetchPicks, fetchLatestPrices, type Pick, type LatestPrice,
} from "@/lib/picks/api";
import {
  buildBriefing, type PicksFilter,
} from "@/lib/picks/copilot";
import {
  fetchMarketEvents, type EventsState, type SymbolEvents,
} from "@/lib/portfolio/events";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";
import FetchError from "@/components/shell/FetchError";


export default function ActionQueuePage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [priceMap, setPriceMap] = useState<Record<string, LatestPrice | null | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [openPickId, setOpenPickId] = useState<string | null>(null);
  const [filter, setFilter] = useState<PicksFilter>("all");
  const [density, setDensity] = useState<Density>(() => readInitialDensity());
  const [eventsState, setEventsState] = useState<EventsState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchPicks(50).then(rows => {
      if (cancelled) return;
      setPicks(rows);
      setLoading(false);
      const symbols = rows.map(r => r.symbol).filter((s): s is string => !!s);
      if (symbols.length > 0) {
        fetchLatestPrices(symbols).then(map => { if (!cancelled) setPriceMap(map); });
        fetchMarketEvents(symbols).then(s => { if (!cancelled) setEventsState(s); });
      }
    }).catch((e: unknown) => {
      if (cancelled) return;
      setError(e instanceof Error ? e : new Error(String(e)));
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const sortedPicks = useMemo(() => {
    const order: Record<string, number> = { buy: 0, sell: 1, trim: 2, hold: 3 };
    return [...picks].sort((a, b) => {
      const ao = a.adjusted_action ?? a.action;
      const bo = b.adjusted_action ?? b.action;
      const oa = order[ao] ?? 9, ob = order[bo] ?? 9;
      if (oa !== ob) return oa - ob;
      const ca = parseFloat(a.adjusted_confidence ?? a.confidence ?? "0");
      const cb = parseFloat(b.adjusted_confidence ?? b.confidence ?? "0");
      return cb - ca;
    });
  }, [picks]);

  const briefing = useMemo(() => buildBriefing(sortedPicks), [sortedPicks]);
  const watchlistCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "hold").length;
  const riskCount = sortedPicks.filter(p =>
    p.stale_data || !p.enough_data || (p.adjusted_action ?? p.action) === "sell"
  ).length;
  const staleCount = sortedPicks.filter(p => p.stale_data).length;

  const openPick = picks.find(p => p.id === openPickId) ?? null;
  const openPrice = openPick?.symbol ? priceMap[openPick.symbol] ?? null : null;
  const eventsBySymbol: Record<string, SymbolEvents> | undefined =
    eventsState.status === "ready" ? eventsState.data.symbols : undefined;

  return (
    <div className="picks-root" data-test="action-queue-page" data-density={density}>
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Action Queue</h1>
            <p className="picks-subtitle">
              {loading ? "Loading…" : `${sortedPicks.length} live ${sortedPicks.length === 1 ? "signal" : "signals"} · grouped by recommendation`}
            </p>
          </div>
          <DensityToggle value={density} onChange={setDensity} />
        </header>

        <PageChapter
          pathname="/action-queue"
          now={
            sortedPicks.length === 0
              ? undefined
              : `Today the AI favors ${briefing.postureLabel.toLowerCase()} — ${sortedPicks.length} live signals across Buy / Trim / Hold / Sell.`
          }
        />

        {loading && <div className="picks-loading">Loading AI suggestions…</div>}

        {error && (
          <FetchError
            title="Could not load action queue"
            message={error.message}
            onRetry={() => window.location.reload()}
          />
        )}

        {!loading && !error && sortedPicks.length > 0 && (
          <section className="queue-section">
            <FilterBar picks={sortedPicks} active={filter} onChange={setFilter} />
            <div className="queue-layout">
              <div className="queue-main">
                <ActionQueue
                  picks={sortedPicks}
                  allPicks={sortedPicks}
                  priceMap={priceMap}
                  filter={filter}
                  eventsBySymbol={eventsBySymbol}
                  onPickClick={setOpenPickId}
                />
              </div>
              <HealthRail
                staleCount={staleCount}
                watchlistCount={watchlistCount}
                riskCount={riskCount}
                posture={briefing.postureLabel}
              />
            </div>
          </section>
        )}

        <NextStepCard
          pathname="/action-queue"
          rationale={
            sortedPicks.length === 0
              ? undefined
              : `Validate model quality before acting on ${sortedPicks.length} live signals.`
          }
        />

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>

      <PickModal pick={openPick} priceCache={openPrice} onClose={() => setOpenPickId(null)} />
    </div>
  );
}
