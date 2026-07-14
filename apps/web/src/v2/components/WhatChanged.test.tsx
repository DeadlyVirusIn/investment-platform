// Wave 1C — WhatChanged states, compact notes, redaction, a11y basics.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

beforeEach(() => { vi.resetModules(); });
afterEach(() => vi.restoreAllMocks());

function delta(over: Record<string, unknown> = {}) {
  return {
    symbol: 'GE', rule_set_version: 'delta-1',
    current_as_of: '2026-07-13T23:00:00+00:00',
    prior_as_of: '2026-07-12T23:00:00+00:00',
    first_seen: false,
    summary: 'The evidence is broadly unchanged since the previous update.',
    changes: [], evidence_balance: 'unchanged',
    price_context: null, freshness_context: null, limitations: [],
    ...over,
  };
}

async function renderSection(payload: unknown, status = 200) {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = vi.fn().mockResolvedValue({
    ok: status === 200, status, json: () => Promise.resolve(payload),
  } as Response);
  const mod = await import('./WhatChanged');
  return { ...render(<mod.WhatChangedSection symbol="GE" />), mod };
}

describe('WhatChangedSection', () => {
  it('feature off (404) renders nothing', async () => {
    const { container } = await renderSection(null, 404);
    await screen.findByText(/checking for changes/i).catch(() => null);
    await new Promise((r) => setTimeout(r, 10));
    expect(container.textContent).toBe('');
  });

  it('first-seen state', async () => {
    await renderSection(delta({
      first_seen: true, prior_as_of: null,
      summary: 'This is a new idea from ArthOS.',
    }));
    expect(await screen.findByText(/new idea from arthos/i)).toBeInTheDocument();
  });

  it('unchanged state shows honest summary and no list', async () => {
    await renderSection(delta());
    expect(await screen.findByText(/broadly unchanged/i)).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('meaningful changes: top three + keyboard disclosure, direction not color-only', async () => {
    const changes = [
      { id: 'a', kind: 'action_change', direction: 'cautious', significance: 'large', beginner_text: 'ArthOS moved from Buy to Hold.', source: 'recommendation' },
      { id: 'b', kind: 'evidence_balance', direction: 'cautious', significance: 'meaningful', beginner_text: 'The balance of evidence became more cautious.', source: 'evidence' },
      { id: 'c', kind: 'family_change:x', direction: 'positive', significance: 'small', beginner_text: 'Trend improved slightly.', source: 'evidence' },
      { id: 'd', kind: 'freshness_change', direction: 'positive', significance: 'small', beginner_text: 'Data fresher.', source: 'freshness' },
    ];
    await renderSection(delta({
      summary: 'ArthOS became more cautious since the previous update.',
      changes,
    }));
    expect(await screen.findByText(/became more cautious since/i)).toBeInTheDocument();
    expect(screen.getByText(/moved from buy to hold/i)).toBeInTheDocument();
    // 4th change hidden behind the (closed) disclosure
    expect(screen.getByText(/data fresher/i)).not.toBeVisible();
    const summary = screen.getByText(/see all 4 changes/i);
    fireEvent.click(summary);
    expect(screen.getByText(/data fresher/i)).toBeVisible();
    // screen-reader direction labels (not color-only)
    expect(screen.getAllByText(/cautionary change:/i).length).toBeGreaterThan(0);
  });

  it('never renders raw diagnostics', async () => {
    const { container } = await renderSection(delta({
      changes: [{ id: 'a', kind: 'price_move', direction: 'informational', significance: 'large', beginner_text: 'Price moved 6%.', source: 'plan' }],
    }));
    await screen.findByText(/price moved/i);
    const html = container.innerHTML;
    for (const leak of ['snapshot_hash', 'git_sha', 'input_hash', 'uuid']) {
      expect(html).not.toContain(leak);
    }
  });
});

describe('compactChangeNote', () => {
  it('null for no delta / small changes; text for meaningful', async () => {
    const { compactChangeNote } = await import('./WhatChanged');
    expect(compactChangeNote(null)).toBeNull();
    expect(compactChangeNote(delta() as never)).toBeNull();
    expect(compactChangeNote(delta({ first_seen: true }) as never)).toBe('New idea');
    expect(compactChangeNote(delta({
      changes: [{ id: 'a', kind: 'action_change', direction: 'cautious', significance: 'large', beginner_text: 'x', source: 'recommendation' }],
    }) as never)).toMatch(/more cautious/i);
    expect(compactChangeNote(delta({
      changes: [{ id: 'a', kind: 'evidence_balance', direction: 'cautious', significance: 'meaningful', beginner_text: 'x', source: 'evidence' }],
    }) as never)).toBe('Risk signals increased');
  });

  it('formatSupersedesNote for inbox reuse', async () => {
    const { formatSupersedesNote } = await import('./WhatChanged');
    expect(formatSupersedesNote(delta() as never)).toMatch(/^Supersedes the 2026-07-12 update/);
    expect(formatSupersedesNote(delta({ first_seen: true, prior_as_of: null }) as never)).toBeNull();
  });
});
