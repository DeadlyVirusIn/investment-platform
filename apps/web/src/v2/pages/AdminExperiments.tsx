// Experiment Lab — Wave 3A minimal owner surface (operate + verify only).
//
// Frontend gate: VITE_EXPERIMENT_LAB === '1' (default off; route absent
// otherwise). Server gate: /api/admin/experiments/* is owner-gated (404
// posture) AND mounted only when EXPERIMENT_LAB_ENABLED is on.
// Deliberately NOT the Comparison Arena: no winner banners, no promotion
// controls — promotion_readiness is a read-only verdict and owner
// approval stays a separate manual action. Labels are honest: measured /
// insufficient data / failed / not evaluated.

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { StatusPanel } from '../components/ui/StatusPanel';
import { apiGet } from '@/lib/api';

export function experimentLabEnabled(): boolean {
  return import.meta.env.VITE_EXPERIMENT_LAB === '1';
}

type RunHead = {
  run_uid: string; name: string; status: string; engine: string | null;
  data_start: string | null; data_end: string | null;
  n_folds: number | null; total_resolved: number | null;
  mean_hit_rate: number | null;
  net_mean_30d_expected_cost: number | null;
  calibration_reported: boolean;
  verdict: string | null;
  reproducibility: boolean | null;
  warnings: number;
  error_summary: string | null;
  created_at: string;
};

type Fold = {
  fold: string; candidates: number; resolved: number; censored: number;
  hit_rate: number | null; auc: number | null; brier: number | null;
  base_rate_brier: number | null; ece: number | null;
  mean_realized_30d: number | null;
};

type RunDetail = {
  run_uid: string; name: string; status: string; engine: string | null;
  seed: number | null; git_sha: string | null; split_method: string | null;
  parent_run_uid?: string | null;
  error_summary: string | null;
  metrics: {
    experiment_hash?: string; dataset_fingerprint?: string;
    dataset_manifest?: Record<string, unknown>;
    summary?: Record<string, unknown>;
    folds?: Fold[];
    skipped_folds?: { fold: string; reason: string }[];
    benchmarks?: Record<string, Record<string, unknown>>;
    cost_sensitivity?: Record<string, Record<string, unknown>>;
    warnings?: string[];
    metric_hash?: string;
    environment?: { python: string; packages: Record<string, string> };
    promotion_readiness?: {
      policy: string; verdict: string;
      gates: Record<string, { pass: boolean; detail: unknown }>;
    };
    reproducibility?: { matches: boolean; baseline_run: string };
  };
};

