// RecentMovesStrip — 4-row "AI's recent moves" journal strip.
//
// Rules:
//  - max 4 rows
//  - plain-English row summaries (no AI agency)
//  - subtle symbol chips only
//  - tap (future) opens calm PickModal variant — wired in PR-4
//  - losses styled equal weight to gains (terracotta dot, same size)
//
// Source data: executed paper trades closed in recent history.

import { useMemo } from "react";

import { fmtPct, fmtSigned } from "@/lib/portfolio/api";


export interface RecentMoveLike {
  fill_ts: string | null;
  symbol: string | null;
  side: "buy" | "sell" | null;
  realized_pnl_dollars: number | null;
  return_pct: number | null;
}


export interface RecentMovesStripProps {
  trades: RecentMoveLike[];
  /** Defaults to 4. Hard cap per spec. */
  max?: number;
}


function ageLabel(iso: string | null): string {
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


export default function RecentMovesStrip({
  trades, max = 4,
}: RecentMovesStripProps) {

  const rows = useMemo(() => {
    return (trades || [])
      .filter(t => t.side === "sell"
                   && t.symbol
                   && t.fill_ts
                   && t.realized_pnl_dollars != null)
      .slice(0, max);
  }, [trades, max]);

  return (
    <section className="today-section" data-test="today-recent-moves">
      <p className="today-section-label">AI's recent moves</p>
      {rows.length === 0 ? (
        <p className="today-empty">
          Recent closed signals will appear here once trades close.
        </p>
      ) : (
        <ul className="today-moves-list">
          {rows.map((t, i) => {
            const pct = t.return_pct;
            const tone = pct == null ? "neutral"
              : pct > 0 ? "up" : pct < 0 ? "down" : "neutral";
            return (
              <li className="today-moves-row" key={i}>
                <span className="today-moves-when">{ageLabel(t.fill_ts)}</span>
                <span className="today-moves-symbol">{t.symbol}</span>
                <span className="today-moves-outcome" data-tone={tone}>
                  {pct != null ? fmtPct(pct) : "—"}
                  {t.realized_pnl_dollars != null && (
                    <>{" · "}{fmtSigned(t.realized_pnl_dollars)}</>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
