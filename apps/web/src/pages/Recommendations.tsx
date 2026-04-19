import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Recommendations() {
  const recs = useQuery({
    queryKey: ['recommendations', { active: true }],
    queryFn: () => apiGet<unknown>('/recommendations?active=true'),
  });

  return (
    <div>
      <h1 className="page-title">Recommendations</h1>

      <section className="card max-w-3xl">
        <h2 className="text-sm font-medium text-text-secondary mb-3">
          Active Recommendations
        </h2>
        {recs.isLoading && (
          <p className="text-text-muted text-sm">Loading…</p>
        )}
        {recs.isError && (
          <p className="text-danger text-sm">
            {(recs.error as Error).message}
          </p>
        )}
        {recs.data !== undefined && (
          <pre className="text-xs text-text-secondary overflow-auto max-h-[32rem]">
            {JSON.stringify(recs.data, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
