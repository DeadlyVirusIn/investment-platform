import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Asset() {
  const { symbol } = useParams<{ symbol: string }>();

  const assetInfo = useQuery({
    queryKey: ['asset', symbol],
    queryFn: () => apiGet<unknown>(`/asset/${symbol}`),
    enabled: Boolean(symbol),
  });

  const prices = useQuery({
    queryKey: ['asset', symbol, 'prices'],
    queryFn: () => apiGet<unknown>(`/asset/${symbol}/prices`),
    enabled: Boolean(symbol),
  });

  return (
    <div>
      <h1 className="page-title">
        Asset:{' '}
        <span className="text-accent uppercase">{symbol ?? '—'}</span>
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="card">
          <h2 className="text-sm font-medium text-text-secondary mb-3">
            Asset Info
          </h2>
          {assetInfo.isLoading && (
            <p className="text-text-muted text-sm">Loading…</p>
          )}
          {assetInfo.isError && (
            <p className="text-danger text-sm">
              {(assetInfo.error as Error).message}
            </p>
          )}
          {assetInfo.data !== undefined && (
            <pre className="text-xs text-text-secondary overflow-auto max-h-64">
              {JSON.stringify(assetInfo.data, null, 2)}
            </pre>
          )}
        </section>

        <section className="card">
          <h2 className="text-sm font-medium text-text-secondary mb-3">
            Price History
          </h2>
          {/* TODO Phase 1: replace with Lightweight Charts candlestick */}
          {prices.isLoading && (
            <p className="text-text-muted text-sm">Loading…</p>
          )}
          {prices.isError && (
            <p className="text-danger text-sm">
              {(prices.error as Error).message}
            </p>
          )}
          {prices.data !== undefined && (
            <pre className="text-xs text-text-secondary overflow-auto max-h-64">
              {JSON.stringify(prices.data, null, 2)}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}
