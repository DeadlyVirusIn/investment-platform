// Wave 2B — Mission Board rendering, postures, and truth rules.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { AdminResearchBoard } from './AdminResearchBoard';

const COLUMNS = [
  'queued', 'running', 'review_needed', 'delivered', 'corrected', 'stale', 'failed',
] as const;

function taskCard(over: Partial<Record<string, unknown>> = {}) {
  return {
    kind: 'task', card_id: `task:${over.task_id ?? 't1'}`, task_id: 't1',
    column: 'queued', title: 'NVDA supply chain', question_preview: 'What changed?',
    scope: null, task_status: 'open', schedule: { defined: false },
    is_follow_up: false, follow_up: null, latest_report: null, execution: null,
    chain: { versions: 0, prior_retained: 0, corrections: 0, current_version: null, current_status: null },
    freshness: 'unknown', freshness_reason: 'no report delivered yet',
    ...over,
  };
}

function board(over: Partial<Record<string, unknown>> = {},
  cardsByColumn: Partial<Record<string, unknown[]>> = {}) {
  return {
    rule_set_version: 'mission-board-1',
    generated_at: new Date().toISOString(),
    gateway_enabled: true,
    counts: Object.fromEntries(COLUMNS.map((k) => [k, (cardsByColumn[k] ?? []).length])),
    columns: COLUMNS.map((k) => ({
      key: k, title: k, help: `${k} help`, total: (cardsByColumn[k] ?? []).length,
      shown: (cardsByColumn[k] ?? []).length, overflow: 0,
      cards: cardsByColumn[k] ?? [],
    })),
    board_health: { complete: true, notes: [] },
    source_freshness: { newest_task_at: null, newest_report_at: null, newest_job_at: null },
    ...over,
  };
}

function mockApi(payload: unknown, status = 200) {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = vi.fn().mockResolvedValue({
    ok: status === 200, status,
    json: () => Promise.resolve(payload),
    text: () => Promise.resolve(''),
  } as Response);
}

afterEach(() => vi.restoreAllMocks());

function renderBoard() {
  return render(<MemoryRouter><AdminResearchBoard /></MemoryRouter>);
}

