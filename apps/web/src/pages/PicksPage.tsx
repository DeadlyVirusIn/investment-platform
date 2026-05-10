// PicksPage — Overview launcher (Phase 11A).
// Compact 5-second answer: snapshot, AI summary, top action, small
// previews for action queue / portfolio health / market events,
// CTAs to the dedicated pages.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import PickModal from "@/components/picks/PickModal";

import PortfolioSnapshot from "@/components/portfolio/PortfolioSnapshot";
import TodayPanel from "@/components/portfolio/TodayPanel";
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
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";


interface LauncherCardProps {
  to: string;
  eyebrow: string;
  title: string;
  metric: string;
  body: string;
  tone?: "good" | "warn" | "bad" | "default";
}


function LauncherCard({ to, eyebrow, title, metric, body, tone = "default" }: LauncherCardProps) {
  return (
    <Link to={to} className="launcher-card" data-tone={tone}>
      <span className="launcher-eyebrow">{eyebrow}</span>
      <div className="launcher-row">
        <h3 className="launcher-title">{title}</h3>
        <span className="launcher-metric">{metric}</span>
      </div>
      <p className="launcher-body">{body}</p>
      <span className="launcher-cta">Open →</span>
    </Link>
  );
}


export default function PicksPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [priceMap, setPriceMap] = useState<Record<string, LatestPrice | null | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [openPickId, setOpenPickId] = useState<string | null>(null);
  const [_filter, setFilter] = useState<PicksFilter>("all");
  const [monthlyPremium, setMonthlyPremium] = useState<number | null>(null);
  const [density, setDensity] = useState<Density>(() => readInitialDensity());

  useEffect(() => {
    let cancelled = false;
    fetchPicks(30).then(rows => {
      if (cancelled) return;
      setPicks(rows);
      setLoading(false);
      const symbols = rows.map(r => r.symbol).filter((s): s is string => !!s);
      if (symbols.length > 0) {
        fetchLatestPrices(symbols).then(map => { if (!cancelled) setPriceMap(map); });
      }
    }).catch(() => { if (!cancelled) setLoading(false); });
    fetchCommandBar().then(d => { if (!cancelled) setMonthlyPremium(d.monthlyPremium); });
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
  const priority = useMemo(() => derivePriority(sortedPicks), [sortedPicks]);

  const buyCount  = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "buy").length;
  const sellCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "sell").length;
  const trimCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "trim").length;
  const watchlistCount = sortedPicks.filter(p => (p.adjusted_action ?? p.action) === "hold").length;
  const riskCount = sortedPicks.filter(p =>
    p.stale_data || !p.enough_data || (p.adjusted_action ?? p.action) === "sell"
  ).length;

  const openPick = picks.find(p => p.id === openPickId) ?? null;
  const openPrice = openPick?.symbol ? priceMap[openPick.symbol] ?? null : null;
  const priorityPrice = priority?.pick.symbol ? priceMap[priority.pick.symbol] ?? null : null;

  return (
    <div className="picks-root" data-test="picks-root" data-density={density}>
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Overview</h1>
            <p className="picks-subtitle">
              {loading ? "Loading…" : `${sortedPicks.length} live ${sortedPicks.length === 1 ? "signal" : "signals"} · 5-second answer`}
            </p>
          </div>
          <DensityToggle value={density} onChange={setDensity} />
        </header>

        <PortfolioSnapshot />

        {!loading && sortedPicks.length > 0 && (
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

            <section className="launcher-grid">
              <LauncherCard
                to="/action-queue"
                eyebrow="Action Queue"
                title="All AI signals"
                metric={`${buyCount}B · ${sellCount}S · ${trimCount}T · ${watchlistCount}H`}
                body="Grouped Buy / Sell / Trim / Hold cards, filters, and the full research cockpit."
              />
              <LauncherCard
                to="/portfolio"
                eyebrow="Portfolio Intelligence"
                title="Positions & exposure"
                metric={`${riskCount} risk-flagged`}
                body="Open positions, P&L, return %, sector + strategy exposure."
                tone={riskCount > 0 ? "warn" : "default"}
              />
              <LauncherCard
                to="/events"
                eyebrow="Events & Research"
                title="News, filings, earnings"
                metric={`${sortedPicks.length} symbols tracked`}
                body="SEC filings, news catalysts, earnings windows for every ticker."
              />
              <LauncherCard
                to="/strategies"
                eyebrow="Strategies"
                title="Options workflows"
                metric={monthlyPremium && monthlyPremium > 0 ? `$${(monthlyPremium / 1000).toFixed(1)}k MTD` : "—"}
                body="Wheel, covered calls, CSPs, LEAPS, spreads · trade lifecycle + premium income."
                tone={monthlyPremium && monthlyPremium > 0 ? "good" : "default"}
              />
              <LauncherCard
                to="/signal-lab"
                eyebrow="Signal Lab"
                title="Model quality"
                metric="readiness score"
                body="Action distribution, signal freshness, event-feature coverage, validation."
              />
            </section>
          </>
        )}

        {!loading && sortedPicks.length === 0 && (
          <div className="picks-empty">
            No AI suggestions available right now. Check back shortly.
          </div>
        )}

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>

      <PickModal pick={openPick} priceCache={openPrice} onClose={() => setOpenPickId(null)} />
    </div>
  );
}
