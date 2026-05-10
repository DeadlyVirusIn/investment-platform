// PicksPage — premium copilot landing.
// Hero briefing + priority action + filter bar + grid + sidebar + modal.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import PickBox from "@/components/picks/PickBox";
import PickModal from "@/components/picks/PickModal";
import Briefing from "@/components/picks/Briefing";
import FilterBar from "@/components/picks/FilterBar";
import Sidebar from "@/components/picks/Sidebar";
import EmptyStateCard from "@/components/picks/EmptyStateCard";
import PriorityAction from "@/components/picks/PriorityAction";
import CommandBar from "@/components/portfolio/CommandBar";
import PositionsTable from "@/components/portfolio/PositionsTable";
import StrategyModules from "@/components/portfolio/StrategyModules";
import PremiumIncome from "@/components/portfolio/PremiumIncome";
import {
  fetchPicks, fetchLatestPrices, type Pick, type LatestPrice,
} from "@/lib/picks/api";
import {
  buildBriefing, applyFilter, rankingLabel, derivePriority,
  type PicksFilter,
} from "@/lib/picks/copilot";


export default function PicksPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [priceMap, setPriceMap] = useState<Record<string, LatestPrice | null | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openPickId, setOpenPickId] = useState<string | null>(null);
  const [filter, setFilter] = useState<PicksFilter>("all");

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
        }
      })
      .catch(err => {
        if (cancelled) return;
        setError(err?.message ?? "Failed to load suggestions.");
        setLoading(false);
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

  const gridPicks = useMemo(() => {
    // Exclude priority pick from the grid to avoid duplication
    const base = priority ? sortedPicks.filter(p => p.id !== priority.pick.id) : sortedPicks;
    return applyFilter(base, filter);
  }, [sortedPicks, filter, priority]);

  const buyCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "buy").length;
  const sellCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "sell").length;

  const priorityPrice = priority?.pick.symbol ? priceMap[priority.pick.symbol] ?? null : null;

  return (
    <div className="picks-root" data-test="picks-root">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">AI Investing OS</h1>
            <p className="picks-subtitle">
              {loading ? "Loading…" : `${sortedPicks.length} live ${sortedPicks.length === 1 ? "signal" : "signals"} · paper portfolio`}
            </p>
          </div>
          <nav className="picks-archive-nav" data-test="picks-archive-nav">
            <span style={{ color: "var(--picks-ink-recede)" }}>archive</span>
            <Link to="/overview?view=working">working</Link>
            <Link to="/overview?view=conviction">conviction</Link>
            <Link to="/overview?view=copilot">copilot</Link>
            <Link to="/overview?view=living">living</Link>
            <Link to="/overview?view=stream">stream</Link>
            <Link to="/overview?view=legacy">legacy</Link>
          </nav>
        </header>

        <CommandBar />

        {loading && (
          <div className="picks-loading" data-test="picks-loading">
            Loading AI suggestions…
          </div>
        )}

        {error && (
          <div className="picks-error" data-test="picks-error">
            {error}
          </div>
        )}

        {!loading && !error && sortedPicks.length === 0 && (
          <div className="picks-empty" data-test="picks-empty">
            No AI suggestions available right now. The recommendation engine may
            still be running. Check back shortly.
          </div>
        )}

        {!loading && !error && sortedPicks.length > 0 && (
          <>
            <Briefing briefing={briefing} onFilterChange={setFilter} />

            {priority && (
              <PriorityAction
                priority={priority}
                price={priorityPrice}
                onOpenCockpit={setOpenPickId}
                onFilterChange={setFilter}
              />
            )}

            <FilterBar picks={sortedPicks} active={filter} onChange={setFilter} />

            <div className="picks-layout">
              <main className="picks-main">
                <div className="picks-grid" data-test="picks-grid">
                  {filter === "all" && buyCount === 0 && <EmptyStateCard action="buy" />}
                  {filter === "all" && sellCount === 0 && <EmptyStateCard action="sell" />}

                  {gridPicks.map(pick => (
                    <PickBox
                      key={pick.id}
                      pick={pick}
                      price={pick.symbol ? priceMap[pick.symbol] : null}
                      rankingLabel={rankingLabel(pick, sortedPicks)}
                      onClick={setOpenPickId}
                    />
                  ))}

                  {gridPicks.length === 0 && filter !== "all" && (
                    <div className="picks-filter-empty">No picks match this filter.</div>
                  )}
                </div>
              </main>

              <Sidebar picks={sortedPicks} briefing={briefing} onPickClick={setOpenPickId} />
            </div>

            <PositionsTable />
            <PremiumIncome />
            <StrategyModules />
          </>
        )}
      </div>

      <PickModal pick={openPick} priceCache={openPrice} onClose={() => setOpenPickId(null)} />
    </div>
  );
}
