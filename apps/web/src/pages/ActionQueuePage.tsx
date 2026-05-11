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
  buildBriefing, applyFilter, type PicksFilter,
} from "@/lib/picks/copilot";
import {
  fetchMarketEvents, type EventsState, type SymbolEvents,
} from "@/lib/portfolio/events";
// Phase 15f.3 — visited-pick memory
import { useVisitedPicks } from "@/lib/picks/visited_memory";
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
  const buyCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "buy").length;
  const sellCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "sell").length;
  const trimCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "trim").length;
  const watchlistCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "hold").length;
  const riskCount = sortedPicks.filter(p =>
    p.stale_data || !p.enough_data || (p.adjusted_action ?? p.action) === "sell"
  ).length;
  const staleCount = sortedPicks.filter(p => p.stale_data).length;

  const openPick = picks.find(p => p.id === openPickId) ?? null;
  const openPrice = openPick?.symbol ? priceMap[openPick.symbol] ?? null : null;
  const eventsBySymbol: Record<string, SymbolEvents> | undefined =
    eventsState.status === "ready" ? eventsState.data.symbols : undefined;

  // Phase 15f.1 — Traversal context. Walk the FILTERED queue (matches
  // what the user is actually scanning). Position uses 1-based count.
  const traversalList = useMemo(
    () => applyFilter(sortedPicks, filter),
    [sortedPicks, filter],
  );
  const openIdx = openPickId
    ? traversalList.findIndex(p => p.id === openPickId)
    : -1;
  const prevPickId = openIdx > 0 ? traversalList[openIdx - 1].id : null;
  const nextPickId = openIdx >= 0 && openIdx < traversalList.length - 1
    ? traversalList[openIdx + 1].id
    : null;

  // Phase 15f.3 — visited memory. Mark current open pick as visited.
  const { visited, mark: markVisited } = useVisitedPicks();
  useEffect(() => {
    if (openPickId) markVisited(openPickId);
  }, [openPickId, markVisited]);

  return (
    <div className="picks-root" data-test="action-queue-page" data-density={density}>
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Action Queue</h1>
            <p className="picks-subtitle">
              {loading
                ? "Loading…"
                : sortedPicks.length === 0
                  ? "AI decision desk · awaiting next evaluation cycle"
                  : `AI decision desk · ${briefing.postureLabel.toLowerCase()} posture · ${sortedPicks.length} live signal${sortedPicks.length === 1 ? "" : "s"}`}
            </p>
          </div>
          <DensityToggle value={density} onChange={setDensity} />
        </header>

        <PageChapter
          pathname="/action-queue"
          now={
            sortedPicks.length === 0
              ? undefined
              : `Today the AI favors ${briefing.postureLabel.toLowerCase()} — ${sortedPicks.length} live signals across buy / sell / trim / hold.`
          }
        />

        {/* Phase 14c — loading skeleton replaces sterile "Loading…" text.
            3 ghost group cards mirror the eventual ActionQueue layout. */}
        {loading && (
          <div className="action-queue action-queue-skeleton" aria-busy="true" aria-live="polite">
            {[0, 1, 2].map(i => (
              <section key={i} className="action-group action-group-skeleton">
                <div className="action-group-skeleton-header" />
                <div className="action-group-skeleton-grid">
                  <div className="action-group-skeleton-card" />
                  <div className="action-group-skeleton-card" />
                  <div className="action-group-skeleton-card" />
                </div>
              </section>
            ))}
            <span className="u-sr-only">Loading AI recommendations…</span>
          </div>
        )}

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

            {/* Phase 14c — "Why no buys?" panel. Honest derivation from
                briefing.body + counts; never invented. Renders only when
                there are zero buy signals AND there are some non-buy
                signals (otherwise empty state below covers it). */}
            {buyCount === 0 && sortedPicks.length > 0 && (
              <aside className="why-no-buys" data-test="why-no-buys">
                <div className="why-no-buys-head">
                  <span className="why-no-buys-eyebrow">Why no buys?</span>
                  <span className="why-no-buys-posture">
                    {briefing.postureLabel} posture
                  </span>
                </div>
                <p className="why-no-buys-body">
                  No buy setups passed the engine&rsquo;s thresholds today.
                  The strongest live signals are{" "}
                  {trimCount > 0 && `${trimCount} trim${trimCount === 1 ? "" : "s"}`}
                  {trimCount > 0 && (sellCount > 0 || watchlistCount > 0) && " · "}
                  {sellCount > 0 && `${sellCount} sell${sellCount === 1 ? "" : "s"}`}
                  {sellCount > 0 && watchlistCount > 0 && " · "}
                  {watchlistCount > 0 && `${watchlistCount} watch${watchlistCount === 1 ? "" : "es"}`}
                  {(trimCount + sellCount + watchlistCount) === 0 && "watchlist holds only"}.
                </p>
                <p className="why-no-buys-meta">
                  Buys reappear when momentum, trend, and breadth filters
                  align — typically after a clean session close above the
                  short-term average.
                </p>
              </aside>
            )}

            <div className="queue-layout">
              <div className="queue-main">
                <ActionQueue
                  picks={sortedPicks}
                  allPicks={sortedPicks}
                  priceMap={priceMap}
                  filter={filter}
                  eventsBySymbol={eventsBySymbol}
                  onPickClick={setOpenPickId}
                  visited={visited}
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

        {!loading && !error && sortedPicks.length === 0 && (
          <div className="picks-empty-state" role="status">
            <span className="picks-empty-state-icon" aria-hidden="true">◌</span>
            <h2 className="picks-empty-state-title">
              No live signals on the desk
            </h2>
            <p className="picks-empty-state-body">
              The recommendation engine has not produced fresh
              suggestions yet. The decision desk fills in once the next
              evaluation cycle completes — usually within one trading
              session.
            </p>
          </div>
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

      {/* Phase 15f.1 — modal traversal across the filtered queue.
          j / k / arrow keys + footer prev/next walk continuously
          through the same list the user is scanning. */}
      <PickModal
        pick={openPick}
        priceCache={openPrice}
        onClose={() => setOpenPickId(null)}
        onPrev={prevPickId ? () => setOpenPickId(prevPickId) : undefined}
        onNext={nextPickId ? () => setOpenPickId(nextPickId) : undefined}
        position={openIdx >= 0
          ? { current: openIdx + 1, total: traversalList.length }
          : undefined}
      />
    </div>
  );
}
