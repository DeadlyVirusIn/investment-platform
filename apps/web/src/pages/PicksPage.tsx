// PicksPage — AI Investing OS homepage (portfolio-first composition).

import { useEffect, useMemo, useState } from "react";

import PickModal from "@/components/picks/PickModal";
import FilterBar from "@/components/picks/FilterBar";
import ActionQueue from "@/components/picks/ActionQueue";

import PortfolioSnapshot from "@/components/portfolio/PortfolioSnapshot";
import TodayPanel from "@/components/portfolio/TodayPanel";
import HealthRail from "@/components/portfolio/HealthRail";
import TradeLifecycle from "@/components/portfolio/TradeLifecycle";
import PositionsTable from "@/components/portfolio/PositionsTable";
import StrategyModules from "@/components/portfolio/StrategyModules";
import PremiumIncome from "@/components/portfolio/PremiumIncome";
import MarketEvents from "@/components/portfolio/MarketEvents";
import DensityToggle, {
  readInitialDensity, type Density,
} from "@/components/portfolio/DensityToggle";

import {
  fetchPicks, fetchLatestPrices, type Pick, type LatestPrice,
} from "@/lib/picks/api";
import {
  buildBriefing, derivePriority, type PicksFilter,
} from "@/lib/picks/copilot";
import { fetchCommandBar } from "@/lib/portfolio/api";
import {
  fetchMarketEvents, type EventsState, type SymbolEvents,
} from "@/lib/portfolio/events";


export default function PicksPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [priceMap, setPriceMap] = useState<Record<string, LatestPrice | null | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openPickId, setOpenPickId] = useState<string | null>(null);
  const [filter, setFilter] = useState<PicksFilter>("all");
  const [monthlyPremium, setMonthlyPremium] = useState<number | null>(null);
  const [density, setDensity] = useState<Density>(() => readInitialDensity());
  const [eventsState, setEventsState] = useState<EventsState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPicks(30)
      .then(rows => {
        if (cancelled) return;
        setPicks(rows);
        setLoading(false);

        const symbols = rows.map(r => r.symbol).filter((s): s is string => !!s);
        const initialMap: Record<string, undefined> = {};
        symbols.forEach(s => { initialMap[s] = undefined; });
        setPriceMap(initialMap);

        if (symbols.length > 0) {
          fetchLatestPrices(symbols).then(map => {
            if (!cancelled) setPriceMap(map);
          });
          fetchMarketEvents(symbols).then(s => {
            if (!cancelled) setEventsState(s);
          });
        }
      })
      .catch(err => {
        if (cancelled) return;
        setError(err?.message ?? "Failed to load suggestions.");
        setLoading(false);
      });

    fetchCommandBar().then(d => {
      if (!cancelled) setMonthlyPremium(d.monthlyPremium);
    });

    return () => { cancelled = true; };
  }, []);

  const openPick = useMemo(
    () => picks.find(p => p.id === openPickId) ?? null,
    [picks, openPickId],
  );
  const openPrice = openPick?.symbol ? priceMap[openPick.symbol] ?? null : null;

  const sortedPicks = useMemo(() => {
    const order: Record<string, number> = { buy: 0, sell: 1, trim: 2, hold: 3 };
    return [...picks].sort((a, b) => {
      const ao = a.adjusted_action ?? a.action;
      const bo = b.adjusted_action ?? b.action;
      const oa = order[ao] ?? 9;
      const ob = order[bo] ?? 9;
      if (oa !== ob) return oa - ob;
      const ca = parseFloat(a.adjusted_confidence ?? a.confidence ?? "0");
      const cb = parseFloat(b.adjusted_confidence ?? b.confidence ?? "0");
      return cb - ca;
    });
  }, [picks]);

  const briefing = useMemo(() => buildBriefing(sortedPicks), [sortedPicks]);
  const priority = useMemo(() => derivePriority(sortedPicks), [sortedPicks]);

  const queuePicks = useMemo(
    () => priority ? sortedPicks.filter(p => p.id !== priority.pick.id) : sortedPicks,
    [sortedPicks, priority],
  );

  const watchlistCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "hold").length;
  const riskCount = sortedPicks.filter(p =>
    p.stale_data || !p.enough_data || (p.adjusted_action ?? p.action) === "sell"
  ).length;
  const staleCount = sortedPicks.filter(p => p.stale_data).length;

  const priorityPrice = priority?.pick.symbol ? priceMap[priority.pick.symbol] ?? null : null;

  const allSymbols = useMemo(
    () => sortedPicks.map(p => p.symbol).filter((s): s is string => !!s),
    [sortedPicks],
  );

  const eventsBySymbol: Record<string, SymbolEvents> | undefined =
    eventsState.status === "ready" ? eventsState.data.symbols : undefined;

  return (
    <div
      className="picks-root"
      data-test="picks-root"
      data-density={density}
    >
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">AI Investing OS</h1>
            <p className="picks-subtitle">
              {loading
                ? "Loading…"
                : `${sortedPicks.length} live ${sortedPicks.length === 1 ? "signal" : "signals"} · paper portfolio`}
            </p>
          </div>
          <DensityToggle value={density} onChange={setDensity} />
        </header>

        <PortfolioSnapshot />

        {loading && (
          <div className="picks-loading" data-test="picks-loading">
            Loading AI suggestions…
          </div>
        )}

        {error && (
          <div className="picks-error" data-test="picks-error">{error}</div>
        )}

        {!loading && !error && sortedPicks.length === 0 && (
          <div className="picks-empty" data-test="picks-empty">
            No AI suggestions available right now. The recommendation engine
            may still be running. Check back shortly.
          </div>
        )}

        {!loading && !error && sortedPicks.length > 0 && (
          <>
            <TodayPanel
              briefing={briefing}
              priority={priority}
              priorityPrice={priorityPrice}
              watchlistCount={watchlistCount}
              riskCount={riskCount}
              monthlyPremium={monthlyPremium}
              onOpenCockpit={setOpenPickId}
              onFilterChange={setFilter}
            />

            <MarketEvents symbols={allSymbols} />

            <section className="queue-section">
              <header className="pi-section-header">
                <h3>Today's Action Queue</h3>
                <span className="pi-section-sub">
                  Grouped by recommendation · click any card for the research cockpit
                </span>
              </header>
              <FilterBar picks={sortedPicks} active={filter} onChange={setFilter} />

              <div className="queue-layout">
                <div className="queue-main">
                  <ActionQueue
                    picks={queuePicks}
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

            <TradeLifecycle />
            <PremiumIncome />
            <StrategyModules />
            <PositionsTable />
          </>
        )}
      </div>

      <PickModal pick={openPick} priceCache={openPrice} onClose={() => setOpenPickId(null)} />
    </div>
  );
}
