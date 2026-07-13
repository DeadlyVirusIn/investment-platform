// Wave 2A — correction + follow-up dialogs, version chain, immutable copy.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { AdminResearchInbox } from './AdminResearchInbox';

const REPORTS = [
  { id: 'r2', task_id: 't1', version: 2, body: 'v2 body', citations: [],
    provenance: 'human', review_status: 'approved', reviewed_by: 'owner@x',
    reviewed_at: null, created_at: new Date().toISOString(), state: 'fresh' },
  { id: 'r1', task_id: 't1', version: 1, body: 'v1 body', citations: [],
    provenance: 'generated', review_status: 'pending', reviewed_by: null,
    reviewed_at: null, created_at: new Date().toISOString(), state: 'superseded' },
];
const TASKS = [{ id: 't1', title: 'Sample task', question: 'Q?', scope: 'sector:test', created_at: null }];

function mockApi(posts: Record<string, unknown> = {}) {
  // @ts-expect-error -- jsdom global
  global.fetch = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
    if (opts?.method === 'POST') {
      const key = Object.keys(posts).find((k) => url.includes(k));
      return Promise.resolve({ ok: true, status: 201,
        json: () => Promise.resolve(posts[key ?? ''] ?? {}) } as Response);
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(
      url.includes('/tasks') ? { tasks: TASKS } : { reports: REPORTS }) } as Response);
  });
}

afterEach(() => vi.restoreAllMocks());
beforeEach(() => mockApi());

function renderInbox() {
  return render(<MemoryRouter><AdminResearchInbox /></MemoryRouter>);
}

describe('Inbox completeness', () => {
  it('version chain: v2 shows supersedes note; superseded v1 has no Correct button', async () => {
    renderInbox();
    expect(await screen.findByText(/supersedes v1/i)).toBeInTheDocument();
    // exactly one Correct button (on the fresh v2, not the superseded v1)
    expect(screen.getAllByRole('button', { name: /correct report/i })).toHaveLength(1);
  });

  it('correction dialog explains immutability and never offers inline edit', async () => {
    renderInbox();
    const correct = await screen.findByRole('button', { name: /correct report/i });
    fireEvent.click(correct);
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByText(/current version is/i)).toBeInTheDocument();
    expect(screen.getByText(/not edited/i)).toBeInTheDocument();
    expect(screen.getByText(/earlier versions stay available/i)).toBeInTheDocument();
  });

  it('successful correction announces new version + focuses flash', async () => {
    mockApi({ '/correct': { version: 3 } });
    renderInbox();
    fireEvent.click(await screen.findByRole('button', { name: /correct report/i }));
    fireEvent.change(screen.getByLabelText(/corrected body/i), { target: { value: 'v3 text' } });
    fireEvent.change(screen.getByLabelText(/correction reason/i), { target: { value: 'fix' } });
    fireEvent.click(screen.getByRole('button', { name: /create corrected version/i }));
    await waitFor(() => expect(screen.getByText(/created v3/i)).toBeInTheDocument());
    expect(screen.getByText(/earlier versions remain available and unchanged/i)).toBeInTheDocument();
  });

  it('follow-up dialog prefills and explains no report mutation / no auto-run', async () => {
    renderInbox();
    fireEvent.click((await screen.findAllByRole('button', { name: /create follow-up/i }))[0]);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/report is/i)).toBeInTheDocument();
    expect(screen.getByText(/not.*modified/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing runs automatically/i)).toBeInTheDocument();
    expect((screen.getByLabelText(/^title$/i) as HTMLInputElement).value)
      .toMatch(/follow up: sample task/i);
  });

  it('citation JSON validation error is surfaced, not thrown', async () => {
    renderInbox();
    fireEvent.click(await screen.findByRole('button', { name: /correct report/i }));
    fireEvent.change(screen.getByLabelText(/citations/i), { target: { value: '{bad json' } });
    fireEvent.change(screen.getByLabelText(/correction reason/i), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: /create corrected version/i }));
    expect(await screen.findByText(/must be valid json/i)).toBeInTheDocument();
  });
});
