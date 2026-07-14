// Posture banner — calm copy, never panic, absent on NORMAL/flag-off.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// bust the module-level cache between tests
beforeEach(() => { vi.resetModules(); });
afterEach(() => vi.restoreAllMocks());

async function renderWithPosture(payload: unknown, status = 200) {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = vi.fn().mockResolvedValue({
    ok: status === 200, status,
    json: () => Promise.resolve(payload),
  } as Response);
  const { PostureBanner } = await import('./PostureBanner');
  return render(<PostureBanner />);
}

describe('PostureBanner', () => {
  it('renders nothing on NORMAL', async () => {
    const { container } = await renderWithPosture({
      posture: 'NORMAL', message: '', evaluated_at: null,
      new_ideas_paused: false, existing_ideas_available: true,
      portfolio_available: true,
    });
    await Promise.resolve();
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it('renders nothing when the route is absent (flag off)', async () => {
    const { container } = await renderWithPosture(null, 404);
    await Promise.resolve();
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it('SAFE shows the calm paused message with availability reassurance', async () => {
    await renderWithPosture({
      posture: 'SAFE', message: 'x', evaluated_at: null,
      new_ideas_paused: true, existing_ideas_available: true,
      portfolio_available: true,
    });
    expect(await screen.findByText(/new ideas are paused/i)).toBeInTheDocument();
    expect(screen.getByText(/still available/i)).toBeInTheDocument();
    // no panic language
    const text = (document.body.textContent ?? '').toLowerCase();
    for (const bad of ['risk', 'danger', 'lost', 'emergency', 'critical']) {
      expect(text).not.toContain(bad);
    }
  });

  it('RESTRICTED shows the delayed-data message', async () => {
    await renderWithPosture({
      posture: 'RESTRICTED', message: 'x', evaluated_at: null,
      new_ideas_paused: false, existing_ideas_available: true,
      portfolio_available: true,
    });
    expect(await screen.findByText(/some data is delayed/i)).toBeInTheDocument();
    expect(screen.getByText(/additional limitations/i)).toBeInTheDocument();
  });
});