describe('AdminResearchBoard', () => {
  it('renders all seven columns with their explanations (desktop)', async () => {
    mockApi(board());
    renderBoard();
    for (const k of ['Queued', 'Running', 'Review needed', 'Delivered', 'Corrected', 'Stale', 'Failed']) {
      expect(await screen.findByRole('heading', { name: new RegExp(k, 'i') })).toBeInTheDocument();
    }
    expect(screen.getByText('stale help')).toBeInTheDocument();
    expect(screen.getByText('failed help')).toBeInTheDocument();
    expect(screen.getByText(/mission-board-1/)).toBeInTheDocument();
  });

  it('empty board shows calm empty states, no diagnostics', async () => {
    mockApi(board());
    renderBoard();
    const empties = await screen.findAllByText('Nothing here right now.');
    expect(empties).toHaveLength(7);
  });

  it('review-needed card links to the Inbox review action', async () => {
    mockApi(board({}, {
      review_needed: [taskCard({
        column: 'review_needed',
        latest_report: {
          report_id: 'r2', version: 2, review_status: 'pending',
          provenance: 'generated', generated_by_label: 'agent:researcher',
          delivered_at: new Date().toISOString(), citation_count: 3,
          review_age_days: 2,
        },
        chain: { versions: 2, prior_retained: 1, corrections: 1, current_version: 2, current_status: 'pending' },
        freshness: 'fresh',
      })],
    }));
    renderBoard();
    const col = within(await screen.findByRole('region', { name: /review needed column/i }));
    expect(col.getByRole('link', { name: /review in the inbox/i }))
      .toHaveAttribute('href', '/admin/research-inbox');
    // version-chain summary rendered
    expect(col.getByText(/1 earlier version retained/i)).toBeInTheDocument();
    expect(col.getByText(/v2 · pending · agent:researcher · 3 citations · waiting 2d/i)).toBeInTheDocument();
  });

  it('follow-up card carries the parent label; broken chain is safe', async () => {
    mockApi(board({}, {
      queued: [
        taskCard({
          card_id: 'task:f1', is_follow_up: true,
          follow_up: { available: true, parent_task_id: 'p', parent_title: 'Root question', depth: 1 },
        }),
        taskCard({
          card_id: 'task:f2', title: 'Cyclic one', is_follow_up: true,
          follow_up: { available: false, note: 'relationship unavailable (cycle detected)' },
        }),
      ],
    }));
    renderBoard();
    const label = await screen.findByText(/Follow-up to Root question/);
    expect(label.closest('p')?.textContent).toContain('source version was not recorded');
    expect(screen.getByText(/relationship unavailable \(cycle detected\)/)).toBeInTheDocument();
  });

  it('stale and failed cards surface their plain-English reasons', async () => {
    mockApi(board({}, {
      stale: [taskCard({
        card_id: 'task:s', column: 'stale', freshness: 'stale',
        freshness_reason: 'evidence observed 12d ago',
        latest_report: {
          report_id: 'r1', version: 1, review_status: 'approved',
          provenance: 'human', generated_by_label: 'owner',
          delivered_at: new Date().toISOString(), citation_count: 1,
          review_age_days: null,
        },
        chain: { versions: 1, prior_retained: 0, corrections: 0, current_version: 1, current_status: 'approved' },
      })],
      failed: [{
        kind: 'gateway_job', card_id: 'job:agj_1', column: 'failed',
        title: 'Gateway job — drift_report', job_uid: 'agj_1',
        job_type: 'drift_report', job_status: 'failed', token_prefix: 'arthos_a',
        task_link: null, queued_at: null, started_at: null,
        freshness: 'unknown', freshness_reason: 'ValueError: boom',
      }],
    }));
    renderBoard();
    expect(await screen.findByText('evidence observed 12d ago')).toBeInTheDocument();
    expect(screen.getByText(/Standalone historical gateway job/i)).toBeInTheDocument();
    expect(screen.getByText('ValueError: boom')).toBeInTheDocument();
  });

  it('gateway-disabled note renders and Running/Failed stay honest-empty', async () => {
    mockApi(board({
      gateway_enabled: false,
      board_health: {
        complete: false,
        notes: ['Agent Gateway is off — Running/Failed job activity is not shown (tasks are unaffected).'],
      },
    }));
    renderBoard();
    expect(await screen.findByText(/Agent Gateway is off/)).toBeInTheDocument();
    expect(screen.getByText(/Agent Gateway off/)).toBeInTheDocument();
  });

  it('summary counts come from the API counts', async () => {
    mockApi(board({}, {
      review_needed: [taskCard({ card_id: 'task:a', column: 'review_needed' })],
      queued: [taskCard({ card_id: 'task:b' }), taskCard({ card_id: 'task:c' })],
    }));
    renderBoard();
    const summary = within(await screen.findByRole('group', { name: /board summary/i }));
    expect(summary.getByText('3').closest('p')).toHaveTextContent('3 active');
    expect(summary.getByText(/review needed/).textContent).toContain('1');
  });

  it('mobile (~390px): segmented tabs, one column at a time, counts kept', async () => {
    const mql = (matches: boolean) => ({
      matches, media: '', addEventListener: vi.fn(), removeEventListener: vi.fn(),
    });
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(() => mql(true)));
    mockApi(board({}, {
      queued: [taskCard()],
      review_needed: [taskCard({ card_id: 'task:rn', column: 'review_needed', title: 'Needs eyes' })],
    }));
    renderBoard();
    const tabs = within(await screen.findByRole('group', { name: /choose a column/i }));
    expect(tabs.getByRole('button', { name: 'Queued (1)' })).toBeInTheDocument();
    // default tab is review_needed → its card is visible, queued card is not
    expect(screen.getByText('Needs eyes')).toBeInTheDocument();
    expect(screen.queryByText('NVDA supply chain')).not.toBeInTheDocument();
    fireEvent.click(tabs.getByRole('button', { name: 'Queued (1)' }));
    expect(screen.getByText('NVDA supply chain')).toBeInTheDocument();
    expect(tabs.getByRole('button', { name: 'Queued (1)' })).toHaveAttribute('aria-pressed', 'true');
    vi.unstubAllGlobals();
  });

  it('task-aware Running card shows execution summary, no standalone job card', async () => {
    mockApi(board({}, {
      running: [taskCard({
        column: 'running', title: 'Refresh in flight', freshness: 'fresh',
        execution: {
          attempts: 2, retries: 1, active_status: 'running',
          last_attempt_at: new Date().toISOString(), last_error: null,
          history_available: true,
        },
      })],
    }));
    renderBoard();
    const col = within(await screen.findByRole('region', { name: /running column/i }));
    expect(col.getByText('Refresh in flight')).toBeInTheDocument();
    expect(col.getByText(/2 runs \(1 retry\) · running now/)).toBeInTheDocument();
    expect(col.getByRole('button', { name: /execution history/i })).toBeInTheDocument();
    expect(col.queryByText(/standalone historical gateway job/i)).not.toBeInTheDocument();
  });

  it('task-aware Failed card carries the bounded failure reason', async () => {
    mockApi(board({}, {
      failed: [taskCard({
        column: 'failed', title: 'Broken run', freshness: 'unknown',
        freshness_reason: 'ValueError: boom',
        execution: {
          attempts: 1, retries: 0, active_status: null,
          last_attempt_at: new Date().toISOString(),
          last_error: 'ValueError: boom', history_available: true,
        },
      })],
    }));
    renderBoard();
    const col = within(await screen.findByRole('region', { name: /failed column/i }));
    expect(col.getByText('Broken run')).toBeInTheDocument();
    expect(col.getByText(/last failure: ValueError: boom/)).toBeInTheDocument();
  });

  it('execution history panel fetches and renders attempts on expand', async () => {
    const boardPayload = board({}, {
      running: [taskCard({
        column: 'running', title: 'With history',
        execution: {
          attempts: 2, retries: 1, active_status: 'running',
          last_attempt_at: new Date().toISOString(), last_error: null,
          history_available: true,
        },
      })],
    });
    const history = {
      task_id: 't1', total: 2, overflow: 0,
      attempts: [
        { attempt: 2, job_uid: 'agj2', job_type: 'drift_report', status: 'running', token_prefix: 'arthos_a', queued_at: new Date().toISOString(), started_at: null, finished_at: null, result_summary: null, error_summary: null, is_retry: true },
        { attempt: 1, job_uid: 'agj1', job_type: 'drift_report', status: 'failed', token_prefix: 'arthos_a', queued_at: new Date().toISOString(), started_at: null, finished_at: null, result_summary: null, error_summary: 'TimeoutError: slow', is_retry: false },
      ],
    };
    // @ts-expect-error -- fetch is a global in jsdom
    global.fetch = vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true, status: 200, text: () => Promise.resolve(''),
        json: () => Promise.resolve(
          String(url).includes('execution-history') ? history : boardPayload),
      } as Response));
    renderBoard();
    fireEvent.click(await screen.findByRole('button', { name: /execution history/i }));
    expect(await screen.findByText(/Attempt 2 \(retry\) · drift_report · running/)).toBeInTheDocument();
    expect(screen.getByText(/TimeoutError: slow/)).toBeInTheDocument();
  });

  it('follow-up cards show exact source version, superseded note, and fallback', async () => {
    mockApi(board({}, {
      queued: [
        taskCard({
          card_id: 'task:v2', title: 'From v2', is_follow_up: true,
          follow_up: { available: true, parent_title: 'Origin', depth: 1, source_version: 2, source_superseded: true },
        }),
        taskCard({
          card_id: 'task:norec', title: 'Historical', is_follow_up: true,
          follow_up: { available: true, parent_title: 'Origin', depth: 1, source_version: null, source_superseded: null },
        }),
      ],
    }));
    renderBoard();
    expect(await screen.findByText(/Follow-up to Origin — from v2 \(superseded — a newer version exists\)/)).toBeInTheDocument();
    expect(screen.getByText(/Follow-up to Origin — source version was not recorded/)).toBeInTheDocument();
  });

  it('standalone historical job card is labelled and never guessed onto a task', async () => {
    mockApi(board({}, {
      running: [{
        kind: 'gateway_job', card_id: 'job:agj_h', column: 'running',
        title: 'Gateway job — drift_report', job_uid: 'agj_h',
        job_type: 'drift_report', job_status: 'running', token_prefix: 'arthos_a',
        task_link: null, queued_at: null, started_at: null,
        freshness: 'fresh', freshness_reason: 'job is running',
      }],
    }));
    renderBoard();
    expect(await screen.findByText(/Standalone historical gateway job/)).toBeInTheDocument();
    expect(screen.getByText(/never guessed onto a task/)).toBeInTheDocument();
  });

  it('404 → owner-only posture; error → retry panel, no raw diagnostics', async () => {
    mockApi({}, 404);
    renderBoard();
    expect(await screen.findByText('This page is owner-only.')).toBeInTheDocument();

    mockApi({}, 500);
    renderBoard();
    expect(await screen.findByText("Couldn't load the board.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });
});
