import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export default function Alerts() {
  const alerts = useQuery({
    queryKey: ['alerts'],
    queryFn: () => apiGet<unknown>('/alerts'),
  });

  return (
    <div>
      <h1 className="page-title">Alerts</h1>

      <section className="card max-w-2xl">
        <h2 className="text-sm font-medium text-text-secondary mb-3">
          Active Alerts
        </h2>
        {alerts.isLoading && (
          <p className="text-text-muted text-sm">Loading…</p>
        )}
        {alerts.isError && (
          <p className="text-danger text-sm">
            {(alerts.error as Error).message}
          </p>
        )}
        {alerts.data !== undefined && (
          <pre className="text-xs text-text-secondary overflow-auto max-h-96">
            {JSON.stringify(alerts.data, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
