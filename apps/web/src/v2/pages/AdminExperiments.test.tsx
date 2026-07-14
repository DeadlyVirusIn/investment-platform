// Wave 3A — Experiment Lab minimal owner surface tests.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { AdminExperiments } from './AdminExperiments';

function runHead(over: Partial<Record<string, unknown>> = {}) {
  return {
    run_uid: 'rr_20260714_abc', name: 'lab: validation', status: 'completed',
    engine: 'stored_rules_engine', data_start: '2024-02-01', data_end: '2026-07-01',
    n_folds: 3, total_resolved: 2217, mean_hit_rate: 0.5787,
    net_mean_30d_expected_cost: 0.0282, calibration_reported: true,
    verdict: 'INSUFFICIENT_EVIDENCE', reproducibility: null, warnings: 0,
    error_summary: null, created_at: new Date().toISOString(),
    ...over,
  };
}

function detail(over: Partial<Record<string, unknown>> = {}) {
  return {
    run_uid: 'rr_20260714_abc', name: 'lab: validation', status: 'completed',
    engine: 'stored_rules_engine', seed: 42, git_sha: 'f5f619c',
    split_method: 'calendar-eval-1', error_summary: null,
    metrics: {
      experiment_hash: 'e'.repeat(64), dataset_fingerprint: 'd'.repeat(64),
      metric_hash: 'm'.repeat(64),
      summary: { n_folds: 3 },
      folds: [{
        fold: '2026-Q2', candidates: 1973, resolved: 1637, censored: 336,
        hit_rate: 0.561, auc: 0.5014, brier: 0.2504, base_rate_brier: 0.2463,
        ece: 0.0391, mean_realized_30d: 0.0822,
      }],
      skipped_folds: [{ fold: '2024-Q3', reason: 'resolved < 30' }],
      benchmarks: {
        buy_and_hold: { total_return: 1.1189 },
        momentum_12_1: { total_return: 1.118 },
        neutral: { total_return: 0 },
        matched_event_horizon: {
          basis: 'per-event 30d horizon, identical entry price, asset buy-and-hold comparator',
          events: 1812, engine_mean_30d: 0.0506, benchmark_mean_30d: 0.0488,
          excess_mean: 0.0018, excess_median: 0.0,
          share_events_beating_asset: 0.5204,
          share_beating_ci95: [0.4974, 0.5434],
        },
      },
      cost_sensitivity: {
        zero_cost: { net_mean_30d: 0.0292 },
        expected_cost: { net_mean_30d: 0.0282 },
        stressed_cost: { net_mean_30d: 0.0272 },
      },
      warnings: [],
      environment: { python: '3.12.0', packages: {} },
      promotion_readiness: {
        policy: 'lab-gates-1', verdict: 'INSUFFICIENT_EVIDENCE',
        gates: {
          min_temporal_folds: { pass: false, detail: '3 folds (need 4)' },
          beats_base_rate_majority: { pass: false, detail: '0/3 folds beat the base-rate Brier' },
        },
      },
    },
    ...over,
  };
}

function mockApi(list: unknown, det?: unknown, status = 200) {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = vi.fn().mockImplementation((url: string) => {
    const isDetail = /runs\/rr_/.test(String(url));
    return Promise.resolve({
      ok: status === 200, status, text: () => Promise.resolve(''),
      json: () => Promise.resolve(isDetail ? det : list),
    } as Response);
  });
}

afterEach(() => vi.restoreAllMocks());
const renderPage = () => render(<MemoryRouter><AdminExperiments /></MemoryRouter>);

describe('AdminExperiments', () => {
  it('empty state is honest, no diagnostics', async () => {
    mockApi({ runs: [] });
    renderPage();
    expect(await screen.findByText('No experiment runs yet.')).toBeInTheDocument();
  });

  it('completed run shows measured summary and verdict chip — never a winner banner', async () => {
    mockApi({ runs: [runHead()] });
    renderPage();
    expect(await screen.findByText('INSUFFICIENT EVIDENCE')).toBeInTheDocument();
    expect(screen.getByText(/hit rate 57.9% \(measured\)/)).toBeInTheDocument();
    expect(screen.getByText(/net 30d at expected cost 2.8%/)).toBeInTheDocument();
    expect(screen.getByText(/calibration reported/)).toBeInTheDocument();
    expect(screen.queryByText(/winner/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /promote/i })).not.toBeInTheDocument();
  });

  it('failed run shows bounded categorized error only', async () => {
    mockApi({ runs: [runHead({ status: 'failed', verdict: null, error_summary: 'dataset_empty: zero decisions in scope' })] });
    renderPage();
    expect(await screen.findByText('dataset_empty: zero decisions in scope')).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
  });

  it('detail expands to fold table, benchmarks, costs, gates', async () => {
    mockApi({ runs: [runHead()] }, detail());
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /detail/i }));
    const table = within(await screen.findByRole('table', { name: /fold metrics/i }));
    expect(table.getByText('2026-Q2')).toBeInTheDocument();
    expect(table.getByText('336')).toBeInTheDocument();       // censored
    expect(await screen.findByText(/Skipped folds: 2024-Q3/)).toBeInTheDocument();
    expect(screen.getByText(/Benchmarks \(same universe\/window\)/)).toBeInTheDocument();
    // Wave 3A.1 — matched comparable-basis line renders with CI
    expect(screen.getByText(/Matched event benchmark/)).toBeInTheDocument();
    expect(screen.getByText(/beats asset in 52.0% of 1812 events \(CI95 49.7%–54.3%\)/)).toBeInTheDocument();
    expect(screen.getByText(/read-only verdict/)).toBeInTheDocument();
    expect(screen.getByText(/0\/3 folds beat the base-rate Brier/)).toBeInTheDocument();
  });

  it('reproducibility failure is surfaced', async () => {
    mockApi({ runs: [runHead({ verdict: 'REPRODUCIBILITY_FAILED', reproducibility: false })] });
    renderPage();
    expect(await screen.findByText('REPRODUCIBILITY FAILED')).toBeInTheDocument();
    expect(screen.getByText(/reproducibility FAILED/)).toBeInTheDocument();
  });

  it('404 → owner-only posture; 500 → retry panel', async () => {
    mockApi({}, undefined, 404);
    renderPage();
    expect(await screen.findByText('This page is owner-only.')).toBeInTheDocument();
    vi.restoreAllMocks();
    mockApi({}, undefined, 500);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Couldn't load experiment runs.")).toBeInTheDocument());
  });
});
