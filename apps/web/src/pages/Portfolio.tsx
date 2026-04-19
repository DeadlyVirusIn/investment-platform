import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Portfolio() {
  const positions = useQuery({
    queryKey: ['portfolio', 'positions'],
    queryFn: () => apiGet<unknown>('/portfolio/positions'),
  });

  const pnl = useQuery({
    queryKey: ['portfolio', 'pnl'],
    queryFn: () => apiGet<unknown>('/portfolio/pnl'),
  });

  return (
    <div>
      <h1 className="page-title">Portfolio</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="card">
          <h2 className="text-sm font-medium text-text-secondary mb-3">
            Positions
          </h2>
          {positions.isLoading && (
            <p className="text-text-muted text-sm">Loading…</p>
          )}
          {positions.isError && (
            <p className="text-danger text-sm">
              {(positions.error as Error).message}
            </p>
          )}
          {positions.data !== undefined && (
            <pre className="text-xs text-text-secondary overflow-auto max-h-64">
              {JSON.stringify(positions.data, null, 2)}
            </pre>
          )}
        </section>

        <section className="card">
          <h2 className="text-sm font-medium text-text-secondary mb-3">
            P&amp;L
          </h2>
          {pnl.isLoading && (
            <p className="text-text-muted text-sm">Loading…</p>
          )}
          {pnl.isError && (
            <p className="text-danger text-sm">
              {(pnl.error as Error).message}
            </p>
          )}
          {pnl.data !== undefined && (
            <pre className="text-xs text-text-secondary overflow-auto max-h-64">
              {JSON.stringify(pnl.data, null, 2)}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}
