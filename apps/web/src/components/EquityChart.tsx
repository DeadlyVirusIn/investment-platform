import { useEffect, useMemo, useRef } from 'react';
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
} from 'lightweight-charts';
import type { EquityPoint, PricePoint } from '@/types';

interface EquityChartProps {
  points: EquityPoint[];
  /** Optional daily price series for a benchmark (e.g. SPY). Normalized at
   * the chart level so both series start from the same equity value on the
   * first date present in ``points``. */
  benchmark?: PricePoint[];
  benchmarkLabel?: string;
  height?: number;
}

interface LineDatum {
  time: string;
  value: number;
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function dedupeAsc(rows: LineDatum[]): LineDatum[] {
  // lightweight-charts requires strictly ascending, unique `time`. Collapse
  // duplicates keeping the LAST value per day, then sort ascending.
  const byTime = new Map<string, number>();
  for (const r of rows) byTime.set(r.time, r.value);
  return Array.from(byTime.entries())
    .map(([time, value]) => ({ time, value }))
    .sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}

function buildPortfolioSeries(points: EquityPoint[]): LineDatum[] {
  const raw = points
    .filter(p => !!p.snapshot_date)
    .map(p => ({
      time: iso(new Date(p.snapshot_date!)),
      value: parseFloat(p.total_equity),
    }))
    .filter(p => Number.isFinite(p.value));
  return dedupeAsc(raw);
}

function buildNormalizedBenchmark(
  benchmark: PricePoint[],
  baseline: number,
  startDateIso: string,
): LineDatum[] {
  const first = benchmark.find(b => !!b.ts && iso(new Date(b.ts)) >= startDateIso);
  if (!first) return [];
  const firstPriceRaw = first.adjusted_close ?? first.close;
  const firstPrice = firstPriceRaw ? parseFloat(firstPriceRaw) : NaN;
  if (!Number.isFinite(firstPrice) || firstPrice <= 0) return [];

  const out: LineDatum[] = [];
  for (const bar of benchmark) {
    if (!bar.ts) continue;
    const d = iso(new Date(bar.ts));
    if (d < startDateIso) continue;
    const raw = bar.adjusted_close ?? bar.close;
    if (raw === null || raw === undefined) continue;
    const parsed = parseFloat(raw);
    if (!Number.isFinite(parsed)) continue;
    out.push({ time: d, value: (parsed / firstPrice) * baseline });
  }
  return dedupeAsc(out);
}

export default function EquityChart({
  points,
  benchmark,
  benchmarkLabel = 'SPY',
  height = 280,
}: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const portfolioSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const benchmarkSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8892a4',
        fontFamily:
          'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(42,51,71,0.5)', style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: '#2a3347' },
      timeScale: { borderColor: '#2a3347', timeVisible: false },
      crosshair: { mode: 1 },
      autoSize: true,
      height,
    });
    const portfolioSeries = chart.addLineSeries({
      color: '#4f7ef8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Portfolio',
    });
    const benchmarkSeries = chart.addLineSeries({
      color: '#8892a4',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: true,
      title: benchmarkLabel,
    });
    chartRef.current = chart;
    portfolioSeriesRef.current = portfolioSeries;
    benchmarkSeriesRef.current = benchmarkSeries;
    return () => {
      chart.remove();
      chartRef.current = null;
      portfolioSeriesRef.current = null;
      benchmarkSeriesRef.current = null;
    };
  }, [height, benchmarkLabel]);

  const portfolioData = useMemo(() => buildPortfolioSeries(points), [points]);

  const benchmarkData = useMemo(() => {
    if (!benchmark || benchmark.length === 0 || portfolioData.length === 0) {
      return [];
    }
    const baseline = portfolioData[0].value;
    const startIso = portfolioData[0].time;
    return buildNormalizedBenchmark(benchmark, baseline, startIso);
  }, [benchmark, portfolioData]);

  useEffect(() => {
    const portfolio = portfolioSeriesRef.current;
    const bench = benchmarkSeriesRef.current;
    if (!portfolio || !bench) return;
    portfolio.setData(portfolioData);
    bench.setData(benchmarkData);
    if (portfolioData.length > 0) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [portfolioData, benchmarkData]);

  return (
    <div>
      <div ref={containerRef} className="w-full" />
      <div className="flex items-center gap-4 mt-2 text-[11px] text-text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-[2px] w-6 rounded"
            style={{ backgroundColor: '#4f7ef8' }}
          />
          Paper Portfolio
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-[2px] w-6 rounded border-t border-dashed"
            style={{ borderColor: '#8892a4' }}
          />
          {benchmarkLabel} Benchmark
          {benchmark !== undefined && benchmarkData.length === 0 && (
            <span className="italic text-text-muted/80">— unavailable</span>
          )}
        </span>
      </div>
    </div>
  );
}
