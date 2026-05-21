// WhatChangedCard — Today section answering "what changed recently?"
//
// Observational rows only. No agency claims. No fabricated narration.
// Every row sources facts from existing backend data and renders
// honest absence when a fact is unknown.
//
// Hard locks (enforced by Tier-A forbidden-phrase lint):
//  - no AI agency verbs — anything that imputes thought to the engine
//  - no emotional market language ("panic / surge / collapse")
//  - no fake certainty (use "is at", not "will be")
//  - losses styled equal weight to gains
//
// Data source:
//  - executed paper trades (last 30 days for largest gain/loss; 7 days
//    for closed positions; 3 days for new entries)
//  - current open positions (top concentration as a % of total NAV)
//  - portfolio NAV (live + official) for estimate-gap row
//  - constant: options dormant note (until canary lifecycle proves)

import { useMemo } from "react";

import {
  fmtCurrency, fmtPct, fmtSigned,
} from "@/lib/portfolio/api";


// Read-only types — match the JSON shapes from existing endpoints.
export interface ExecutedTradeLike {
  fill_ts: string | null;
  symbol: string | null;
  side: "buy" | "sell" | null;
  realized_pnl_dollars: number | null;
  return_pct: number | null;
  is_replay?: boolean | null;
}

export interface OpenPositionLike {
  symbol: string | null;
  market_value?: number | null;
}

export interface WhatChangedCardProps {
  trades: ExecutedTradeLike[];
  openPositions: OpenPositionLike[];
  totalNav: number | null;          // official snapshot NAV (from /paper/summary)
  liveNav: number | null;           // live estimate (from /paper/live-nav)
  /** Optional: skip the options-dormant row when canary lifecycle activates. */
  optionsDormant?: boolean;
}


type Row = {
  text: string;
  ts: string | null;           // when this fact happened (newest first)
  tone?: "up" | "down" | "neutral";
};


function daysAgo(iso: string | null): string | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  const days = Math.floor(ms / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}


function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}


export default function WhatChangedCard({
  trades, openPositions, totalNav, liveNav, optionsDormant = true,
}: WhatChangedCardProps) {

  const rows: Row[] = useMemo(() => {
    const out: Row[] = [];
    const now = Date.now();
    const day = 86_400_000;

    const tradesArr = (trades || []).filter(t => t.fill_ts && t.symbol);

    // ---- 1. Closed positions in last 7d (sells with realized P&L) -----
    const closed = tradesArr
      .filter(t => t.side === "sell"
                   && t.fill_ts!
                   && (now - new Date(t.fill_ts!).getTime()) < (7 * day))
      .slice(0, 3);
    for (const t of closed) {
      const pct = t.return_pct;
      const tone: Row["tone"] = pct == null ? "neutral"
        : pct > 0 ? "up" : pct < 0 ? "down" : "neutral";
      const pctText = pct != null ? ` at ${fmtPct(pct)}` : "";
      out.push({
        text: `Closed ${t.symbol}${pctText} on ${fmtDate(t.fill_ts!)}.`,
        ts: t.fill_ts,
        tone,
      });
    }

    // ---- 2. New entries in last 3d (buys) -----------------------------
    const opened = tradesArr
      .filter(t => t.side === "buy"
                   && t.fill_ts!
                   && (now - new Date(t.fill_ts!).getTime()) < (3 * day))
      .slice(0, 2);
    for (const t of opened) {
      out.push({
        text: `Opened ${t.symbol} on ${fmtDate(t.fill_ts!)}.`,
        ts: t.fill_ts,
      });
    }

    // ---- 3. Largest realized gain in past 30d -------------------------
    const lastMonth = tradesArr
      .filter(t => t.side === "sell"
                   && t.fill_ts!
                   && (now - new Date(t.fill_ts!).getTime()) < (30 * day)
                   && t.realized_pnl_dollars != null);
    const maxGain = lastMonth
      .filter(t => (t.realized_pnl_dollars ?? 0) > 0)
      .sort((a, b) => (b.realized_pnl_dollars ?? 0) - (a.realized_pnl_dollars ?? 0))[0];
    if (maxGain && maxGain.realized_pnl_dollars != null) {
      out.push({
        text: `Largest gain in the past month: ${maxGain.symbol} `
              + `${fmtSigned(maxGain.realized_pnl_dollars)}.`,
        ts: maxGain.fill_ts,
        tone: "up",
      });
    }
    // ---- 4. Largest realized loss in past 30d -------------------------
    const maxLoss = lastMonth
      .filter(t => (t.realized_pnl_dollars ?? 0) < 0)
      .sort((a, b) => (a.realized_pnl_dollars ?? 0) - (b.realized_pnl_dollars ?? 0))[0];
    if (maxLoss && maxLoss.realized_pnl_dollars != null) {
      out.push({
        text: `Largest loss in the past month: ${maxLoss.symbol} `
              + `${fmtSigned(maxLoss.realized_pnl_dollars)}.`,
        ts: maxLoss.fill_ts,
        tone: "down",
      });
    }

    // ---- 5. Top concentration ----------------------------------------
    if (openPositions && openPositions.length > 0 && totalNav && totalNav > 0) {
      const top = [...openPositions]
        .filter(p => p.symbol && Number(p.market_value) > 0)
        .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0))[0];
      if (top && top.market_value != null) {
        const pct = (top.market_value / totalNav) * 100;
        if (pct >= 1.0) {
          out.push({
            text: `Top concentration: ${top.symbol} at `
                  + `${fmtPct(pct)} of portfolio.`,
            ts: null,
          });
        }
      }
    }

    // ---- 6. Portfolio estimate gap (live vs official) -----------------
    if (liveNav != null && totalNav != null) {
      const gap = liveNav - totalNav;
      // Only surface when the gap is meaningful — at least $100 or 0.1%
      const absRel = totalNav !== 0 ? Math.abs(gap / totalNav) : 0;
      if (Math.abs(gap) >= 100 && absRel >= 0.001) {
        const direction = gap >= 0 ? "above" : "below";
        out.push({
          text: `Today's portfolio estimate is `
                + `${fmtCurrency(Math.abs(gap))} ${direction} `
                + `the last official close.`,
          ts: null,
          tone: gap >= 0 ? "up" : "down",
        });
      }
    }

    // ---- 7. Options dormant note (constant until canary proves) -------
    if (optionsDormant) {
      out.push({
        text: "Options remain dormant — equities only for now.",
        ts: null,
      });
    }

    // Rank: rows with timestamps first (newest first), then constants
    return out.sort((a, b) => {
      if (a.ts && !b.ts) return -1;
      if (!a.ts && b.ts) return 1;
      if (a.ts && b.ts) {
        return new Date(b.ts).getTime() - new Date(a.ts).getTime();
      }
      return 0;
    }).slice(0, 6);
  }, [trades, openPositions, totalNav, liveNav, optionsDormant]);

  return (
    <section className="today-section" data-test="today-what-changed">
      <p className="today-section-label">What changed recently</p>
      {rows.length === 0 ? (
        <p className="today-empty">No notable changes since your last visit.</p>
      ) : (
        <ul className="today-changed-list">
          {rows.map((r, i) => (
            <li className="today-changed-row" key={i}>
              <span className="today-changed-text">{r.text}</span>
              {r.ts && (
                <span className="today-changed-when">{daysAgo(r.ts)}</span>
              )}
              {r.tone && (
                <span className="today-changed-dot"
                      data-tone={r.tone}
                      aria-hidden="true" />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
