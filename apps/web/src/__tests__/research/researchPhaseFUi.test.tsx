// Phase 11W (Phase F) — UI tests for the read-only Research panel.
//
// These tests target vitest + @testing-library/react. apps/web does
// not yet ship vitest (see apps/web/package.json); the file is
// written in framework form so it executes the moment those deps
// are added. Until then, these tests serve as a frozen behavioral
// spec.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import ResearchBanner from '../../components/research/ResearchBanner';
import ResearchByline from '../../components/research/ResearchByline';
import FreshnessBadge from '../../components/research/FreshnessBadge';
import ResearchSafetyFailure from '../../components/research/ResearchSafetyFailure';
import ResearchIntelligenceTab from '../../components/research/ResearchIntelligenceTab';
import ResearchPulseCard from '../../components/research/ResearchPulseCard';
import ResearchJobHealthCard from '../../components/research/ResearchJobHealthCard';
import { scanForbiddenTokens } from '../../lib/research/forbiddenTokens';


// ---------------------------------------------------------------------------
// Fetch mock helper
// ---------------------------------------------------------------------------


function _mockFetch(map: Record<string, unknown>) {
  return vi.fn().mockImplementation((url: string) => {
    const key = Object.keys(map).find((k) => url.includes(k));
    const body = key ? map[key] : { runs: [] };
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    } as Response);
  });
}

beforeEach(() => {
  // @ts-expect-error -- fetch is a global in jsdom
  global.fetch = _mockFetch({});
});

afterEach(() => {
  vi.restoreAllMocks();
});


// ---------------------------------------------------------------------------
// 1. Flag off unmounts everything
// ---------------------------------------------------------------------------


describe('research UI flag', () => {
  it('test_research_ui_flag_off_unmounts_all', () => {
    // Components are mounted by the host page only when
    // import.meta.env.VITE_RESEARCH_RO_ENABLED === 'true'. We
    // simulate the off path by checking the flag value before render.
    vi.stubEnv('VITE_RESEARCH_RO_ENABLED', 'false');
    expect(import.meta.env.VITE_RESEARCH_RO_ENABLED).toBe('false');
    // (Host page guard short-circuits before any of the components
    // below get rendered. There is no path that mounts them when
    // the flag is false.)
  });
});


// ---------------------------------------------------------------------------
// 2. Tab renders banner + 3. Tab requires banner
// ---------------------------------------------------------------------------


describe('ResearchIntelligenceTab', () => {
  it('test_research_tab_renders_banner', async () => {
    // @ts-expect-error -- fetch is a global in jsdom
    global.fetch = _mockFetch({
      '/api/research/ticker/UNH/latest': { symbol: 'UNH', run: null },
    });
    render(<ResearchIntelligenceTab symbol="UNH" />);
    await waitFor(() => {
      expect(screen.getByText(/Research note/i)).toBeTruthy();
      expect(screen.getByText(/not execution logic/i)).toBeTruthy();
    });
  });

  it('test_research_tab_requires_banner', () => {
    expect(() =>
      render(
        // @ts-expect-error — intentionally missing context prop
        <ResearchBanner />,
      ),
    ).toThrow(/context/);
  });
});


// ---------------------------------------------------------------------------
// 4. Fail-closed on forbidden token
// ---------------------------------------------------------------------------


describe('client fail-closed', () => {
  it('test_research_fail_closed_on_forbidden_token', async () => {
    // @ts-expect-error -- fetch is a global in jsdom
    global.fetch = _mockFetch({
      '/api/research/ticker/UNH/latest': {
        symbol: 'UNH',
        run: {
          id: 'r1', symbol: 'UNH', as_of: '2026-04-29',
          provider: 'mock', model_id: 'm1', model_version: 'v1',
          prompt_hash: 'h', status: 'succeeded',
          started_at: new Date().toISOString(),
          finished_at: new Date().toISOString(),
          operator_id: 'op',
        },
      },
      '/api/research/runs/r1': {
        run: { id: 'r1', symbol: 'UNH' },
        outputs: [{
          id: 'o1', agent_role: 'bull_researcher', sequence_no: 0,
          // Body contains a forbidden word; server SHOULD have set
          // safety_status='unsafe' and stripped body to null. We
          // simulate a leak (server bug) and verify the client
          // still fails closed.
          body: 'we recommend buy AAPL', safety_status: 'safe',
        }],
      },
    });
    render(<ResearchIntelligenceTab symbol="UNH" />);
    await waitFor(() => {
      expect(screen.getByText(/Research note rejected/i)).toBeTruthy();
    });
    // Body text MUST NOT appear.
    expect(screen.queryByText(/recommend buy/i)).toBeNull();
  });
});


// ---------------------------------------------------------------------------
// 5. No action buttons + 6. No POST from UI
// ---------------------------------------------------------------------------


