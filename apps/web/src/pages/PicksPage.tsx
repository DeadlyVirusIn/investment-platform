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
import PageChapter from "@/components/shell/PageChapter";
import NextStepCard from "@/components/shell/NextStepCard";

import {
  fetchPicks, fetchLatestPrices, type Pick, type LatestPrice,
} from "@/lib/picks/api";
import {
  buildBriefing, derivePriority, type PicksFilter,
} from "@/lib/picks/copilot";
import {
  fetchCommandBar, fmtCurrency, fmtPct,
  type CommandBarData,
} from "@/lib/portfolio/api";
import { RESEARCH_NOTE } from "@/lib/ui/disclaimers";
import FetchError from "@/components/shell/FetchError";
// Phase 15e — Today's-read hero + returning-user continuity.
import OverviewHero from "@/components/picks/OverviewHero";
import {
  readOverviewSnapshot, writeOverviewSnapshot, deriveOverviewDiff,
} from "@/lib/picks/overview_memory";
// Phase 15f.3 — visited-pick memory for the priority-card modal opens.
import { useVisitedPicks } from "@/lib/picks/visited_memory";


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
  const [error, setError] = useState<Error | null>(null);
  const [openPickId, setOpenPickId] = useState<string | null>(null);
  const [_filter, setFilter] = useState<PicksFilter>("all");
  const [commandBar, setCommandBar] = useState<CommandBarData | null>(null);
  const [density, setDensity] = useState<Density>(() => readInitialDensity());
  // Phase 15e.2 — read prior snapshot ONCE per page mount (before any
  // current-cycle write). All subsequent comparisons use this captured
  // value so the diff line is derived from "what was last time" not
  // "what we just wrote 200ms ago".
  const [priorSnapshot] = useState(() => readOverviewSnapshot());

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
    }).catch((e: unknown) => {
      if (cancelled) return;
      setError(e instanceof Error ? e : new Error(String(e)));
      setLoading(false);
    });
    // Phase 14b — capture full command bar (post-13k canonical) for the
    // executive-briefing subtitle and launcher metrics.
    fetchCommandBar().then(d => { if (!cancelled) setCommandBar(d); });
    return () => { cancelled = true; };
  }, []);

  const monthlyPremium = commandBar?.monthlyPremium ?? null;

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

  // Phase 14b — executive briefing subtitle. Composes from canonical
  // command-bar fields (post-13k data-truth fix). Honest empty when
  // command bar hasn't loaded yet — no fake values, no "—" filler.
  const navText = commandBar?.totalNav != null
    ? fmtCurrency(commandBar.totalNav, { compact: true })
    : null;
  const returnText = commandBar?.totalReturnPct != null
    ? fmtPct(commandBar.totalReturnPct) + " return"
    : null;
  const postureText = sortedPicks.length > 0
    ? briefing.postureLabel.toLowerCase() + " posture"
    : null;
  const subtitleParts = [navText, returnText, postureText].filter(Boolean);
  const subtitle = loading
    ? "Loading…"
    : subtitleParts.length > 0
      ? subtitleParts.join(" · ")
      : `${sortedPicks.length} live ${sortedPicks.length === 1 ? "signal" : "signals"}`;

  // Phase 14b — last-evaluation timestamp for empty state.
  const freshAtDate = briefing.freshestAtIso
    ? new Date(briefing.freshestAtIso).toLocaleString(undefined, {
        month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      })
    : commandBar?.freshAt ?? null;

  // Phase 15e.2 — Compose current-cycle snapshot + diff vs prior visit.
  // Snapshot is computed every render but written to localStorage only
  // once per successful load via the effect below.
  const currentSnapshot = useMemo(() => ({
    ts: Date.now(),
    nav: commandBar?.totalNav ?? null,
    picksCount: sortedPicks.length,
    buy: buyCount,
    sell: sellCount,
    trim: trimCount,
    hold: watchlistCount,
    posture: briefing.posture,
    riskCount,
  }), [commandBar?.totalNav, sortedPicks.length, buyCount, sellCount,
       trimCount, watchlistCount, briefing.posture, riskCount]);

  const diff = useMemo(
    () => deriveOverviewDiff(priorSnapshot, currentSnapshot),
    [priorSnapshot, currentSnapshot],
  );

  // Persist current snapshot exactly once per page load — only after
  // the data has resolved and we have a real briefing in hand. Using
  // a stable trigger (loading + commandBar present) avoids constant
  // localStorage churn on every state setter.
  useEffect(() => {
    if (loading || error) return;
    if (commandBar?.totalNav == null && sortedPicks.length === 0) return;
    writeOverviewSnapshot(currentSnapshot);
    // Intentionally narrow deps — we only want the write to happen
    // after the page has stably resolved, not on every minor change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, error, commandBar?.totalNav, sortedPicks.length]);

  // Phase 15f.3 — mark the priority pick visited when the user opens
  // the modal from this page. PicksPage is a single-pick context (no
  // queue traversal here), so no onPrev/onNext are passed.
  const { mark: markVisited } = useVisitedPicks();
  useEffect(() => {
    if (openPickId) markVisited(openPickId);
  }, [openPickId, markVisited]);

  return (
    <div className="picks-root" data-test="picks-root" data-density={density}>
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">Overview</h1>
            <p className="picks-subtitle">{subtitle}</p>
          </div>
          <DensityToggle value={density} onChange={setDensity} />
        </header>

        {/* Phase 15e.1 — Today's-read hero.
            The first emotional moment of the page. A single calm
            institutional-strategist sentence + optional honest diff
            line vs the user's last visit. Renders BEFORE PageChapter
            so the AI's voice is the first voice the user hears. */}
        <OverviewHero
          briefing={briefing}
          diff={diff}
          ready={!loading && !error}
        />

        {/* Phase 15c3 — PageChapter without NOW (counts redundant
            with launcher metric below + new hero above). Section
            breadcrumb + WHY + NEXT cells still render. */}
        <PageChapter pathname="/overview" />

        <PortfolioSnapshot />

        {error && (
          <FetchError
            title="Could not load AI recommendations"
            message={error.message}
            onRetry={() => window.location.reload()}
          />
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

            {/* Phase 14b → 15e.1 — Today's-read line removed here;
                content elevated to the new OverviewHero block above
                PageChapter. Single hero surface; no duplicate. */}

            {/* Phase 14b — 4-card launcher grid per Phase 14 spec.
                Order matches an executive's reading flow:
                signals -> catalysts -> strategies -> risk. Signal Lab
                stays nav-reachable but is not surfaced on Overview. */}
            <section className="launcher-grid">
              <LauncherCard
                to="/action-queue"
                eyebrow="Review AI Signals"
                title="Today's recommendations"
                metric={`${buyCount} buy · ${sellCount} sell · ${trimCount} trim · ${watchlistCount} hold`}
                body="Grouped cards with plain-English thesis, confidence, and catalyst context for every active idea."
                tone={buyCount > 0 ? "good" : sellCount > 0 ? "bad" : "default"}
              />
              <LauncherCard
                to="/events"
                eyebrow="Inspect Catalysts"
                title="What's moving the market"
                metric={`${sortedPicks.length} symbol${sortedPicks.length === 1 ? "" : "s"} tracked`}
                body="SEC filings, news momentum, and earnings windows behind today's signal changes."
              />
              <LauncherCard
                to="/strategies"
                eyebrow="Manage Strategies"
                title="How to express each idea"
                metric={
                  monthlyPremium != null && monthlyPremium > 0
                    ? `$${(monthlyPremium / 1000).toFixed(1)}k premium MTD`
                    : "Wheel · CC · CSP · LEAPS"
                }
                body="Match each signal to the right options structure. Track premium income and trade lifecycle."
                tone={monthlyPremium != null && monthlyPremium > 0 ? "good" : "default"}
              />
              <LauncherCard
                to="/portfolio"
                eyebrow="Review Portfolio Risk"
                title="Positions & exposure"
                metric={
                  riskCount > 0
                    ? `${riskCount} risk-flagged`
                    : "All clear"
                }
                body="Open positions, P&L, return %, sector and strategy exposure across every paper portfolio."
                tone={riskCount > 0 ? "warn" : "good"}
              />
            </section>
          </>
        )}

        {!loading && sortedPicks.length === 0 && (
          <div className="picks-empty-state" role="status">
            <span className="picks-empty-state-icon" aria-hidden="true">◌</span>
            <h2 className="picks-empty-state-title">
              Engine has no live signals
            </h2>
            <p className="picks-empty-state-body">
              The recommendation engine has not produced any results
              recently. Signals reappear after the next evaluation cycle —
              typically once per market session.
            </p>
            {freshAtDate && (
              <span className="picks-empty-state-meta">
                Last evaluation · {freshAtDate}
              </span>
            )}
          </div>
        )}

        <NextStepCard
          pathname="/overview"
          rationale={
            riskCount > 0
              // Phase 15b3 microcopy round 2 — Opus verbatim swap:
              //   was "${N} signal(s) flagged for risk — see what changed in catalysts first"
              //   now "${N} picks need a closer look — start with what changed today"
              ? `${riskCount} pick${riskCount === 1 ? "" : "s"} need a closer look — start with what changed today.`
              : undefined
          }
        />

        <footer className="picks-disclaimer">{RESEARCH_NOTE}</footer>
      </div>

      <PickModal pick={openPick} priceCache={openPrice} onClose={() => setOpenPickId(null)} />
    </div>
  );
}
