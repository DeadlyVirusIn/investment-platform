import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Performance() {
  const perf = useQuery({
    queryKey: ['performance', { window: '30d' }],
    queryFn: () => apiGet<unknown>('/performance?window=30d'),
  });

  return (
    <div>
      <h1 className="page-title">Performance</h1>

      <section className="card max-w-2xl">
        <h2 className="text-sm font-medium text-text-secondary mb-3">
          30-Day Window
        </h2>
        {/* TODO Phase 1: window selector UI (7d / 30d / 90d / YTD / 1y) */}
        {perf.isLoading && (
          <p className="text-text-muted text-sm">Loading…</p>
        )}
        {perf.isError && (
          <p className="text-danger text-sm">
            {(perf.error as Error).message}
          </p>
        )}
        {perf.data !== undefined && (
          <pre className="text-xs text-text-secondary overflow-auto max-h-96">
            {JSON.stringify(perf.data, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
