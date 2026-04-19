import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Briefing() {
  const briefing = useQuery({
    queryKey: ['briefing', 'today'],
    queryFn: () => apiGet<unknown>('/briefing/today'),
  });

  return (
    <div>
      <h1 className="page-title">Daily Briefing</h1>

      <section className="card max-w-3xl">
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
          <pre className="text-xs text-text-secondary overflow-auto max-h-[32rem]">
            {JSON.stringify(briefing.data, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
