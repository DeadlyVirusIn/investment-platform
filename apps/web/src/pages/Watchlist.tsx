import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Watchlist() {
  const watchlist = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => apiGet<unknown>('/watchlist'),
  });

  return (
    <div>
      <h1 className="page-title">Watchlist</h1>

      <section className="card max-w-2xl">
        <h2 className="text-sm font-medium text-text-secondary mb-3">
          Watched Symbols
        </h2>
        {watchlist.isLoading && (
          <p className="text-text-muted text-sm">Loading…</p>
        )}
        {watchlist.isError && (
          <p className="text-danger text-sm">
            {(watchlist.error as Error).message}
          </p>
        )}
        {watchlist.data !== undefined && (
          <pre className="text-xs text-text-secondary overflow-auto max-h-96">
            {JSON.stringify(watchlist.data, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
