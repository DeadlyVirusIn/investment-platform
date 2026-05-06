// Phase UI-TERMINAL-LAYERS — Layer 3: regime heatmap strip.
// Last 30 market days, derived from trades list (entry regime with
// carry-forward), trade-fired dots, anomaly borders.

import { useMemo } from "react";
import { usePaperTrades, useAnomalies } from "@/lib/operator/hooks";
import type { Regime } from "@/lib/operator/types";
import { cn } from "@/lib/cn";
import { Label } from "@/components/ui/primitives";

const DAYS = 30;

interface Cell {
  date: string;
  regime: Regime | "unknown";
  hasTrade: boolean;
  hasAnomaly: boolean;
}

export default function RegimeHeatmap() {
  const { data: trades } = usePaperTrades();
  const { data: anomalies } = useAnomalies("open");

  const cells = useMemo<Cell[]>(() => {
    const tradesByDate = new Map<string, Regime>();
    for (const t of trades ?? []) {
      if (!tradesByDate.has(t.entry_date) && t.regime_at_entry) {
        tradesByDate.set(t.entry_date, t.regime_at_entry);
      }
    }
    const anomByDate = new Set((anomalies ?? []).map(a => a.as_of_date));

    // Anchor last available trade date; else today
    const sortedDates = [...tradesByDate.keys()].sort();
    const anchor = sortedDates.length > 0
      ? sortedDates[sortedDates.length - 1]
      : new Date().toISOString().slice(0, 10);
    const anchorDate = new Date(anchor);

    const out: Cell[] = [];
    let carry: Regime | "unknown" = "unknown";
    // Walk backwards DAYS market days (approx by calendar days then filter weekends)
    const raw: { date: string; weekday: number }[] = [];
    const cursor = new Date(anchorDate);
    while (raw.length < DAYS + 15) {
      const day = cursor.getUTCDay();
      if (day !== 0 && day !== 6) {
        raw.push({ date: cursor.toISOString().slice(0, 10), weekday: day });
      }
      cursor.setUTCDate(cursor.getUTCDate() - 1);
    }
    const window = raw.slice(0, DAYS).reverse();

    // Carry-forward from earliest observed regime
    // Find earliest carry candidate
    const sortedForwardsInWindow = [...window].map(w => w.date);
    for (const d of sortedForwardsInWindow) {
      if (tradesByDate.has(d)) { carry = tradesByDate.get(d)!; break; }
    }
    if (carry === "unknown" && sortedDates.length > 0) {
      carry = tradesByDate.get(sortedDates[0])!;
    }

    for (const w of window) {
      const dayRegime = tradesByDate.get(w.date);
      if (dayRegime) carry = dayRegime;
      out.push({
        date: w.date,
        regime: carry,
        hasTrade: tradesByDate.has(w.date),
        hasAnomaly: anomByDate.has(w.date),
      });
    }
    return out;
  }, [trades, anomalies]);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Regime memory · last {DAYS} days</Label>
          <div className="u-caption-2 mt-0.5">
            Green = directional · Red = stress · Gray = neutral ·
            {" "}dot = trade · ring = anomaly
          </div>
        </div>
        <div className="flex items-center gap-2">
          <LegendSwatch cls="is-directional" label="DIR" />
          <LegendSwatch cls="is-stress" label="STR" />
          <LegendSwatch cls="is-neutral" label="NEU" />
        </div>
      </div>
      <div className="u-regime-map">
        {cells.map(c => (
          <div key={c.date}
               title={`${c.date} · ${c.regime}${
                 c.hasTrade ? " · trade" : ""
               }${c.hasAnomaly ? " · anomaly" : ""}`}
               className={cn("u-regime-cell",
                 c.regime === "stress" ? "is-stress"
                 : c.regime === "directional" ? "is-directional"
                 : "is-neutral",
                 c.hasTrade && "has-trade",
                 c.hasAnomaly && "has-anomaly",
               )} />
        ))}
      </div>
    </div>
  );
}

function LegendSwatch({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 u-caption-2">
      <span className={cn("u-regime-cell", cls)}
            style={{ width: 10, height: 10, flex: "0 0 auto" }} />
      {label}
    </span>
  );
}
