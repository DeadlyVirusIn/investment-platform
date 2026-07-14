// Demo-vs-user book honesty (audit M2): "Your" is earned by an
// authenticated session, never by the shared canonical engine book.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const sessionState = { authenticated: false, loading: false, user: null as unknown };
const bookState: { data: Record<string, unknown> | undefined; isLoading: boolean } =
  { data: undefined, isLoading: false };

vi.mock('../state/SessionContext', () => ({
  useSession: () => sessionState,
}));

vi.mock('@/lib/operator/hooks', () => ({
  useCanonicalStockPortfolio: () => bookState,
  useExecutedPositions: () => ({ data: { positions: [] }, isLoading: false, isError: false }),
}));

// The chrome shell (ticker, side nav, palette) is out of scope here.
vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MetaLabel: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}));
vi.mock('./components/PracticeTabs', () => ({ PracticeTabs: () => null }));

import { PaperBook } from './PaperBook';

function renderBook() {
  return render(<MemoryRouter><PaperBook /></MemoryRouter>);
}

const DEMO_BOOK = {
  portfolio_id: 'engine-book', nav: 100000, cash: 5000,
  as_of: new Date().toISOString(), freshness: 'fresh', open_positions_count: 3,
};

beforeEach(() => {
  sessionState.authenticated = false;
  sessionState.loading = false;
  bookState.data = undefined;
  bookState.isLoading = false;
});

describe('PaperBook demo/user presentation', () => {
  it('signed-out + engine book → labeled Demo, never "Your", sign-in CTA', () => {
    bookState.data = DEMO_BOOK;
    renderBook();
    expect(screen.getByRole('heading', { name: /demo practice portfolio/i })).toBeInTheDocument();
    expect(screen.getByText(/doesn't belong to you/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create a free account/i })).toHaveAttribute('href', '/account');
    expect(screen.queryByText(/your practice portfolio/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/this is your/i)).not.toBeInTheDocument();
  });

  it('signed-in user book → "Your practice portfolio", no demo framing', () => {
    sessionState.authenticated = true;
    bookState.data = DEMO_BOOK;
    renderBook();
    expect(screen.getByRole('heading', { name: /^practice portfolio\.$/i })).toBeInTheDocument();
    expect(screen.getByText(/your practice portfolio/i)).toBeInTheDocument();
    expect(screen.queryByText(/demo practice portfolio/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /create a free account/i })).not.toBeInTheDocument();
  });

  it('session still resolving → does not prematurely claim demo', () => {
    sessionState.loading = true;
    bookState.data = DEMO_BOOK;
    renderBook();
    expect(screen.queryByText(/demo practice portfolio/i)).not.toBeInTheDocument();
  });

  it('signed-in with no book resolved → still "Your", empty-state guidance', () => {
    sessionState.authenticated = true;
    bookState.data = undefined;
    renderBook();
    expect(screen.getByText(/your practice portfolio/i)).toBeInTheDocument();
    expect(screen.getByText(/your portfolio is empty/i)).toBeInTheDocument();
  });
});
