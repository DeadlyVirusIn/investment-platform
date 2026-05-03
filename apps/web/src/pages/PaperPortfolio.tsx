import Badge from '@/components/Badge';
import Card from '@/components/Card';
import EquityChart from '@/components/EquityChart';
import ErrorBoundary from '@/components/ErrorBoundary';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import Table, { type Column } from '@/components/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import {
  useBenchmarkPrices,
  usePaperEquity,
  usePaperPortfolio,
  usePaperPortfolios,
  usePaperTrades,
} from '@/lib/hooks';
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  formatRatio,
  formatSignedCurrency,
  formatSignedPercent,
  n,
  pnlToneClass,
} from '@/lib/format';
import { useSelectedPortfolio } from '@/lib/useSelectedPortfolio';
import type { Position, Trade } from '@/types';

const BENCHMARK_SYMBOL = 'SPY';

function MissingFieldCard({ fields }: { fields: string[] }) {
  if (fields.length === 0) return null;
  return (
    <Card title="Data incomplete" className="mb-4">
      <div className="text-sm text-text-secondary">
        Backend response is missing expected field(s):
      </div>
      <ul className="mt-2 list-disc pl-5 text-xs font-mono text-text-muted">
        {fields.map(f => <li key={f}>{f}</li>)}
      </ul>
    </Card>
  );
}

export default function PaperPortfolio() {
  return (
    <ErrorBoundary fallbackTitle="Mock Portfolio page crashed">
      <PaperPortfolioInner />
    </ErrorBoundary>
  );
}

function PaperPortfolioInner() {
  const portfoliosQ = usePaperPortfolios();
  const portfolios = portfoliosQ.data?.portfolios ?? [];
  const { activeId, setId } = useSelectedPortfolio(portfolios);

  const detailQ = usePaperPortfolio(activeId);
  const tradesQ = usePaperTrades(activeId, 200);
  const equityQ = usePaperEquity(activeId);

  // Derive benchmark date range from current equity curve so we only fetch
  // the relevant slice.
  const curve = equityQ.data?.curve ?? [];
  const firstSnap = curve[0]?.snapshot_date ?? null;
  const lastSnap = curve[curve.length - 1]?.snapshot_date ?? null;
  const benchmarkQ = useBenchmarkPrices(
    curve.length > 0 ? BENCHMARK_SYMBOL : null,
    { from: firstSnap, to: lastSnap },
  );

  if (portfoliosQ.isLoading) return <LoadingState />;
  if (portfoliosQ.error) return <ErrorState message={String(portfoliosQ.error)} />;

  if (portfolios.length === 0) {
    return (
      <>
        <PageHeader title="Mock Portfolio" />
        <Card title="No portfolio">
          <EmptyState title="No paper portfolio yet" />
        </Card>
      </>
    );
  }

  const detail = detailQ.data;
  const totalReturnPct = detail?.total_return_pct;
  const dd = detail?.validation?.drawdown;
  const conf = Array.isArray(detail?.validation?.confidence_validation)
    ? detail!.validation!.confidence_validation
    : [];
  const openPositions = Array.isArray(detail?.open_positions)
    ? detail!.open_positions
    : [];
  const trades = Array.isArray(tradesQ.data?.trades) ? tradesQ.data!.trades : [];

  // Defensive: enumerate missing expected fields so incomplete payloads get a
  // visible fallback card rather than causing a blank page.
  const missingFields: string[] = [];
  if (detail) {
    if (detail.total_equity == null) missingFields.push('total_equity');
    if (detail.cash == null) missingFields.push('cash');
    if (detail.validation == null) missingFields.push('validation');
    if (detail.open_positions === undefined) missingFields.push('open_positions');
  }

  return (
    <>
      <PageHeader
        title="Mock Portfolio"
        subtitle={detail?.name ? `${detail.name} · paper trading only` : undefined}
        actions={
          portfolios.length > 1 ? (
            <select
              value={activeId ?? ''}
              onChange={e => setId(e.target.value)}
              className="bg-surface-card border border-surface-border rounded-md text-sm px-3 py-1.5 text-text-primary"
            >
              {portfolios.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          ) : null
        }
      />

      {detailQ.isLoading && <LoadingState />}
      {detailQ.error && <ErrorState message={String(detailQ.error)} />}

      <MissingFieldCard fields={missingFields} />

      {detail && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <StatCard
              label="Total equity"
              value={formatCurrency(detail.total_equity)}
              secondary={
                totalReturnPct != null ? `${formatSignedPercent(totalReturnPct)} vs start` : undefined
              }
              tone={n(totalReturnPct) !== null && n(totalReturnPct)! >= 0 ? 'positive' : 'negative'}
            />
            <StatCard label="Cash" value={formatCurrency(detail.cash)} tone="muted" />
            <StatCard
              label="Unrealized P&L"
              value={formatSignedCurrency(detail.unrealized_pnl)}
              tone={n(detail.unrealized_pnl) !== null && n(detail.unrealized_pnl)! >= 0 ? 'positive' : 'negative'}
            />
            <StatCard
              label="Realized P&L"
              value={formatSignedCurrency(detail.realized_pnl_cumulative)}
              tone={n(detail.realized_pnl_cumulative) !== null && n(detail.realized_pnl_cumulative)! >= 0 ? 'positive' : 'negative'}
            />
            <StatCard
              label="Max drawdown"
              value={dd?.max_drawdown_pct ? formatSignedPercent(dd.max_drawdown_pct) : '—'}
              secondary={
                dd?.max_drawdown_duration_days != null
                  ? `${dd.max_drawdown_duration_days} days`
                  : undefined
              }
              tone="negative"
            />
          </div>

          <Card
            title="Equity curve"
            actions={<UpdatedLabel at={equityQ.dataUpdatedAt} />}
            className="mb-6"
          >
            {equityQ.isLoading ? (
              <LoadingState />
            ) : equityQ.error ? (
              <ErrorState message={String(equityQ.error)} />
            ) : curve.length === 0 ? (
              <EmptyState
                title="No snapshots yet"
                hint="Daily equity is captured by the run_paper_trading scheduler job."
              />
            ) : (
              <EquityChart
                points={curve}
                benchmark={benchmarkQ.data?.prices}
                benchmarkLabel={BENCHMARK_SYMBOL}
              />
            )}
          </Card>

          <Card
            title="Holdings"
            actions={<UpdatedLabel at={detailQ.dataUpdatedAt} />}
            contentClassName="p-0"
            className="mb-6"
          >
            <Table<Position>
              rows={openPositions}
              rowKey={r => r.position_id ?? `${r.symbol}-${r.asset_id}`}
              emptyLabel="No open positions"
              columns={HOLDINGS_COLUMNS}
            />
          </Card>

          <Card
            title="Confidence validation (closed trades)"
            actions={<UpdatedLabel at={detailQ.dataUpdatedAt} />}
            className="mb-6"
            contentClassName="p-0"
          >
            <Table
              rows={conf}
              rowKey={r => r.bucket ?? 'unknown'}
              emptyLabel="No closed trades yet"
              columns={[
                { key: 'b', label: 'Bucket', render: r => r.bucket },
                { key: 'count', label: 'Trades', align: 'right', render: r => r.count },
                {
                  key: 'w',
                  label: 'Wins / Losses',
                  align: 'right',
                  render: r => `${r.wins} / ${r.losses}`,
                },
                { key: 'hit', label: 'Hit rate', align: 'right', render: r => formatPercent(r.hit_rate) },
                {
                  key: 'pnl',
                  label: 'Avg realized',
                  align: 'right',
                  render: r => (
                    <span className={pnlToneClass(r.avg_realized_pnl)}>
                      {r.avg_realized_pnl ? formatSignedCurrency(r.avg_realized_pnl) : '—'}
                    </span>
                  ),
                },
              ]}
            />
          </Card>

          <Card
            title="Trade log"
            actions={<UpdatedLabel at={tradesQ.dataUpdatedAt} />}
            contentClassName="p-0"
          >
            {tradesQ.isLoading ? (
              <LoadingState />
            ) : tradesQ.error ? (
              <ErrorState message={String(tradesQ.error)} />
            ) : (
              <Table<Trade>
                rows={trades}
                rowKey={r => r.trade_id ?? `${r.symbol}-${r.fill_ts}`}
                emptyLabel="No trades yet"
                columns={TRADE_COLUMNS}
              />
            )}
          </Card>
        </>
      )}
    </>
  );
}

