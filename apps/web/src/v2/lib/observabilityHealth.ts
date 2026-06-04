// Shared pipeline-health derivation.
//
// Single source for the operational HEALTH signal, consumed by BOTH the
// Admin Observability page hero AND the top-strip HEALTH badge so the two
// surfaces can never disagree. Logic relocated verbatim from
// Observability.tsx — weights and thresholds unchanged.

import type { Observability } from './observability';

export type HealthTone = 'good' | 'warn' | 'bad' | 'muted';

export interface PipelineHealth {
  score: number;
  label: string;
  tone: HealthTone;
}

// Pipeline health score (0–100, derived only from real fields).
export function pipelineHealth(d: Observability): PipelineHealth {
  const known = d.freshness.matrix.filter((m) => m.status !== 'unknown');
  const freshFrac = known.length
    ? known.filter((m) => m.status === 'fresh').length / known.length
    : 1;
  const jobFrac = d.jobs.length
    ? 1 - d.failed_jobs_count / d.jobs.length
    : 1;
  const dbOk = d.db.head_matches ? 1 : 0;
  const workerOk =
    d.workers.tickloop_alive === true ? 1
      : d.workers.tickloop_alive === null ? 0.5 : 0;
  const canaryOk = d.canary.status === 'dormant' ? 1
    : d.canary.status === 'unknown' ? 0.5 : 0;
  const score = Math.round(
    100 * (0.4 * freshFrac + 0.25 * jobFrac + 0.15 * dbOk
      + 0.1 * workerOk + 0.1 * canaryOk),
  );
  const tone: HealthTone = score >= 85 ? 'good' : score >= 60 ? 'warn' : 'bad';
  const label = score >= 85 ? 'Healthy' : score >= 60 ? 'Degraded' : 'At risk';
  return { score, label, tone };
}