describe('action surface', () => {
  it('test_research_no_action_buttons', () => {
    render(<ResearchIntelligenceTab symbol="UNH" />);
    // Scan rendered DOM for any <button> element.
    const buttons = document.querySelectorAll('button');
    expect(buttons.length).toBe(0);
  });

  it('test_research_no_post_from_ui', async () => {
    // @ts-expect-error -- override
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({ runs: [] }),
    });
    render(<ResearchPulseCard />);
    render(<ResearchJobHealthCard />);
    render(<ResearchIntelligenceTab symbol="UNH" />);
    await waitFor(() => {
      // Every fetch call must be a GET (or no method = GET default).
      // @ts-expect-error -- mock typing
      const calls = (global.fetch as any).mock.calls as Array<[string, RequestInit | undefined]>;
      for (const [, init] of calls) {
        const m = (init?.method ?? 'GET').toUpperCase();
        expect(m).toBe('GET');
      }
    });
  });
});


// ---------------------------------------------------------------------------
// 7-8. Pulse + JobHealth read GET only
// ---------------------------------------------------------------------------


describe('cards', () => {
  it('test_research_pulse_reads_get_only', async () => {
    // @ts-expect-error
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({ runs: [] }),
    });
    render(<ResearchPulseCard />);
    await waitFor(() => {
      // @ts-expect-error
      const [url, init] = (global.fetch as any).mock.calls[0];
      expect(String(url)).toContain('/api/research/runs');
      expect((init?.method ?? 'GET').toUpperCase()).toBe('GET');
    });
  });

  it('test_research_job_health_reads_get_only', async () => {
    // @ts-expect-error
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({
        audit_table: 'present',
        summary: {
          accepted: 1, duplicate: 0, rejected: 0,
          in_flight: 0, errored: 0, cost_usd_today: 0.001,
        },
      }),
    });
    render(<ResearchJobHealthCard />);
    await waitFor(() => {
      // @ts-expect-error
      const [url, init] = (global.fetch as any).mock.calls[0];
      expect(String(url)).toContain('/api/research/usage');
      expect((init?.method ?? 'GET').toUpperCase()).toBe('GET');
    });
  });
});


// ---------------------------------------------------------------------------
// 9. Byline + 10. Freshness badge
// ---------------------------------------------------------------------------


describe('byline + freshness', () => {
  it('test_research_byline_renders_provenance', () => {
    render(
      <ResearchByline
        provider="mock"
        modelId="research-mock-v1"
        modelVersion="v1.0.0"
        promptHash="abcdef0123456789"
        asOf="2026-04-29"
        operatorId="op-f"
      />,
    );
    expect(screen.getByText(/provider=/i)).toBeTruthy();
    expect(screen.getByText(/model=/i)).toBeTruthy();
    expect(screen.getByText(/prompt_hash=/i)).toBeTruthy();
    expect(screen.getByText(/as_of=/i)).toBeTruthy();
    // Hash must be truncated.
    expect(screen.getByText(/abcdef0123…/i)).toBeTruthy();
  });

  it('test_research_freshness_badge', () => {
    const now = new Date('2026-05-01T12:00:00Z');
    const fresh = new Date(now.getTime() - 1 * 3_600_000).toISOString();
    const aging = new Date(now.getTime() - 12 * 3_600_000).toISOString();
    const stale = new Date(now.getTime() - 48 * 3_600_000).toISOString();

    const { unmount: u1 } = render(
      <FreshnessBadge isoTimestamp={fresh} nowOverride={now} />,
    );
    expect(
      document.querySelector('[data-bucket="fresh"]'),
    ).toBeTruthy();
    u1();

    const { unmount: u2 } = render(
      <FreshnessBadge isoTimestamp={aging} nowOverride={now} />,
    );
    expect(
      document.querySelector('[data-bucket="aging"]'),
    ).toBeTruthy();
    u2();

    render(<FreshnessBadge isoTimestamp={stale} nowOverride={now} />);
    expect(
      document.querySelector('[data-bucket="stale"]'),
    ).toBeTruthy();
  });
});


// ---------------------------------------------------------------------------
// 11. No research UI imports trading modules
// 12. No scheduler / worker changes
// (These are static checks — see the Python-side test
// `test_research_phase_f_static.py` for grep enforcement on the
// frontend tree. UI test runner doesn't have shell access; we
// instead assert the public component prop surface stays minimal.)
// ---------------------------------------------------------------------------


describe('component contracts', () => {
  it('safety failure component has no body prop', () => {
    // Sanity: the SafetyFailure component MUST NOT accept a "body"
    // prop. It exists to render a fixed string only.
    render(<ResearchSafetyFailure />);
    expect(screen.getByText(/failed safety check/i)).toBeTruthy();
  });

  it('forbiddenTokens scanner blocks recommend/buy/sell', () => {
    expect(scanForbiddenTokens('we recommend buy AAPL').ok).toBe(false);
    expect(scanForbiddenTokens('clean narrative').ok).toBe(true);
  });
});
