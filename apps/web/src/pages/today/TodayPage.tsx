// TodayPage — calm premium investing mentor shell (PR-1, additive).
//
// Mounted at /today as a PARALLEL route. The existing /
// (PicksPage) is untouched. All operator surfaces (Decisions /
// Signal Lab / Alpha Lab / Ops / Agents / Diagnostics) are NOT
// reachable from this page's nav — only via direct URL.
//
// Hard locks (must hold):
//  - paper-only labels stay
//  - "Live estimate · delayed 15 min" wording stays
//  - "Official close · DATE" wording stays
//  - no AI-agency claims (Tier-A lint enforces)
//  - no real-time claims
//  - reasoning text must come from ReasoningCard (Phase L lock)
//
// All copy below is observational + lint-clean.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchCommandBar, fetchLiveNav, fetchEquityCurve,
  fmtCurrency, fmtPct, fmtSigned,
  type CommandBarData, type LiveNavData, type EquityPoint,
} from "@/lib/portfolio/api";
import { fetchPicks, type Pick } from "@/lib/picks/api";
import EquitySparkline from "@/components/portfolio/EquitySparkline";

import TodayNav from "@/components/today/TodayNav";
import WhatChangedCard from "@/components/today/WhatChangedCard";
import RecentMovesStrip from "@/components/today/RecentMovesStrip";
import AITrackRecord from "@/components/today/AITrackRecord";

import "./today.css";


// Read-only shape for executed-trades from /api/paper/executed/trades.
// Subset of fields we actually render.
interface ExecutedTrade {
  fill_ts: string | null;
  symbol: string | null;
  side: "buy" | "sell" | null;
  realized_pnl_dollars: number | null;
  return_pct: number | null;
  is_replay?: boolean | null;
  is_open?: boolean | null;
}


function greetingForHour(hour: number): string {
  if (hour < 5)  return "Hello tonight.";
  if (hour < 12) return "Good morning.";
  if (hour < 17) return "Good afternoon.";
  if (hour < 21) return "Good evening.";
  return "Hello tonight.";
}


// Observational AI-read sentence derived from canonical numerics.
// No agency claims. No emotional language. Tier-A lint-clean.
function aiReadSentence(c: CommandBarData | null): string {
  if (!c || c.totalNav == null) {
    return "Portfolio value pending the next refresh.";
  }
  const daily = c.dailyPnl;
  const totalPct = c.totalReturnPct;
  const dailyClause = daily == null
    ? null
    : daily > 0
      ? `up ${fmtSigned(daily)} today`
      : daily < 0
        ? `down ${fmtSigned(daily)} today`
        : "flat today";
  const inceptionClause = totalPct == null
    ? null
    : totalPct > 0
      ? `${fmtPct(totalPct)} since inception`
      : totalPct < 0
        ? `${fmtPct(totalPct)} since inception`
        : "flat since inception";
  const parts = [dailyClause, inceptionClause].filter(Boolean);
  if (parts.length === 0) return "Portfolio steady.";
  return `Portfolio is ${parts.join(" · ")}.`;
}


function pickTopOne(picks: Pick[]): Pick | null {
  if (!picks || picks.length === 0) return null;
  // Deterministic: highest adjusted_confidence on a Buy first;
  // otherwise highest confidence regardless of action.
  const score = (p: Pick): number => {
    const c = parseFloat(p.adjusted_confidence ?? p.confidence ?? "0");
    const pct = c > 1 ? c : c * 100;
    const action = p.adjusted_action ?? p.action;
    const bonus = action === "buy" ? 20 : action === "trim" || action === "sell" ? 10 : 0;
    return pct + bonus;
  };
  return [...picks].sort((a, b) => score(b) - score(a))[0] ?? null;
}


function actionLabel(a: string | null | undefined): string {
  switch ((a ?? "").toLowerCase()) {
    case "buy":  return "Buy";
    case "sell": return "Sell";
    case "trim": return "Trim";
    case "hold": return "Hold";
    default:     return "—";
  }
}


