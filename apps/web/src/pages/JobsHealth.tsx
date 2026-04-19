import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import FreshnessBadge, { type FreshnessStatus } from '@/components/FreshnessBadge';

interface JobStatus {
  name: string;
  status: FreshnessStatus;
  last_run?: string;
  next_run?: string;
  error?: string;
}

interface JobsHealthResponse {
  jobs: JobStatus[];
}

export default function JobsHealth() {
  const health = useQuery({
    queryKey: ['jobs', 'health'],
    queryFn: () => apiGet<JobsHealthResponse>('/jobs/health'),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <h1 className="page-title">Jobs Health</h1>

      {health.isLoading && (
        <p className="text-text-muted text-sm">Loading…</p>
      )}
      {health.isError && (
        <p className="text-danger text-sm">
          {(health.error as Error).message}
        </p>
      )}

      {health.data?.jobs && (
        <div className="card max-w-3xl">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-text-muted text-xs">
                <th className="text-left pb-2 font-medium">Job</th>
                <th className="text-left pb-2 font-medium">Status</th>
                <th className="text-left pb-2 font-medium">Last Run</th>
                <th className="text-left pb-2 font-medium">Next Run</th>
              </tr>
            </thead>
            <tbody>
              {health.data.jobs.map((job) => (
                <tr
                  key={job.name}
                  className="border-b border-surface-border/50 last:border-0"
                >
                  <td className="py-2 pr-4 text-text-primary font-mono text-xs">
                    {job.name}
                  </td>
                  <td className="py-2 pr-4">
                    <FreshnessBadge
                      status={job.status}
                      lastUpdated={job.last_run}
                    />
                  </td>
                  <td className="py-2 pr-4 text-text-muted text-xs">
                    {job.last_run
                      ? new Date(job.last_run).toLocaleString()
                      : '—'}
                  </td>
                  <td className="py-2 text-text-muted text-xs">
                    {job.next_run
                      ? new Date(job.next_run).toLocaleString()
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Raw fallback when shape doesn't match */}
      {health.data && !health.data.jobs && (
        <section className="card max-w-2xl">
          <pre className="text-xs text-text-secondary overflow-auto max-h-96">
            {JSON.stringify(health.data, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}
