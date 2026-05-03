import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import { ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { formatCurrency, formatSignedPercent, pnlToneClass } from '@/lib/format';
import type { WatchlistResponse } from '@/types';

export default function Watchlist() {
  const qc = useQueryClient();
  const [input, setInput] = useState('');
  const [flash, setFlash] = useState<string | null>(null);

  const q = useQuery<WatchlistResponse>({
    queryKey: ['watchlist'],
    queryFn: () => apiGet<WatchlistResponse>('/watchlist'),
  });

  const addM = useMutation({
    mutationFn: (symbol: string) =>
      apiPost<{ symbol: string; created: boolean }>('/watchlist', { symbol }),
    onSuccess: data => {
      setInput('');
      setFlash(data.created ? `Added ${data.symbol}` : `${data.symbol} already on watchlist`);
      qc.invalidateQueries({ queryKey: ['watchlist'] });
    },
    onError: (err: unknown) => {
      setFlash(err instanceof Error ? err.message : 'Add failed');
    },
  });

  const removeM = useMutation({
    mutationFn: (symbol: string) =>
      apiDelete<{ symbol: string; removed: boolean }>(`/watchlist/${symbol}`),
    onSuccess: data => {
      setFlash(`Removed ${data.symbol}`);
      qc.invalidateQueries({ queryKey: ['watchlist'] });
    },
    onError: (err: unknown) => {
      setFlash(err instanceof Error ? err.message : 'Remove failed');
    },
  });

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;

  const items = q.data?.items ?? [];

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    addM.mutate(sym);
  }

  return (
    <>
      <PageHeader
        title="Watchlist"
        subtitle="Track symbols outside the active universe"
        actions={<UpdatedLabel at={q.dataUpdatedAt} />}
      />

      <Card className="mb-6" contentClassName="px-5 py-4">
        <form onSubmit={handleSubmit} className="flex items-center gap-3">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Add symbol (e.g. NVDA)"
            maxLength={16}
            className="flex-1 bg-surface-card border border-surface-border rounded-md text-sm px-3 py-1.5 text-text-primary font-mono uppercase"
          />
          <button
            type="submit"
            disabled={!input.trim() || addM.isPending}
            className="px-4 py-1.5 rounded-md text-sm bg-accent text-white hover:bg-accent/90 disabled:opacity-50"
          >
            {addM.isPending ? 'Adding…' : 'Add'}
          </button>
        </form>
        {flash && <div className="mt-2 text-xs text-text-muted">{flash}</div>}
      </Card>

      <Card title={`Symbols (${items.length})`} contentClassName="p-0">
        {items.length === 0 ? (
          <div className="px-5 py-8 text-center text-text-muted text-sm">
            No symbols on the watchlist yet.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-text-muted text-xs">
                <th className="text-left py-2 px-4 font-medium">Symbol</th>
                <th className="text-right py-2 px-4 font-medium">Last close</th>
                <th className="text-right py-2 px-4 font-medium">Change</th>
                <th className="text-left py-2 px-4 font-medium">Added</th>
                <th className="py-2 px-4 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.symbol} className="border-b border-surface-border/40 last:border-0">
                  <td className="py-2 px-4 font-medium">{it.symbol}</td>
                  <td className="py-2 px-4 text-right font-mono tabular-nums">
                    {formatCurrency(it.last_close)}
                  </td>
                  <td className={`py-2 px-4 text-right font-mono tabular-nums ${pnlToneClass(it.change_pct)}`}>
                    {formatSignedPercent(it.change_pct)}
                  </td>
                  <td className="py-2 px-4 text-xs text-text-muted">
                    {it.added_at ? it.added_at.slice(0, 10) : '—'}
                  </td>
                  <td className="py-2 px-4 text-right">
                    <button
                      onClick={() => removeM.mutate(it.symbol)}
                      disabled={removeM.isPending}
                      className="text-xs text-text-muted hover:text-danger transition-colors"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
