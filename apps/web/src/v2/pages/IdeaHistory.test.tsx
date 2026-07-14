// Wave 1D — history page states + redaction + a11y basics.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MetaLabel: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}));

beforeEach(() => { vi.resetModules(); });
afterEach(() => vi.restoreAllMocks());

function replay(over: Record<string, unknown> = {}) {
  return {
    symbol: 'GE',
    recommendation_as_of: '2026-07-10T23:42:00+00:00',
    lifecycle_status: 'open',
    completeness: 'partial',
    completeness_note: 'This idea predates publication-preflight recording.',
    events: [{
      key: 'generated', type: 'idea_generated',
      occurred_at: '2026-07-10T23:42:00+00:00',
      title: 'Idea generated',
      summary: 'ArthOS recorded a Buy read at high confidence.',
      label: 'proven', source: 'recommendation',
      detail_status: 'complete', details: {},
    }],
    unavailable_sections: [{
      section: 'publication_preflight',
      reason: 'This idea predates publication-preflight recording.',
    }],
    user_scoped: false,
    generated_at: '2026-07-13T00:00:00+00:00',
    ...over,
  };
}

async function renderPage(payload: unknown, status = 200) {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = vi.fn().mockResolvedValue({
    ok: status === 200, status, json: () => Promise.resolve(payload),
  } as Response);
  const { IdeaHistory } = await import('./IdeaHistory');
  return render(
    <MemoryRouter initialEntries={['/today/pick/GE/history']}>
      <Routes>
        <Route path="/today/pick/:symbol/history" element={<IdeaHistory />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('IdeaHistory', () => {
  it('flag off (404) → calm unavailable state, nothing lost', async () => {
    await renderPage(null, 404);
    expect(await screen.findByText(/history isn't available/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing is lost/i)).toBeInTheDocument();
  });

  it('partial timeline: pre-preflight idea disclosed honestly', async () => {
    await renderPage(replay());
    expect(await screen.findByText(/idea generated/i)).toBeInTheDocument();
    expect(screen.getByText(/high confidence/i)).toBeInTheDocument(); // historical wording
    expect(screen.getAllByText(/predates publication-preflight/i).length)
      .toBeGreaterThan(0);
    expect(screen.getByText(/some history was not recorded/i)).toBeInTheDocument();
    // paper-only disclosure always present
    expect(screen.getByText(/practice money, never real trades/i)).toBeInTheDocument();
  });

  it('complete resolved timeline with paper + outcome + lesson order', async () => {
    const at = '2026-07-11T00:00:00+00:00';
    await renderPage(replay({
      completeness: 'complete',
      completeness_note: 'Every recorded artifact for this idea is shown.',
      lifecycle_status: 'resolved_target',
      unavailable_sections: [],
      events: [
        { key: 'generated', type: 'idea_generated', occurred_at: at, title: 'Idea generated', summary: 's', label: 'proven', source: 'recommendation', detail_status: 'complete', details: {} },
        { key: 'preflight', type: 'preflight', occurred_at: at, title: 'Publication check', summary: 'Published with honest limitations after the publication check.', label: 'proven', source: 'preflight', detail_status: 'complete', details: {} },
        { key: 'paper_open:0', type: 'paper_action', occurred_at: at, title: 'Added to your practice portfolio', summary: 'p', label: 'proven', source: 'paper', detail_status: 'partial', details: { execution_costs_note: 'Execution-cost detail was not recorded for this practice trade.' } },
        { key: 'outcome', type: 'outcome', occurred_at: at, title: 'Target condition reached', summary: 'o', label: 'proven', source: 'outcome', detail_status: 'complete', details: {} },
      ],
    }));
    expect(await screen.findByText(/resolved by reaching its target/i)).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items.length).toBe(4);
    expect(items[0]).toHaveTextContent('Idea generated');
    expect(items[3]).toHaveTextContent('Target condition reached');
    // missing cost detail disclosed
    expect(screen.getByText(/detail partial/i)).toBeInTheDocument();
  });

  it('never renders raw diagnostics', async () => {
    const { container } = await renderPage(replay());
    await screen.findByText(/idea generated/i);
    for (const leak of ['snapshot_hash', 'git_sha', 'input_hash', 'checks_json']) {
      expect(container.innerHTML).not.toContain(leak);
    }
  });
});
