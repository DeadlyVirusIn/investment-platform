import Badge from '@/components/Badge';
import Card from '@/components/Card';
import PageHeader from '@/components/PageHeader';
import ResearchJobHealthCard from '@/components/research/ResearchJobHealthCard';
import { ErrorState, LoadingState } from '@/components/States';
import UpdatedLabel from '@/components/UpdatedLabel';
import { useOpsStatus } from '@/lib/hooks';
import { formatDateTime } from '@/lib/format';
import type { OpsJob } from '@/types';

function statusTone(status: string | null): 'positive' | 'negative' | 'info' | 'muted' {
  if (status === 'success') return 'positive';
  if (status === 'error') return 'negative';
  if (status === 'running') return 'info';
  return 'muted';
}

function statusLabel(status: string | null): string {
  if (status === 'success') return 'Success';
  if (status === 'error') return 'Error';
  if (status === 'running') return 'Running';
  return 'Idle';
}

export default function JobsHealth() {
  const q = useOpsStatus();

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;

  const data = q.data;
  const jobs: OpsJob[] = Array.isArray(data?.jobs) ? (data!.jobs as OpsJob[]) : [];
  const counts = data?.counts ?? {};

  return (
    <>
      <PageHeader
        title="Jobs Health"
        subtitle={
          data?.checked_at
            ? `Scheduler ${data.scheduler_alive ? 'alive' : 'down'} · checked ${formatDateTime(
                data.checked_at,
              )}`
            : undefined
        }
        actions={<UpdatedLabel at={q.dataUpdatedAt} />}
      />

      {Object.keys(counts).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {Object.entries(counts).map(([k, v]) => (
            <Card key={k} contentClassName="px-5 py-3">
              <div className="text-[11px] font-semibold tracking-wider uppercase text-text-secondary">
                {k.replace(/_/g, ' ')}
              </div>
              <div className="mt-1 font-mono tabular-nums text-2xl text-text-primary">
                {typeof v === 'number' ? v : String(v)}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Card title="Scheduled jobs" contentClassName="p-0">
        {jobs.length === 0 ? (
          <div className="px-5 py-8 text-center text-text-muted text-sm">
            No scheduled jobs registered yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-border text-text-muted text-xs">
                  <th className="text-left py-2 px-4 font-medium">Job</th>
                  <th className="text-left py-2 px-4 font-medium">Cron</th>
                  <th className="text-left py-2 px-4 font-medium">Enabled</th>
                  <th className="text-left py-2 px-4 font-medium">Last status</th>
                  <th className="text-left py-2 px-4 font-medium">Last run</th>
                  <th className="text-left py-2 px-4 font-medium">Next run</th>
                  <th className="text-left py-2 px-4 font-medium">Duration</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr
                    key={job.name}
                    className="border-b border-surface-border/40 last:border-0"
                  >
                    <td className="py-2 px-4 text-text-primary font-mono text-xs">
                      {job.name}
                    </td>
                    <td className="py-2 px-4 text-text-muted font-mono text-xs">
                      {job.cron}
                    </td>
                    <td className="py-2 px-4">
                      {job.enabled ? (
                        <Badge tone="positive">On</Badge>
                      ) : (
                        <Badge tone="muted">Off</Badge>
                      )}
                    </td>
                    <td className="py-2 px-4">
                      <Badge tone={statusTone(job.last_status)}>
                        {statusLabel(job.last_status)}
                      </Badge>
                      {job.last_error && (
                        <div
                          className="mt-1 text-[11px] text-danger truncate max-w-[240px]"
                          title={job.last_error}
                        >
                          {job.last_error.slice(0, 120)}
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-4 text-text-muted text-xs">
                      {job.last_run_at ? formatDateTime(job.last_run_at) : '—'}
                    </td>
                    <td className="py-2 px-4 text-text-muted text-xs">
                      {job.next_run_at ? formatDateTime(job.next_run_at) : '—'}
                    </td>
                    <td className="py-2 px-4 text-text-muted font-mono text-xs">
                      {job.last_duration_seconds
                        ? `${parseFloat(job.last_duration_seconds).toFixed(2)}s`
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/*
        Phase 11W (Phase B) — Research Job Health card. Mounted only
        when VITE_RESEARCH_RO_ENABLED === 'true'. Phase B = static
        "subsystem disabled" notice.
      */}
      {import.meta.env.VITE_RESEARCH_RO_ENABLED === 'true' && (
        <div className="mt-4">
          <ResearchJobHealthCard />
        </div>
      )}
    </>
  );
}
