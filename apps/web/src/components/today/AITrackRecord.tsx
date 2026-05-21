// AITrackRecord — journal-style "Since X: Y%. Largest decline: Z%."
//
// Rules:
//  - journal tone, not marketing
//  - no streaks
//  - no leaderboard feeling
//  - no "beat the market" claims
//  - portfolio numbers larger than track-record %, never the reverse
//  - shows max drawdown even when overall return is positive
//
// Source data: existing /api/performance/equity-curve series.

import { useMemo } from "react";

import { fmtPct, type EquityPoint } from "@/lib/portfolio/api";


export interface AITrackRecordProps {
  equity: EquityPoint[];
}


export default function AITrackRecord({ equity }: AITrackRecordProps) {

  const summary = useMemo(() => {
    if (!equity || equity.length < 2) return null;
    const first = equity[0]?.equity;
    const last = equity[equity.length - 1]?.equity;
    if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) {
      return null;
    }
    const sincePct = ((last - first) / first) * 100;
    let peak = first;
    let maxDrawdown = 0;
    for (const p of equity) {
      if (p.equity > peak) peak = p.equity;
      const dd = ((p.equity - peak) / peak) * 100;
      if (dd < maxDrawdown) maxDrawdown = dd;
    }
    return {
      sincePct,
      firstDate: equity[0]?.date ?? null,
      maxDrawdown,
    };
  }, [equity]);

  return (
    <section className="today-section" data-test="today-track-record">
      <p className="today-section-label">Track record</p>
      {summary ? (
        <p className="today-track-summary">
          <span className="today-track-period">Since </span>
          {summary.firstDate
            ? new Date(summary.firstDate).toLocaleDateString([], {
                month: "short", day: "numeric",
              })
            : "inception"}
          {": "}
          <span className="today-track-value">
            {fmtPct(summary.sincePct)}
          </span>
          {". "}
          <span className="today-track-period">Largest decline: </span>
          <span className="today-track-value">
            {fmtPct(summary.maxDrawdown)}
          </span>
          {"."}
        </p>
      ) : (
        <p className="today-empty">
          Track record will appear once the equity history accumulates.
        </p>
      )}
    </section>
  );
}
