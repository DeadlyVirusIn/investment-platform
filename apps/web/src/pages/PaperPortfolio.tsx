// Phase 11Z — legacy /legacy/paper-portfolio page.
//
// Reads executed trades + open positions from the account-path
// `/paper/executed/*` endpoints (paper_trade + paper_position) — NOT
// from `/paper/portfolios/:id/trades` which mixes replay rows in
// silently and from `paper_trade_log` (= 0). Includes:
//   * always-on live + replay split counts in the header strip
//   * "Show recovered replay data" toggle (default OFF)
//   * banner spelling out recovered counts when replay rows exist
//   * per-row "Recovered replay" warning chip on replay-tagged trades

import { useState } from 'react';
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
} from '@/lib/hooks';
import {
  useExecutedSummary,
  useExecutedTrades,
  type ExecutedTrade,
} from '@/lib/operator/hooks';
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
import type { Position } from '@/types';

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
  // Phase 11Z — toggle defaults OFF so live-only stays the headline.
  // Banner reveals when has_replay_recovered_rows=true.
  const [includeReplay, setIncludeReplay] = useState(false);
  const execSummaryQ = useExecutedSummary(includeReplay);
  const execTradesQ = useExecutedTrades(includeReplay, activeId);
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
  const trades: ExecutedTrade[] = execTradesQ.data?.trades ?? [];
  const execSummary = execSummaryQ.data;
  const liveTradesCount = execSummary?.live_trades_count ?? 0;
  const replayTradesCount = execSummary?.replay_trades_count ?? 0;
  const liveOpenPositions = execSummary?.live_open_positions_count ?? 0;
  const replayOpenPositions = execSummary?.replay_open_positions_count ?? 0;
  const hasReplayRecovered = !!execSummary?.has_replay_recovered_rows;

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

      {/* Phase 11Z — executed-trade strip (account path), always shown
          regardless of include_replay toggle. Live counts on the left,
          replay availability on the right. */}
      <div
        data-test="paper-portfolio-executed-strip"
        className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4"
      >
        <StatCard
          label="Live executed trades"
          value={String(liveTradesCount)}
          secondary={`paper_trade · live only`}
          tone="muted"
        />
        <StatCard
          label="Live open positions"
          value={String(liveOpenPositions)}
          secondary={`paper_position · live only`}
          tone="muted"
        />
        <StatCard
          label="Recovered replay trades"
          value={String(replayTradesCount)}
          secondary={
            hasReplayRecovered
              ? "available — not live"
              : "none recovered"
          }
          tone={replayTradesCount > 0 ? "negative" : "muted"}
        />
        <StatCard
          label="Recovered replay positions"
          value={String(replayOpenPositions)}
          secondary={
            hasReplayRecovered
              ? "available — not live"
              : "none recovered"
          }
          tone={replayOpenPositions > 0 ? "negative" : "muted"}
        />
      </div>

      {hasReplayRecovered && (
        <div
          data-test="paper-portfolio-replay-banner"
          className="mb-4 rounded-md border border-amber-700 bg-amber-900/20 px-3 py-2 text-sm text-zinc-200 flex items-center justify-between"
        >
          <div>
            <div className="font-semibold">
              Recovered replay rows present — NOT live trading activity
            </div>
            <div className="text-xs text-zinc-400 mt-1 leading-relaxed">
              <strong>{replayTradesCount}</strong> recovered replay trades and{' '}
              <strong>{replayOpenPositions}</strong> recovered open positions
              were rebuilt from the 2026-05-02 DB wipe via the
              execution-chain replay. Tagged in
              {' '}<code>replay_recovery_manifest</code>; excluded by default.
            </div>
          </div>
          <label className="text-xs flex items-center gap-2 ml-4 shrink-0">
            <input
              type="checkbox"
              checked={includeReplay}
              onChange={e => setIncludeReplay(e.target.checked)}
            />
            <span>Show recovered replay data</span>
          </label>
        </div>
      )}

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
            title={includeReplay
              ? "Trade log (live + recovered replay)"
              : "Trade log (live only)"}
            actions={<UpdatedLabel at={execTradesQ.dataUpdatedAt} />}
            contentClassName="p-0"
          >
            {execTradesQ.isLoading ? (
              <LoadingState />
            ) : execTradesQ.error ? (
              <ErrorState message={String(execTradesQ.error)} />
            ) : (
              <Table<ExecutedTrade>
                rows={trades}
                rowKey={r => r.trade_id ?? `${r.symbol}-${r.fill_ts ?? ''}`}
                emptyLabel={
                  includeReplay
                    ? "No trades (live or recovered replay)"
                    : hasReplayRecovered
                      ? "No live trades — toggle 'Show recovered replay data' above to see " + replayTradesCount + " recovered rows."
                      : "No trades yet"
                }
                columns={EXECUTED_TRADE_COLUMNS}
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

const EXECUTED_TRADE_COLUMNS: Column<ExecutedTrade>[] = [
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
        {r.realized_pnl != null ? formatSignedCurrency(r.realized_pnl) : '—'}
      </span>
    ),
  },
  {
    key: 'src',
    label: 'Source',
    render: r => (
      r.source === 'replay' || r.source === 'test'
        ? <Badge tone="negative">Recovered replay — not live trading activity</Badge>
        : <span className="text-text-muted text-xs">{r.source ?? 'live'}</span>
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
