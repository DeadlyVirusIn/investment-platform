import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import Table, { type Column } from '@/components/Table';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import { apiGet } from '@/lib/api';
import {
  formatCurrency,
  formatDateTime,
  formatRatio,
  formatSignedCurrency,
  n,
  pnlToneClass,
} from '@/lib/format';

interface LedgerPosition {
  symbol: string;
  asset_id: string;
  quantity: string;
  avg_cost_basis: string;
  total_cost_basis: string;
  last_price: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  lot_count: number;
}

interface LedgerPositionsResponse {
  account_id: string;
  positions: LedgerPosition[];
  count: number;
}

interface LedgerPnLResponse {
  account_id: string;
  realized_pnl: string;
  unrealized_pnl: string | null;
  total_market_value: string | null;
  total_cost_basis: string;
  position_count: number;
}

interface LedgerTransactionsResponse {
  account_id: string;
  transactions: Array<{
    id: string;
    symbol: string | null;
    ts: string | null;
    action: string;
    quantity: string | null;
    price: string | null;
    fees: string | null;
  }>;
  count: number;
}

export default function Portfolio() {
  const positionsQ = useQuery<LedgerPositionsResponse>({
    queryKey: ['portfolio', 'positions'],
    queryFn: () => apiGet<LedgerPositionsResponse>('/portfolio/positions'),
  });
  const pnlQ = useQuery<LedgerPnLResponse>({
    queryKey: ['portfolio', 'pnl'],
    queryFn: () => apiGet<LedgerPnLResponse>('/portfolio/pnl'),
  });
  const txnsQ = useQuery<LedgerTransactionsResponse>({
    queryKey: ['portfolio', 'transactions', 50],
    queryFn: () => apiGet<LedgerTransactionsResponse>('/portfolio/transactions?limit=50'),
  });

  if (positionsQ.isLoading || pnlQ.isLoading) return <LoadingState />;
  if (positionsQ.error) return <ErrorState message={String(positionsQ.error)} />;
  if (pnlQ.error) return <ErrorState message={String(pnlQ.error)} />;

  const positions = positionsQ.data?.positions ?? [];
  const pnl = pnlQ.data;
  const hasData = positions.length > 0;

  return (
    <>
      <PageHeader
        title="Portfolio (Ledger)"
        subtitle="Real holdings tracker. For the simulated account see Mock Portfolio."
        actions={<UpdatedLabel at={positionsQ.dataUpdatedAt} />}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Positions"
          value={pnl?.position_count ?? 0}
        />
        <StatCard
          label="Total market value"
          value={formatCurrency(pnl?.total_market_value)}
          tone="muted"
        />
        <StatCard
          label="Unrealized P&L"
          value={formatSignedCurrency(pnl?.unrealized_pnl)}
          tone={n(pnl?.unrealized_pnl) !== null && n(pnl?.unrealized_pnl)! >= 0 ? 'positive' : 'negative'}
        />
        <StatCard
          label="Realized P&L"
          value={formatSignedCurrency(pnl?.realized_pnl)}
          tone={n(pnl?.realized_pnl) !== null && n(pnl?.realized_pnl)! >= 0 ? 'positive' : 'negative'}
        />
      </div>

      <Card
        title="Holdings"
        actions={<UpdatedLabel at={positionsQ.dataUpdatedAt} />}
        contentClassName="p-0"
        className="mb-6"
      >
        {!hasData ? (
          <EmptyState
            title="No ledger holdings yet"
            hint={
              <>
                This page tracks your real-broker holdings via the ledger API.
                For the simulation, see{' '}
                <Link to="/paper-portfolio" className="text-accent hover:underline">
                  Mock Portfolio
                </Link>
                . Import broker CSV or POST to{' '}
                <code className="text-text-secondary">/api/portfolio/transactions</code>{' '}
                to populate.
              </>
            }
          />
        ) : (
          <Table<LedgerPosition>
            rows={positions}
            rowKey={r => r.asset_id}
            columns={HOLDINGS_COLUMNS}
          />
        )}
      </Card>

      <Card
        title="Recent transactions"
        actions={<UpdatedLabel at={txnsQ.dataUpdatedAt} />}
        contentClassName="p-0"
      >
        {(txnsQ.data?.transactions?.length ?? 0) === 0 ? (
          <EmptyState title="No transactions yet" />
        ) : (
          <Table
            rows={txnsQ.data!.transactions}
            rowKey={r => r.id}
            columns={[
              { key: 't', label: 'When', render: r => formatDateTime(r.ts) },
              { key: 's', label: 'Symbol', render: r => r.symbol ?? '—' },
              {
                key: 'a',
                label: 'Action',
                render: r => <span className="capitalize">{r.action}</span>,
              },
              { key: 'q', label: 'Qty', align: 'right', render: r => formatRatio(r.quantity, 4) },
              { key: 'p', label: 'Price', align: 'right', render: r => formatCurrency(r.price) },
            ]}
          />
        )}
      </Card>
    </>
  );
}

const HOLDINGS_COLUMNS: Column<LedgerPosition>[] = [
  { key: 's', label: 'Symbol', render: r => <span className="font-medium">{r.symbol}</span> },
  { key: 'q', label: 'Quantity', align: 'right', render: r => formatRatio(r.quantity, 4) },
  { key: 'b', label: 'Avg cost', align: 'right', render: r => formatCurrency(r.avg_cost_basis) },
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
  { key: 'lots', label: 'Lots', align: 'right', render: r => r.lot_count },
];