const HOLDINGS_COLUMNS: Column<Position>[] = [
  { key: 's', label: 'Symbol', render: r => <span className="font-medium">{r.symbol}</span> },
  { key: 'q', label: 'Quantity', align: 'right', render: r => formatRatio(r.quantity, 4) },
  { key: 'b', label: 'Avg cost', align: 'right', render: r => formatCurrency(r.avg_cost) },
  { key: 'l', label: 'Last price', align: 'right', render: r => formatCurrency(r.last_price) },
  { key: 'mv', label: 'Market value', align: 'right', render: r => formatCurrency(r.market_value) },
  {
    key: 'upl',
    label: 'Unrealized P&L',
    align: 'right',
    render: r => (
      <span className={pnlToneClass(r.unrealized_pnl)}>
        {formatSignedCurrency(r.unrealized_pnl)}
      </span>
    ),
  },
  { key: 'o', label: 'Opened', render: r => formatDateTime(r.opened_at) },
];

const TRADE_COLUMNS: Column<Trade>[] = [
  { key: 'ts', label: 'Fill time', render: r => formatDateTime(r.fill_ts) },
  { key: 's', label: 'Symbol', render: r => r.symbol },
  {
    key: 'side',
    label: 'Side',
    render: r => (
      <Badge tone={r.side === 'buy' ? 'positive' : 'negative'}>{r.side}</Badge>
    ),
  },
  { key: 'q', label: 'Qty', align: 'right', render: r => formatRatio(r.quantity, 4) },
  { key: 'px', label: 'Fill', align: 'right', render: r => formatCurrency(r.fill_price) },
  {
    key: 'pnl',
    label: 'Realized',
    align: 'right',
    render: r => (
      <span className={pnlToneClass(r.realized_pnl)}>
        {r.realized_pnl ? formatSignedCurrency(r.realized_pnl) : '—'}
      </span>
    ),
  },
  {
    key: 'reason',
    label: 'Reason',
    render: r => (
      <span className="text-text-muted text-xs">{r.reason ?? '—'}</span>
    ),
  },
];

// Expose Badge as a component import (referenced by tone in columns above).
export { Badge };
