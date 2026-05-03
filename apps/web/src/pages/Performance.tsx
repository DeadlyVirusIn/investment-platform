import { useEffect, useMemo, useRef } from 'react';
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
} from 'lightweight-charts';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import Table, { type Column } from '@/components/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import DecisionQualityRibbon from '@/components/DecisionQualityRibbon';
import {
  useIntelligenceSummary,
  usePaperEquityCurve,
  usePnlByRegime,
  usePnlByScoreBucket,
  usePnlBySymbol,
  usePnlSummary,
} from '@/lib/hooks';
import {
  formatCurrency,
  formatPercent,
  formatRatio,
  formatSignedCurrency,
  n,
  pnlToneClass,
} from '@/lib/format';
import type {
  PaperEquityCurvePoint,
  PnlBucket,
  PnlBySymbolItem,
  PnlRegimeStat,
} from '@/types';

export default function Performance() {
  const summaryQ = usePnlSummary();
  const intelQ = useIntelligenceSummary();
  const bySymbolQ = usePnlBySymbol();
  const bucketQ = usePnlByScoreBucket();
  const regimeQ = usePnlByRegime();
  const curveQ = usePaperEquityCurve();

  if (summaryQ.isLoading) return <LoadingState />;
  if (summaryQ.error) return <ErrorState message={String(summaryQ.error)} />;

  const s = summaryQ.data;
  const symbols = bySymbolQ.data?.items ?? [];
  const buckets = bucketQ.data?.buckets ?? [];
  const regimes = regimeQ.data?.regimes ?? [];
  const curve = curveQ.data?.points ?? [];

  const tradesTotal = (s?.open_positions ?? 0) + (s?.closed_trades ?? 0);
  const smallSample = tradesTotal < 5;

  return (
    <>
      <PageHeader
        title="Performance"
        subtitle={
          s
            ? `Default Paper — ${s.open_positions} open / ${s.closed_trades} closed`
            : 'Default Paper'
        }
        actions={<UpdatedLabel at={summaryQ.dataUpdatedAt} />}
      />

      <DecisionQualityRibbon intelligence={intelQ.data} className="mb-4" />

      {smallSample && (
        <Card className="mb-6" contentClassName="px-5 py-4">
          <p className="text-xs text-text-muted">
            Sample size is small (&lt;5 trades). Metrics will stabilize as paper
            trading accumulates.
          </p>
        </Card>
      )}

      {/* Core stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="NAV"
          value={formatCurrency(s?.nav)}
        />
        <StatCard
          label="Cumulative PnL"
          value={formatSignedCurrency(s?.cumulative_pnl)}
          tone={
            n(s?.cumulative_pnl) !== null && n(s?.cumulative_pnl)! >= 0
              ? 'positive' : 'negative'
          }
        />
        <StatCard
          label="Unrealized PnL"
          value={formatSignedCurrency(s?.unrealized_pnl)}
          tone={
            n(s?.unrealized_pnl) !== null && n(s?.unrealized_pnl)! >= 0
              ? 'positive' : 'negative'
          }
        />
        <StatCard
          label="Realized PnL"
          value={formatSignedCurrency(s?.realized_pnl)}
          secondary={
            s ? `${s.wins}W · ${s.losses}L · ${s.breakeven}BE` : undefined
          }
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Win rate"
          value={formatPercent(s?.win_rate)}
          tone="muted"
        />
        <StatCard
          label="Avg win"
          value={formatSignedCurrency(s?.avg_win)}
          tone="muted"
        />
        <StatCard
          label="Avg loss"
          value={formatSignedCurrency(s?.avg_loss)}
          tone="muted"
        />
        <StatCard
          label="Daily PnL"
          value={formatSignedCurrency(s?.daily_pnl)}
          tone={
            n(s?.daily_pnl) !== null && n(s?.daily_pnl)! >= 0
              ? 'positive' : 'negative'
          }
        />
      </div>

      {/* Equity curve */}
      <Card title="Equity curve" className="mb-6" contentClassName="px-5 py-4">
        {curve.length < 2 ? (
          <EmptyState
            title="Equity curve not ready"
            hint="Need at least 2 equity snapshots. Rebalance once paper trades settle."
          />
        ) : (
          <PaperEquityChart points={curve} />
        )}
      </Card>

      {/* Per-symbol */}
      <Card
        title="Per-symbol PnL"
        className="mb-6"
        contentClassName="p-0"
      >
        {symbols.length === 0 ? (
          <EmptyState title="No trades yet" />
        ) : (
          <Table<PnlBySymbolItem>
            rows={symbols}
            rowKey={r => r.asset_id}
            columns={SYMBOL_COLUMNS}
          />
        )}
      </Card>

      {/* Attribution by score bucket */}
      <Card
        title="Attribution by entry composite score"
        className="mb-6"
        contentClassName="p-0"
      >
        {buckets.every(b => b.trade_count === 0) ? (
          <EmptyState
            title="No attribution yet"
            hint="Appears when paper trades accumulate with known entry composite scores."
          />
        ) : (
          <Table<PnlBucket>
            rows={buckets}
            rowKey={r => r.bucket}
            columns={BUCKET_COLUMNS}
          />
        )}
      </Card>

      {/* Attribution by regime */}
      <Card
        title="Attribution by regime at entry"
        contentClassName="p-0"
      >
        {regimes.every(r => r.trade_count === 0) ? (
          <EmptyState title="No regime attribution yet" />
        ) : (
          <Table<PnlRegimeStat>
            rows={regimes.filter(r => r.trade_count > 0)}
            rowKey={r => `${r.market_trend}-${r.vol_regime}`}
            columns={REGIME_COLUMNS}
          />
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// Equity chart (reused from prior Performance page)
// ---------------------------------------------------------------------------


function PaperEquityChart({ points }: { points: PaperEquityCurvePoint[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

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
      height: 260,
    });
    const series = chart.addLineSeries({
      color: '#4f7ef8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Equity',
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  const data = useMemo(
    () =>
      points
        .map(p => ({ time: p.date, value: parseFloat(p.equity) }))
        .filter(p => Number.isFinite(p.value)),
    [points],
  );

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(data);
    if (data.length > 0) chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} className="w-full" />;
}

// ---------------------------------------------------------------------------
// Columns
// ---------------------------------------------------------------------------


const SYMBOL_COLUMNS: Column<PnlBySymbolItem>[] = [
  {
    key: 's', label: 'Symbol',
    render: r => <span className="font-medium">{r.symbol ?? '—'}</span>,
  },
  {
    key: 'st', label: 'Status',
    render: r => <span className="text-xs capitalize">{r.status}</span>,
  },
  {
    key: 'q', label: 'Qty', align: 'right',
    render: r => formatRatio(r.quantity, 4),
  },
  {
    key: 'avg', label: 'Avg cost', align: 'right',
    render: r => formatCurrency(r.avg_cost),
  },
  {
    key: 'mk', label: 'Mark', align: 'right',
    render: r => formatCurrency(r.mark),
  },
  {
    key: 'rpl', label: 'Realized', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.realized_pnl)}>
        {formatSignedCurrency(r.realized_pnl)}
      </span>
    ),
  },
  {
    key: 'upl', label: 'Unrealized', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.unrealized_pnl)}>
        {formatSignedCurrency(r.unrealized_pnl)}
      </span>
    ),
  },
  {
    key: 'tpl', label: 'Total', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.total_pnl)}>
        {formatSignedCurrency(r.total_pnl)}
      </span>
    ),
  },
  {
    key: 'd', label: 'Holding', align: 'right',
    render: r => (r.holding_days != null ? `${r.holding_days}d` : '—'),
  },
  {
    key: 'es', label: 'Entry score', align: 'right',
    render: r => formatRatio(r.entry_composite_score, 3),
  },
  {
    key: 'er', label: 'Entry regime',
    render: r => (
      <span className="text-xs text-text-muted">
        {r.entry_market_trend ?? '—'} · {r.entry_vol_regime ?? '—'}
      </span>
    ),
  },
];

