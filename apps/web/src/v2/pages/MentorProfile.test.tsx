import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../state/SessionContext', () => ({
  useSession: () => ({ authenticated: true, loading: false }),
}));
vi.mock('../../lib/profile', () => ({
  getProfile: vi.fn().mockResolvedValue({
    profile: {
      investing_experience: 'none', investing_goal: 'learn', risk_comfort: 'low',
      time_horizon: 'long', preferred_style: 'steady', liquidity_need: null, options_experience: null,
    },
  }),
}));
vi.mock('../chrome/ArthosChrome', () => ({ ArthosPage: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }));
vi.mock('./components/MeTabs', () => ({ MeTabs: () => null }));
vi.mock('../components/ui/PageHeader', () => ({ PageHeader: () => null }));
vi.mock('../components/ui/SurfaceCard', () => ({ SurfaceCard: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('../chrome/ArthVoice', () => ({ ArthVoice: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, ArthGlyph: () => <span /> }));
vi.mock('../lib/arth/streak', () => ({ useStreak: () => ({ current_day: 0, longest_day: 0, visit_dates: [] }) }));
vi.mock('../lib/arth/memory', () => ({ useMemoryNotes: () => [] }));
vi.mock('../lib/arth/patterns', () => ({ useVisiblePatterns: () => [], confirmPattern: vi.fn(), disputePattern: vi.fn(), confidenceHedge: () => '' }));
vi.mock('../lib/arth/competence', () => ({ useCompetence: () => [] }));
vi.mock('../lib/arth/strengths', () => ({ deriveStrengths: () => [], deriveBlindSpots: () => [] }));
vi.mock('../lib/arth/events', () => ({ useEvents: () => [] }));
vi.mock('../lib/arth/decisions', () => ({ useDecisions: () => [] }));
vi.mock('../lib/arth/contextualLessons', () => ({ CONTEXTUAL_LESSONS: {} }));
vi.mock('../lib/arth/demoSeed2e', () => ({ seed2eMentorDemo: vi.fn() }));

import { MentorProfile } from './MentorProfile';

describe('MentorProfile', () => {
  it('renders saved profile answers using the profile labels', async () => {
    render(<MemoryRouter><MentorProfile /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/experience —/i)).toBeInTheDocument());
    expect(screen.getByText(/new to investing/i)).toBeInTheDocument();
    expect(screen.getByText(/horizon —/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /edit/i })).toHaveAttribute('href', '/profile');
  });
});