const VERDICT_META: Record<string, { color: string; hint: string }> = {
  ELIGIBLE_FOR_OWNER_REVIEW: {
    color: 'var(--brand)',
    hint: 'All lab-gates passed. Owner review is still a separate, manual decision.',
  },
  PASSES_BASELINE_WITH_LIMITATIONS: {
    color: 'oklch(0.70 0.14 75)', hint: 'Beats the baseline but with documented limitations.',
  },
  FAILS_BASELINE: {
    color: 'oklch(0.62 0.19 25)', hint: 'Does not beat the simple baseline.',
  },
  INSUFFICIENT_EVIDENCE: {
    color: 'var(--muted-foreground)', hint: 'Not enough resolved samples or temporal folds to claim anything.',
  },
  REPRODUCIBILITY_FAILED: {
    color: 'oklch(0.62 0.19 25)', hint: 'A re-run did not reproduce the recorded metrics.',
  },
};

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${(v * 100).toFixed(1)}%`;
}
function num(v: number | null | undefined, d = 3): string {
  return v == null ? '—' : v.toFixed(d);
}

export function AdminExperiments() {
  const [runs, setRuns] = useState<RunHead[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'denied' | 'error'>('loading');
  const [openUid, setOpenUid] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);

  const load = useCallback(() => {
    setState('loading');
    apiGet<{ runs: RunHead[] }>('/admin/experiments/runs')
      .then((r) => { setRuns(r.runs); setState('ready'); })
      .catch((e: { status?: number }) => setState(e?.status === 404 ? 'denied' : 'error'));
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!openUid) { setDetail(null); return; }
    setDetail(null);
    apiGet<RunDetail>(`/admin/experiments/runs/${openUid}`)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [openUid]);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <p className="text-meta ink-fainter mb-1 mt-8">ADMIN — OWNER-FACING</p>
      <h1 className="font-serif text-headline ink-primary mb-2">Experiment Lab</h1>
      <p className="ink-muted text-[13.5px] mb-6 max-w-narrative">
        Deterministic evaluation of recommendation engines against simple
        baselines on temporal out-of-sample windows. Every run is recorded
        immutably; nothing here promotes a model — verdicts are measured
        evidence, and approval stays a separate human decision.
      </p>

      {state === 'loading' && <p className="ink-fainter text-[13px]" role="status">Loading runs…</p>}
      {state === 'denied' && (
        <StatusPanel variant="info" title="This page is owner-only." role="status"
          action={<Link to="/discover" className="text-[12.5px] font-semibold" style={{ color: 'var(--brand)' }}>Back to Discover →</Link>}>
          The Experiment Lab is an operator surface (mounted only when the
          EXPERIMENT_LAB flag is on). Nothing is wrong with your account.
        </StatusPanel>
      )}
      {state === 'error' && (
        <StatusPanel variant="error" title="Couldn't load experiment runs." role="alert"
          action={<button type="button" onClick={load} className="px-3.5 py-1.5 rounded-full font-semibold" style={{ fontSize: 12.5, color: 'var(--brand-foreground)', backgroundColor: 'var(--brand)' }}>Try again</button>}>
          Runs live in the research registry on the server — nothing is lost.
        </StatusPanel>
      )}

      {state === 'ready' && runs.length === 0 && (
        <StatusPanel variant="info" title="No experiment runs yet.">
          Runs are created through the owner API
          (POST /api/admin/experiments/runs) with a bounded specification.
        </StatusPanel>
      )}

      {state === 'ready' && runs.length > 0 && (
        <ul className="space-y-3">
          {runs.map((r) => {
            const vm = r.verdict ? VERDICT_META[r.verdict] : null;
            const open = openUid === r.run_uid;
            return (
              <li key={r.run_uid} className="rounded-xl px-5 py-4" style={{
                border: '1px solid var(--border)',
                backgroundColor: 'color-mix(in oklch, var(--card) 60%, transparent)',
              }}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <h2 className="ink-primary text-[14px] font-semibold">{r.name.replace(/^lab: /, '')}</h2>
                    <p className="ink-fainter text-[11.5px] tabular-nums mt-0.5">
                      {r.run_uid} · {r.status} · {r.engine ?? '—'} · {r.data_start} → {r.data_end}
                    </p>
                  </div>
                  {r.status === 'failed' ? (
                    <span className="text-[11px] font-semibold uppercase" style={{ color: 'oklch(0.62 0.19 25)' }}>failed</span>
                  ) : vm ? (
                    <span title={vm.hint} className="text-[11px] font-semibold uppercase rounded-full px-2.5 py-0.5"
                      style={{ color: vm.color, border: `1px solid color-mix(in oklch, ${vm.color} 35%, transparent)` }}>
                      {r.verdict!.replace(/_/g, ' ')}
                    </span>
                  ) : (
                    <span className="ink-fainter text-[11px] uppercase">not evaluated</span>
                  )}
                </div>
                {r.status === 'failed' ? (
                  <p className="ink-muted text-[12px] mt-2">{r.error_summary}</p>
                ) : (
                  <p className="ink-muted text-[12px] mt-2 tabular-nums">
                    {r.n_folds ?? '—'} folds · {r.total_resolved ?? '—'} resolved ·
                    hit rate {pct(r.mean_hit_rate)} (measured) ·
                    net 30d at expected cost {pct(r.net_mean_30d_expected_cost)} ·
                    calibration {r.calibration_reported ? 'reported' : 'not evaluated'}
                    {r.reproducibility != null && ` · reproducibility ${r.reproducibility ? 'verified' : 'FAILED'}`}
                    {r.warnings > 0 && ` · ${r.warnings} warning${r.warnings === 1 ? '' : 's'}`}
                  </p>
                )}
                <button type="button" onClick={() => setOpenUid(open ? null : r.run_uid)}
                  aria-expanded={open}
                  className="text-[12px] font-semibold mt-2"
                  style={{ color: 'var(--brand)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
                  {open ? 'Hide detail' : 'Detail →'}
                </button>
                {open && detail && detail.run_uid === r.run_uid && (
                  <RunDetailView d={detail} />
                )}
                {open && !detail && <p className="ink-fainter text-[12px] mt-2" role="status">Loading detail…</p>}
              </li>
            );
          })}
        </ul>
      )}
    </ArthosPage>
  );
}

function RunDetailView({ d }: { d: RunDetail }) {
  const m = d.metrics ?? {};
  const folds = m.folds ?? [];
  const readiness = m.promotion_readiness;
  return (
    <div className="mt-3 space-y-3">
      {(m.warnings ?? []).map((w) => (
        <p key={w} className="text-[12px]" role="note" style={{ color: 'oklch(0.70 0.14 75)' }}>⚠ {w}</p>
      ))}

      {folds.length > 0 && (
        <div className="overflow-x-auto">
          <table className="text-[11.5px] tabular-nums w-full" aria-label="Fold metrics">
            <thead>
              <tr className="ink-fainter text-left">
                <th className="pr-3 font-medium">Fold</th><th className="pr-3 font-medium">Resolved</th>
                <th className="pr-3 font-medium">Censored</th><th className="pr-3 font-medium">Hit</th>
                <th className="pr-3 font-medium">AUC</th><th className="pr-3 font-medium">Brier</th>
                <th className="pr-3 font-medium">Base Brier</th><th className="pr-3 font-medium">ECE</th>
                <th className="pr-3 font-medium">30d ret</th>
              </tr>
            </thead>
            <tbody className="ink-muted">
              {folds.map((f) => (
                <tr key={f.fold}>
                  <td className="pr-3">{f.fold}</td><td className="pr-3">{f.resolved}</td>
                  <td className="pr-3">{f.censored}</td><td className="pr-3">{pct(f.hit_rate)}</td>
                  <td className="pr-3">{num(f.auc)}</td><td className="pr-3">{num(f.brier)}</td>
                  <td className="pr-3">{num(f.base_rate_brier)}</td><td className="pr-3">{num(f.ece)}</td>
                  <td className="pr-3">{pct(f.mean_realized_30d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(m.skipped_folds ?? []).length > 0 && (
        <p className="ink-fainter text-[11.5px]">
          Skipped folds: {(m.skipped_folds ?? []).map((s) => `${s.fold} (${s.reason})`).join(' · ')}
        </p>
      )}

      {m.benchmarks && (
        <p className="ink-muted text-[12px]">
          <strong className="ink-primary">Benchmarks (same universe/window):</strong>{' '}
          {Object.entries(m.benchmarks)
            .filter(([k]) => k !== 'matched_event_horizon')
            .map(([k, v]) => (
              <span key={k} className="mr-3 tabular-nums">
                {k}: {'error' in v ? String(v.error) : pct(v.total_return as number)}
              </span>
            ))}
        </p>
      )}
      {(() => {
        // Wave 3A.1 — the only return comparison on a COMPARABLE basis.
        const meb = m.benchmarks?.matched_event_horizon;
        if (!meb) return null;
        if ('error' in meb) {
          return <p className="ink-fainter text-[12px]">Matched event benchmark: {String(meb.error)}</p>;
        }
        return (
          <p className="ink-muted text-[12px] tabular-nums">
            <strong className="ink-primary">Matched event benchmark ({String(meb.basis)}):</strong>{' '}
            engine {pct(meb.engine_mean_30d as number)} vs asset {pct(meb.benchmark_mean_30d as number)} ·
            excess {pct(meb.excess_mean as number)} (median {pct(meb.excess_median as number)}) ·
            beats asset in {pct(meb.share_events_beating_asset as number)} of {String(meb.events)} events
            {Array.isArray(meb.share_beating_ci95) &&
              ` (CI95 ${pct(meb.share_beating_ci95[0] as number)}–${pct(meb.share_beating_ci95[1] as number)})`}
          </p>
        );
      })()}
      {m.cost_sensitivity && !('error' in m.cost_sensitivity) && (
        <p className="ink-muted text-[12px] tabular-nums">
          <strong className="ink-primary">Cost sensitivity (mean 30d):</strong>{' '}
          {Object.entries(m.cost_sensitivity).map(([k, v]) => (
            <span key={k} className="mr-3">{k}: {pct(v.net_mean_30d as number)}</span>
          ))}
        </p>
      )}

      {readiness && (
        <div>
          <p className="ink-primary text-[12.5px] font-semibold mb-1">
            Promotion readiness ({readiness.policy}) — read-only verdict
          </p>
          <ul className="space-y-0.5">
            {Object.entries(readiness.gates).map(([k, g]) => (
              <li key={k} className="ink-fainter text-[11.5px]">
                {g.pass ? '✓' : '✕'} {k} — {typeof g.detail === 'string' ? g.detail : JSON.stringify(g.detail)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="ink-fainter text-[11px] tabular-nums break-all">
        spec {m.experiment_hash?.slice(0, 16)}… · dataset {m.dataset_fingerprint?.slice(0, 16)}… ·
        metrics {m.metric_hash?.slice(0, 16)}… · seed {d.seed} · {d.split_method} ·
        python {m.environment?.python}
        {d.parent_run_uid && ` · reproduces ${d.parent_run_uid}`}
        {m.reproducibility && ` · reproducibility ${m.reproducibility.matches ? 'verified' : 'FAILED'} vs ${m.reproducibility.baseline_run}`}
      </p>
    </div>
  );
}
