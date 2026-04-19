import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Dashboard() {
  const summary = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: () => apiGet<unknown>('/portfolio/summary'),
  });

  const briefing = useQuery({
    queryKey: ['briefing', 'today'],
    queryFn: () => apiGet<unknown>('/briefing/today'),
  });

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="card">
          <h2 className="text-sm font-medium text-text-secondary mb-3">
            Portfolio Summary
          </h2>
          {summary.isLoading && (
            <p className="text-text-muted text-sm">Loading…</p>
          )}
          {summary.isError && (
            <p className="text-danger text-sm">
              {(summary.error as Error).message}
            </p>
          )}
          {summary.data !== undefined && (
            <pre className="text-xs text-text-secondary overflow-auto max-h-48">
              {JSON.stringify(summary.data, null, 2)}
            </pre>
          )}
        </section>

        <section className="card">
          <h2 className="text-sm font-medium text-text-secondary mb-3">
            Today's Briefing
          </h2>
          {briefing.isLoading && (
            <p className="text-text-muted text-sm">Loading…</p>
          )}
          {briefing.isError && (
            <p className="text-danger text-sm">
              {(briefing.error as Error).message}
            </p>
          )}
          {briefing.data !== undefined && (
            <pre className="text-xs text-text-secondary overflow-auto max-h-48">
              {JSON.stringify(briefing.data, null, 2)}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}