const BUCKET_COLUMNS: Column<PnlBucket>[] = [
  { key: 'b', label: 'Bucket', render: r => r.bucket },
  { key: 'n', label: 'Trades', align: 'right', render: r => r.trade_count },
  { key: 'w', label: 'Wins', align: 'right', render: r => r.wins },
  {
    key: 'rpl', label: 'Realized', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.realized_pnl)}>
        {formatSignedCurrency(r.realized_pnl)}
      </span>
    ),
  },
  {
    key: 'upl', label: 'Unrealized', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.unrealized_pnl)}>
        {formatSignedCurrency(r.unrealized_pnl)}
      </span>
    ),
  },
  {
    key: 't', label: 'Total', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.total_pnl)}>
        {formatSignedCurrency(r.total_pnl)}
      </span>
    ),
  },
  {
    key: 'avg', label: 'Avg / trade', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.avg_pnl_per_trade)}>
        {formatSignedCurrency(r.avg_pnl_per_trade)}
      </span>
    ),
  },
];

const REGIME_COLUMNS: Column<PnlRegimeStat>[] = [
  { key: 't', label: 'Trend', render: r => r.market_trend },
  { key: 'v', label: 'Vol', render: r => r.vol_regime },
  { key: 'n', label: 'Trades', align: 'right', render: r => r.trade_count },
  {
    key: 'rpl', label: 'Realized', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.realized_pnl)}>
        {formatSignedCurrency(r.realized_pnl)}
      </span>
    ),
  },
  {
    key: 'upl', label: 'Unrealized', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.unrealized_pnl)}>
        {formatSignedCurrency(r.unrealized_pnl)}
      </span>
    ),
  },
  {
    key: 't', label: 'Total', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.total_pnl)}>
        {formatSignedCurrency(r.total_pnl)}
      </span>
    ),
  },
  {
    key: 'avg', label: 'Avg / trade', align: 'right',
    render: r => (
      <span className={pnlToneClass(r.avg_pnl_per_trade)}>
        {formatSignedCurrency(r.avg_pnl_per_trade)}
      </span>
    ),
  },
];
