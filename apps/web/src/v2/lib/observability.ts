// Admin Observability — types + read-only TanStack Query hook.
//
// Single source: GET /api/admin/observability (apps/api/src/api/
// admin_observability.py). Read-only; honest null/unknown values.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export type FreshStatus = 'fresh' | 'degraded' | 'stale' | 'unknown';
export type SystemStatus = 'healthy' | 'degraded' | 'failed' | 'unknown';
export type AlertSeverity = 'failed' | 'stale' | 'warning';

export interface ObsChannel {
  status: FreshStatus;
  as_of: string | null;
  last_run_id: string | null;
  message: string;
}

export interface ObsMatrixRow {
  key: string;
  label: string;
  latest: string | null;
  age_hours: number | null;
  age_human: string | null;
  expected_cadence_hours: number | null;
  status: FreshStatus;
  source: string;
}

export interface ObsJob {
  name: string;
  cron: string | null;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_duration_seconds: string | null;
  last_error: string | null;
}

export interface ObsAlert {
  severity: AlertSeverity;
  area: string;
  message: string;
}

export interface Observability {
  as_of: string;
  system_status: SystemStatus;
  api: {
    status: string;
    version: string | null;
    uptime_seconds: number | null;
  };
  db: {
    reachable: boolean;
    head: string | null;
    expected_head: string;
    head_matches: boolean | null;
    postmaster_start_time: string | null;
    uptime_seconds: number | null;
  };
  deploy: {
    app_version: string | null;
    git_sha: string | null;
    image_tag: string | null;
    build_time: string | null;
    db_head: string | null;
    expected_head: string;
  };
  workers: {
    tickloop_alive: boolean | null;
    last_job_run_at: string | null;
    note: string;
  };
  canary: {
    lifecycle_run_count: number | null;
    strategy_candidate_count: number | null;
    status: 'dormant' | 'active' | 'unknown';
  };
  freshness: {
    overall: FreshStatus;
    last_successful_cycle_at: string | null;
    channels: Record<string, ObsChannel>;
    matrix: ObsMatrixRow[];
    stale_count: number;
  };
  jobs: ObsJob[];
  failed_jobs_count: number;
  slowest_jobs: Array<{
    name: string;
    max_duration_seconds: number | null;
    avg_duration_seconds: number | null;
    last_run_at: string | null;
  }>;
  errors_24h: {
    failures: number | null;
    successes: number | null;
    total: number | null;
    failure_rate_pct: number | null;
  };
  market: {
    is_open: boolean;
    is_weekend: boolean;
    is_holiday: boolean | null;
    label: string;
  };
  db_connections: {
    active: number | null;
    idle: number | null;
    total: number | null;
    max_connections: number | null;
    utilization_pct: number | null;
    status: 'healthy' | 'warning' | 'critical' | 'unknown';
  };
  counts: {
    assets: number | null;
    price_bars: number | null;
    recommendations: number | null;
  };
  alerts: ObsAlert[];
}

export function useObservability() {
  return useQuery<Observability>({
    queryKey: ['admin', 'observability'],
    queryFn: () => apiGet<Observability>('/admin/observability'),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
