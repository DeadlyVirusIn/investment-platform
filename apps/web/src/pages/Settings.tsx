import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import { ErrorState, LoadingState } from '@/components/States';
import { apiGet, apiPatch } from '@/lib/api';
import type { AppSettings } from '@/types';

type PatchPayload = Partial<{
  benchmark_symbol: string;
  default_portfolio_name: string;
  data_refresh_enabled: boolean;
  tiingo_api_key_override: string;
}>;

export default function Settings() {
  const qc = useQueryClient();
  const q = useQuery<AppSettings>({
    queryKey: ['settings'],
    queryFn: () => apiGet<AppSettings>('/settings'),
  });

  const [benchmark, setBenchmark] = useState('SPY');
  const [portfolioName, setPortfolioName] = useState('Default Paper');
  const [refresh, setRefresh] = useState(true);
  const [tiingoOverride, setTiingoOverride] = useState('');
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    if (q.data) {
      setBenchmark(q.data.benchmark_symbol);
      setPortfolioName(q.data.default_portfolio_name);
      setRefresh(q.data.data_refresh_enabled);
      setTiingoOverride('');
    }
  }, [q.data]);

  const save = useMutation({
    mutationFn: (patch: PatchPayload) =>
      apiPatch<{ ok: boolean; updated_keys: string[] }>('/settings', patch),
    onSuccess: data => {
      setFlash(
        data.updated_keys.length > 0
          ? `Saved: ${data.updated_keys.join(', ')}`
          : 'Nothing changed',
      );
      qc.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: (err: unknown) => {
      setFlash(err instanceof Error ? err.message : 'Save failed');
    },
  });

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const patch: PatchPayload = {};
    if (q.data) {
      if (benchmark !== q.data.benchmark_symbol) patch.benchmark_symbol = benchmark;
      if (portfolioName !== q.data.default_portfolio_name)
        patch.default_portfolio_name = portfolioName;
      if (refresh !== q.data.data_refresh_enabled)
        patch.data_refresh_enabled = refresh;
      if (tiingoOverride) patch.tiingo_api_key_override = tiingoOverride;
    }
    if (Object.keys(patch).length === 0) {
      setFlash('Nothing to save');
      return;
    }
    save.mutate(patch);
  }

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Minimal config persisted to the database"
      />

      <Card contentClassName="px-5 py-4">
        <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
          <Field label="Benchmark symbol">
            <input
              type="text"
              value={benchmark}
              onChange={e => setBenchmark(e.target.value.toUpperCase())}
              maxLength={16}
              className="w-full bg-surface-card border border-surface-border rounded-md text-sm px-3 py-1.5 text-text-primary font-mono uppercase"
            />
          </Field>

          <Field label="Default portfolio name">
            <input
              type="text"
              value={portfolioName}
              onChange={e => setPortfolioName(e.target.value)}
              maxLength={64}
              className="w-full bg-surface-card border border-surface-border rounded-md text-sm px-3 py-1.5 text-text-primary"
            />
          </Field>

          <Field label="Data refresh (scheduler)">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={refresh}
                onChange={e => setRefresh(e.target.checked)}
                className="accent-accent"
              />
              Enabled
            </label>
          </Field>

          <Field
            label="Tiingo API key override"
            hint={
              q.data?.tiingo_api_key_override_present
                ? `Current: ${q.data.tiingo_api_key_override_masked} (leave blank to keep)`
                : 'No override set — .env value is used'
            }
          >
            <input
              type="password"
              value={tiingoOverride}
              onChange={e => setTiingoOverride(e.target.value)}
              placeholder="paste new key to override"
              maxLength={128}
              className="w-full bg-surface-card border border-surface-border rounded-md text-sm px-3 py-1.5 text-text-primary font-mono"
            />
          </Field>

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={save.isPending}
              className="px-4 py-1.5 rounded-md text-sm bg-accent text-white hover:bg-accent/90 disabled:opacity-50"
            >
              {save.isPending ? 'Saving…' : 'Save settings'}
            </button>
            {flash && <span className="text-xs text-text-muted">{flash}</span>}
          </div>
        </form>
      </Card>
    </>
  );
}

function Field({
  label, hint, children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold tracking-wider uppercase text-text-secondary mb-1">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </div>
  );
}
