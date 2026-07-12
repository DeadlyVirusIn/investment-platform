// Research Inbox — review-state rendering + fail-closed postures.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { AdminResearchInbox } from './AdminResearchInbox';

function report(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'r1', task_id: 't1', version: 1,
    body: 'Sample research body.', citations: [],
    provenance: 'generated', review_status: 'pending',
    reviewed_by: null, reviewed_at: null,
    created_at: new Date().toISOString(), state: 'fresh',
    ...over,
  };
}

function mockApi(reports: unknown[], tasks: unknown[] = [{ id: 't1', title: 'Sample task', question: 'q', scope: 'sector:test', created_at: null }]) {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = vi.fn().mockImplementation((url: string) =>
    Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve(String(url).includes('/tasks') ? { tasks } : { reports }),
    } as Response));
}

afterEach(() => vi.restoreAllMocks());
beforeEach(() => mockApi([]));

function renderInbox() {
  return render(<MemoryRouter><AdminResearchInbox /></MemoryRouter>);
}

describe('AdminResearchInbox review states', () => {
  it('pending report → Pending review chip + Approve/Reject actions', async () => {
    mockApi([report()]);
    renderInbox();
    const card = within(await screen.findByRole('list'));
    expect(card.getByText('Pending review')).toBeInTheDocument();
    expect(card.getByRole('button', { name: /^approve$/i })).toBeInTheDocument();
    expect(card.getByRole('button', { name: /^reject$/i })).toBeInTheDocument();
    expect(card.getByText(/machine-generated/i)).toBeInTheDocument();
  });

  it('approved report → Approved chip, reviewer shown, no action buttons', async () => {
    mockApi([report({ review_status: 'approved', reviewed_by: 'owner@example.com' })]);
    renderInbox();
    const card = within(await screen.findByRole('list'));
    expect(card.getByText('Approved')).toBeInTheDocument();
    expect(card.getByText(/reviewed by owner@example.com/i)).toBeInTheDocument();
    expect(card.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
  });

  it('rejected report stays listed — history is never deleted', async () => {
    mockApi([report({ review_status: 'rejected', reviewed_by: 'owner@example.com' })]);
    renderInbox();
    const card = within(await screen.findByRole('list'));
    expect(card.getByText('Rejected')).toBeInTheDocument();
    expect(card.getByText(/sample research body/i)).toBeInTheDocument();
  });

  it('superseded version carries the Superseded chip with history hint', async () => {
    mockApi([report({ state: 'superseded', version: 1 })]);
    renderInbox();
    const card = within(await screen.findByRole('list'));
    expect(card.getByText('Superseded')).toBeInTheDocument();
    expect(card.getByText('v1')).toBeInTheDocument();
  });

  it('owner-only 404 → fail-closed panel, no report data rendered', async () => {
    // @ts-expect-error -- fetch is a global in jsdom
    global.fetch = vi.fn().mockRejectedValue({ status: 404 });
    renderInbox();
    expect(await screen.findByText(/owner-only/i)).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
  });

  it('empty inbox → honest empty state', async () => {
    renderInbox();
    expect(await screen.findByText(/inbox is empty/i)).toBeInTheDocument();
  });
});
