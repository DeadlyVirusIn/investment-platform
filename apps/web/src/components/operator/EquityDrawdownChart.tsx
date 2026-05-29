// Elite terminal chart — 360 equity + 120 drawdown, 3px stroke with glow,
// gradient fill, near-invisible grid.

import { useEffect, useRef, useState } from "react";
import {
  createChart, IChartApi, ISeriesApi, LineStyle, LineType,
} from "lightweight-charts";
import { usePaperEquity, useCanonicalStockPortfolio } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

type ViewMode = "1M" | "3M" | "YTD" | "All";

// Client-derived per-point drawdown (%) from the equity series, running
// peak-to-trough. The chart no longer trusts the backend dd_pct field:
// it is computed here so a single source (the canonical equity curve)
// drives both the equity line and the drawdown, and so a future backend
// regression can never re-introduce a bogus drawdown into this surface.
function drawdownSeries(points: { equity: number }[]): number[] {
  let peak = points[0]?.equity ?? 0;
  return points.map((p) => {
    peak = Math.max(peak, p.equity);
    return peak > 0 ? ((p.equity - peak) / peak) * 100 : 0;
  });
}

export default function EquityDrawdownChart() {
  const [view, setView] = useState<ViewMode>("All");
  // F1: scope to the single canonical portfolio — never the all-portfolios
  // aggregate. Same source as the shell NAV / TrackRecord.
  const { data: book } = useCanonicalStockPortfolio();
  const { data, isLoading } = usePaperEquity(
    computeFrom(view), undefined, book?.portfolio_id,
  );
  const eqContainerRef = useRef<HTMLDivElement>(null);
  const ddContainerRef = useRef<HTMLDivElement>(null);
  const chartsRef = useRef<{
    eq?: IChartApi; dd?: IChartApi;
    eqSeries?: ISeriesApi<"Area">;
    ddSeries?: ISeriesApi<"Area">;
  }>({});
  // Phase 4 — watch html[data-theme] and rebuild charts on toggle.
  const [themeTick, setThemeTick] = useState(0);
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeTick(t => t + 1));
    obs.observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!data || !eqContainerRef.current || !ddContainerRef.current) return;
    // Theme changed → tear down and re-create with current vars.
    if (themeTick > 0 && chartsRef.current.eq) {
      try { chartsRef.current.eq.remove(); } catch {/*noop*/}
      try { chartsRef.current.dd?.remove(); } catch {/*noop*/}
      chartsRef.current = {};
    }

    // Phase 4 — read live CSS-var values so chart adapts to theme.
    const css = getComputedStyle(document.documentElement);
    const C = (k: string, fb: string) =>
      (css.getPropertyValue(k).trim() || fb);
    const T = {
      text:    C("--text-muted",     "#7A8499"),
      grid:    C("--border-subtle",  "rgba(255,255,255,0.06)"),
      border:  C("--border-subtle",  "rgba(255,255,255,0.06)"),
      accent:  C("--accent",         "#4B8BFF"),
      pos:     C("--chart-positive", "#26CA72"),
      neg:     C("--chart-negative", "#F25053"),
      surface: C("--surface-1",      "#1A2234"),
    };

    const commonOpts = {
      layout: {
        background: { color: "transparent" },
        textColor: T.text,
        fontFamily: "'JetBrains Mono', 'SF Mono', Menlo, monospace",
      },
      grid: {
        vertLines: { color: T.grid, style: LineStyle.Dotted },
        horzLines: { color: T.grid, style: LineStyle.Dotted },
      },
      timeScale: {
        borderColor: T.border,
        barSpacing: 4,
      },
      rightPriceScale: {
        borderColor: T.border,
      },
      crosshair: {
        mode: 1 as const,
        vertLine: { color: T.accent, width: 1 as 1,
                    style: LineStyle.Solid,
                    labelBackgroundColor: T.accent },
        horzLine: { color: T.accent, width: 1 as 1,
                    style: LineStyle.Solid,
                    labelBackgroundColor: T.accent },
      },
    };

    const lastEq = data[data.length - 1]?.equity ?? 0;
    const firstEq = data[0]?.equity ?? lastEq;
    const trendingUp = lastEq >= firstEq;

    // ----- Equity (area 360) -----
    if (!chartsRef.current.eq) {
      chartsRef.current.eq = createChart(eqContainerRef.current, {
        ...commonOpts, height: 360,
      });
    }
    const eqChart = chartsRef.current.eq!;
    if (chartsRef.current.eqSeries) {
      eqChart.removeSeries(chartsRef.current.eqSeries);
    }

    const eqColor = trendingUp ? T.pos : T.neg;
    const eqSeries = eqChart.addAreaSeries({
      lineColor: eqColor,
      topColor: trendingUp
        ? "rgba(38, 202, 114, 0.40)"
        : "rgba(242, 80, 83, 0.40)",
      bottomColor: trendingUp
        ? "rgba(38, 202, 114, 0.00)"
        : "rgba(242, 80, 83, 0.00)",
      lineWidth: 2,
      lineType: LineType.Simple,
      priceLineVisible: true,
      priceLineColor: trendingUp
        ? "rgba(38, 202, 114, 0.45)"
        : "rgba(242, 80, 83, 0.45)",
      priceLineStyle: LineStyle.Dashed,
      priceLineWidth: 1,
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: T.surface,
      crosshairMarkerBorderWidth: 2,
      crosshairMarkerBackgroundColor: eqColor,
      lastValueVisible: true,
    });
    eqSeries.setData(
      data.map(p => ({ time: p.date as unknown as string, value: p.equity })),
    );
    chartsRef.current.eqSeries = eqSeries;

    // ----- Drawdown (area 120) -----
    if (!chartsRef.current.dd) {
      chartsRef.current.dd = createChart(ddContainerRef.current, {
        ...commonOpts, height: 120,
        timeScale: { ...commonOpts.timeScale, visible: true },
      });
    }
    const ddChart = chartsRef.current.dd!;
    if (chartsRef.current.ddSeries) {
      ddChart.removeSeries(chartsRef.current.ddSeries);
    }
    const ddSeries = ddChart.addAreaSeries({
      lineColor: T.neg,
      topColor: "rgba(242, 80, 83, 0.50)",
      bottomColor: "rgba(242, 80, 83, 0.05)",
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderWidth: 2,
      crosshairMarkerBorderColor: "#0A0F1C",
      crosshairMarkerBackgroundColor: "#FF5A5D",
    });
    const ddVals = drawdownSeries(data);
    ddSeries.setData(
      data.map((p, i) => ({ time: p.date as unknown as string, value: ddVals[i] })),
    );
    chartsRef.current.ddSeries = ddSeries;

    eqChart.timeScale().fitContent();
    ddChart.timeScale().fitContent();

    const eqTs = eqChart.timeScale();
    const ddTs = ddChart.timeScale();
    const eqHandler = (r: unknown) =>
      r && ddTs.setVisibleLogicalRange(r as any);
    const ddHandler = (r: unknown) =>
      r && eqTs.setVisibleLogicalRange(r as any);
    eqTs.subscribeVisibleLogicalRangeChange(eqHandler);
    ddTs.subscribeVisibleLogicalRangeChange(ddHandler);

    return () => {
      eqTs.unsubscribeVisibleLogicalRangeChange(eqHandler);
      ddTs.unsubscribeVisibleLogicalRangeChange(ddHandler);
    };
  }, [data, themeTick]);

  useEffect(() => {
    return () => {
      chartsRef.current.eq?.remove();
      chartsRef.current.dd?.remove();
      chartsRef.current = {};
    };
  }, []);

  const last = data?.[data.length - 1];
  const first = data?.[0];
  const cumPct = last?.cum_pct ?? 0;
  const ddMin = data && data.length ? Math.min(...drawdownSeries(data)) : 0;
  const glowClass = first && last && last.equity < first.equity
    ? "u-chart-glow is-danger" : "u-chart-glow";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="u-label-sm">Equity Path</span>
          {first && last && (
            <span className={cn("u-mono-sm font-semibold",
              cumPct > 0 ? "text-success" : "text-danger")}>
              {cumPct > 0 ? "+" : ""}{cumPct.toFixed(2)}%
            </span>
          )}
          <span className="u-chip u-chip-neutral">
            MaxDD {ddMin.toFixed(2)}%
          </span>
        </div>
        <div className="flex gap-1">
          {(["1M", "3M", "YTD", "All"] as ViewMode[]).map(v => (
            <button key={v} onClick={() => setView(v)}
              className={cn(
                "u-mono-sm px-2.5 py-1 rounded border transition-colors",
                view === v ? "text-accent" : "text-fg-3 hover:text-fg-2",
              )}
              style={view === v
                ? { background: "var(--accent-subtle)",
                    borderColor: "rgba(75,139,255,0.4)" }
                : { background: "transparent",
                    borderColor: "var(--border-2)" }}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {isLoading && !data ? (
        <div className="h-[480px] bg-elev animate-pulse rounded-md" />
      ) : (
        <>
          <div ref={eqContainerRef} className={cn("w-full", glowClass)} />
          <div className="flex items-center justify-between pt-2 mb-1
                            border-t border-b1">
            <span className="u-label-sm">Drawdown · %</span>
            <span className="u-mono-sm text-danger">
              worst {ddMin.toFixed(2)}%
            </span>
          </div>
          <div ref={ddContainerRef} className="w-full" />
        </>
      )}
    </div>
  );
}

function computeFrom(view: ViewMode): string | undefined {
  const today = new Date();
  const d = new Date(today);
  switch (view) {
    case "1M": d.setMonth(d.getMonth() - 1); return d.toISOString().slice(0, 10);
    case "3M": d.setMonth(d.getMonth() - 3); return d.toISOString().slice(0, 10);
    case "YTD": return `${today.getFullYear()}-01-01`;
    case "All":
    default: return undefined;
  }
}