function formatAge(iso: string | null): string {
  if (!iso) return "";
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "";
  const days = Math.floor(ms / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}


// Static glossary term for PR-1. Rotating + full /learn route lands
// in PR-3. Pulled from the existing lib/novice/glossary catalog.
const LEARN_TERM = {
  term: "What does “Trim” mean?",
  body: (
    "Trim is a partial reduction of an open position. It appears when "
    + "momentum weakens but the thesis is still intact — the engine "
    + "is lowering exposure, not exiting outright."
  ),
};


// ---------------------------------------------------------------
// Component
// ---------------------------------------------------------------

interface OpenPositionLite {
  symbol: string | null;
  market_value?: number | null;
}


export default function TodayPage() {
  const [cmd, setCmd]     = useState<CommandBarData | null>(null);
  const [live, setLive]   = useState<LiveNavData | null>(null);
  const [picks, setPicks] = useState<Pick[]>([]);
  const [trades, setTrades] = useState<ExecutedTrade[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [openPositions, setOpenPositions] = useState<OpenPositionLite[]>([]);
  const [loading, setLoading] = useState(true);

  // Fetch all read-only data in parallel on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, l, p, tRes, eRes, posRes] = await Promise.all([
          fetchCommandBar(),
          fetchLiveNav(),
          fetchPicks(30),
          fetch("/api/paper/executed/trades")
            .then(r => r.ok ? r.json() : { trades: [] })
            .catch(() => ({ trades: [] })),
          fetchEquityCurve(),
          fetch("/api/paper/executed/positions?is_open=true")
            .then(r => r.ok ? r.json() : { positions: [] })
            .catch(() => ({ positions: [] })),
        ]);
        if (cancelled) return;
        setCmd(c);
        setLive(l);
        setPicks(p);
        setTrades(Array.isArray(tRes?.trades) ? tRes.trades : []);
        setEquity(eRes);
        setOpenPositions(Array.isArray(posRes?.positions) ? posRes.positions : []);
      } catch {
        // Honest absence — leave state as nulls.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    // Refresh live MTM every 30s when tab is visible (visibility gate
    // matches paper_live cache TTL).
    const interval = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      fetchLiveNav().then((l) => { if (!cancelled) setLive(l); });
    }, 30_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const greeting = useMemo(
    () => greetingForHour(new Date().getHours()),
    [],
  );
  const aiSentence = aiReadSentence(cmd);
  const topPick = pickTopOne(picks);

  // Live + official portfolio numbers
  const liveNav = live?.liveEstimatedNav;
  const liveAsOf = live?.pricesAsOfEpoch != null
    ? new Date(live.pricesAsOfEpoch * 1000)
    : null;
  const officialNav = cmd?.totalNav;
  const officialAsOf = cmd?.freshAt;

  // PR-3 moved the inline track-record + recent-moves logic into
  // dedicated components <AITrackRecord/> and <RecentMovesStrip/>.
  // The data they need still comes from `equity` + `trades` above.

  return (
    <div className="today-root">
      <TodayNav />

      <main className="today-page">
        {/* 1. Greeting + AI read */}
        <section className="today-section">
          <h1 className="today-greeting">{greeting}</h1>
          <p className="today-section-label">The AI read today</p>
          <p className="today-ai-read">{aiSentence}</p>
          {loading && (
            <p className="today-ai-meta">Loading the most recent data…</p>
          )}
        </section>

        {/* 2. Portfolio — minimal: one number + live line + official line */}
        <section className="today-section">
          <p className="today-section-label">Your paper portfolio</p>
          <div className="today-portfolio">
            <h2 className="today-nav-value">
              {liveNav != null
                ? fmtCurrency(liveNav, { compact: true })
                : officialNav != null
                  ? fmtCurrency(officialNav, { compact: true })
                  : "—"}
            </h2>
            {equity.length >= 2 && (
              <div className="today-portfolio-spark">
                <EquitySparkline points={equity.slice(-30)} height={28} />
              </div>
            )}
          </div>
          <div className="today-portfolio-lines">
            {liveNav != null && (
              <span className="today-portfolio-line">
                <strong>Live estimate:</strong>{" "}
                {fmtCurrency(liveNav)}
                {" · prices delayed 15 min"}
                {liveAsOf && (
                  <>
                    {" · as of "}
                    {liveAsOf.toLocaleTimeString([], {
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </>
                )}
              </span>
            )}
            {officialNav != null && (
              <span className="today-portfolio-line">
                <strong>Official close:</strong>{" "}
                {fmtCurrency(officialNav)}
                {officialAsOf && (
                  <>{" · "}{officialAsOf}</>
                )}
              </span>
            )}
          </div>
        </section>

        {/* 3. One thing to look at — reasoning FIRST, prices quiet */}
        <section className="today-section">
          <p className="today-section-label">One thing to look at</p>
          {topPick ? (
            <article className="today-onething"
                     data-test="today-onething"
                     aria-labelledby="today-onething-sym">
              <h3 id="today-onething-sym" className="today-onething-symbol">
                {topPick.symbol}
              </h3>
              {/* Reasoning first per amendment 3. We use the pick's
                  own short-form context. Full deterministic reasoning
                  from the backend envelope is reached via "See details".
                  For research-stage picks (no paper_trade), we render
                  a calm absence rather than frontend-authored prose. */}
              <p className="today-onething-reasoning">
                {topPick.thesis && topPick.thesis.length > 0
                  ? topPick.thesis
                  : "Reasoning is recorded once a trade is opened. " +
                    "Open the details to see the signal context."}
              </p>
              <span className="today-onething-signal"
                    data-action={(topPick.adjusted_action ?? topPick.action ?? "").toLowerCase()}>
                <span className="today-onething-signal-dot" />
                Signal:{" "}
                {actionLabel(topPick.adjusted_action ?? topPick.action)}
              </span>
              {(topPick.risk?.entry_price != null
                || topPick.risk?.target_price != null
                || topPick.risk?.stop_loss != null) && (
                <p className="today-onething-prices">
                  Reference:
                  {topPick.risk?.entry_price != null && (
                    <> entry {fmtCurrency(topPick.risk.entry_price)}</>
                  )}
                  {topPick.risk?.target_price != null && (
                    <> · target {fmtCurrency(topPick.risk.target_price)}</>
                  )}
                  {topPick.risk?.stop_loss != null && (
                    <> · stop {fmtCurrency(topPick.risk.stop_loss)}</>
                  )}
                </p>
              )}
              <Link
                to={`/today/pick/${topPick.symbol ?? ""}`}
                className="today-onething-cta"
              >
                See details &rarr;
              </Link>
            </article>
          ) : (
            <p className="today-empty">No signals matched today's filters.</p>
          )}
        </section>

        {/* 4. What changed recently — observational rows (PR-3) */}
        <WhatChangedCard
          trades={trades}
          openPositions={openPositions}
          totalNav={officialNav ?? null}
          liveNav={liveNav ?? null}
          optionsDormant={true}
        />

        {/* 5. AI's recent moves — 4-row journal strip (PR-3) */}
        <RecentMovesStrip trades={trades} max={4} />

        {/* 6. Track record summary — "Since X: Y%. Largest decline: Z%." (PR-3) */}
        <AITrackRecord equity={equity} />

        {/* 5. Learning card — strategic identity, not filler */}
        <section className="today-section">
          <div className="today-learn">
            <h3 className="today-learn-term">{LEARN_TERM.term}</h3>
            <p className="today-learn-def">{LEARN_TERM.body}</p>
            <Link to="/learn" className="today-learn-cta">
              More terms &rarr;
            </Link>
          </div>
        </section>

        {/* 6. Browse footer */}
        <nav className="today-browse" aria-label="Browse more">
          <Link to="/ideas">Ideas</Link>
          <span>·</span>
          <Link to="/portfolio">Holdings</Link>
          <span>·</span>
          <Link to="/learn">Learn</Link>
        </nav>

        {/* 7. Advanced expander (intentionally quiet) */}
        <details className="today-advanced">
          <summary>Advanced</summary>
          <ul>
            <li><Link to="/events">Events &amp; catalysts</Link></li>
            <li><Link to="/strategies">Strategies</Link></li>
            <li><Link to="/options">Options (preview)</Link></li>
            <li><Link to="/risk">Risk</Link></li>
            <li><Link to="/decisions">AI activity audit</Link></li>
          </ul>
        </details>
      </main>
    </div>
  );
}
