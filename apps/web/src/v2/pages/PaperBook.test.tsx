// Canonical book ownership and no-snapshot honesty.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const sessionState = { authenticated: false, loading: false, user: null as unknown };
const bookState: {
  data: Record<string, unknown> | undefined;
  isLoading: boolean;
  isError: boolean;
} = { data: undefined, isLoading: false, isError: false };
const positionsState: {
  data: { positions: Record<string, unknown>[] };
  isLoading: boolean;
  isError: boolean;
} = { data: { positions: [] }, isLoading: false, isError: false };

vi.mock('../state/SessionContext', () => ({
  useSession: () => sessionState,
}));

vi.mock('@/lib/operator/hooks', () => ({
  useCanonicalStockPortfolio: () => bookState,
  useExecutedPositions: () => positionsState,
}));

// The chrome shell (ticker, side nav, palette) is out of scope here.
vi.mock('../chrome/ArthosChrome', () => ({
  ArthosPage: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  MetaLabel: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}));
vi.mock('./components/PracticeTabs', () => ({ PracticeTabs: () => null }));

import {
  PaperBook,
  estimatedLivePositionsValue,
  getBookNarrative,
} from './PaperBook';

function renderBook() {
  // Position rows render CompanyTitle → useAssetNames → useQuery, so the
  // tree needs a QueryClient even though the book/positions hooks are mocked.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><PaperBook /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const SHARED_DEMO_BOOK = {
  portfolio_id: 'engine-book', nav: 100000, cash: 5000,
  as_of: new Date().toISOString(), freshness: 'fresh', open_positions_count: 3,
  book_scope: 'shared_demo',
};
const USER_BOOK = {
  ...SHARED_DEMO_BOOK,
  portfolio_id: 'user-book',
  book_scope: 'user',
};

beforeEach(() => {
  sessionState.authenticated = false;
  sessionState.loading = false;
  bookState.data = undefined;
  bookState.isLoading = false;
  bookState.isError = false;
  positionsState.data = { positions: [] };
  positionsState.isLoading = false;
  positionsState.isError = false;
});

describe('PaperBook demo/user presentation', () => {
  it('keeps an anonymous shared demo with positions labeled Demo, never device-owned', () => {
    bookState.data = SHARED_DEMO_BOOK;
    positionsState.data = { positions: [{ position_id: 'one' }] };
    renderBook();

    expect(screen.getByRole('heading', { name: /demo practice portfolio/i })).toBeInTheDocument();
    expect(screen.getByText(/doesn't belong to you/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create a free account/i }))
      .toHaveAttribute('href', '/account?mode=signup');
    expect(screen.queryByText(/your practice book \(this browser\)/i)).not.toBeInTheDocument();
  });

  it('uses account framing only for an authenticated user-scoped book', () => {
    sessionState.authenticated = true;
    bookState.data = USER_BOOK;
    renderBook();

    expect(screen.getByText(/your practice portfolio/i)).toBeInTheDocument();
    expect(screen.queryByText(/demo practice portfolio/i)).not.toBeInTheDocument();
  });

  it('uses device framing only for an anonymous user-scoped book', () => {
    bookState.data = USER_BOOK;
    renderBook();

    expect(screen.getByText(/your practice book \(this browser\)/i)).toBeInTheDocument();
    expect(screen.getByText(/it's tracked for this browser/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create a free account/i }))
      .toHaveAttribute('href', '/account?mode=signup');
  });

  it('stays neutral while the session or canonical book is unresolved or errored', () => {
    sessionState.loading = true;
    bookState.data = SHARED_DEMO_BOOK;
    renderBook();
    expect(screen.getAllByText(/loading this practice portfolio/i)).toHaveLength(3);
    expect(screen.queryByText(/your portfolio is empty/i)).not.toBeInTheDocument();
  });

  it('does not claim ownership or emptiness for a canonical error', () => {
    bookState.isError = true;
    renderBook();

    expect(screen.getAllByText(/couldn't load this practice portfolio/i)).toHaveLength(2);
    expect(screen.queryByText(/your portfolio is empty/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/demo practice portfolio/i)).not.toBeInTheDocument();
  });

  it('labels a partially priced no-snapshot book as invested positions, not book value', () => {
    sessionState.authenticated = true;
    bookState.data = {
      ...USER_BOOK,
      nav: null,
      cash: null,
      open_positions_count: 3,
    };
    positionsState.data = {
      positions: [
        { position_id: 'one', current_price: 10, market_value: 25, is_open: true },
        { position_id: 'two', current_price: null, market_value: 99, is_open: true },
        { position_id: 'three', current_price: 20, market_value: -5, is_open: true },
      ],
    };
    renderBook();

    expect(screen.getByText('Invested in open positions (priced positions only)')).toBeInTheDocument();
    expect(screen.getByText(/cash isn't known until the next market snapshot records the official book value/i)).toBeInTheDocument();
    expect(screen.getByText(/1 of 3 positions priced/i)).toBeInTheDocument();
  });
});

describe('PaperBook truth helpers', () => {
  it('uses authoritative scope, conservative fallbacks, and neutral loading/error states', () => {
    expect(getBookNarrative(false, false, 'shared_demo')).toBe('demo');
    expect(getBookNarrative(true, false, 'shared_demo')).toBe('demo');
    expect(getBookNarrative(true, false, 'user')).toBe('account');
    expect(getBookNarrative(false, false, 'user')).toBe('device');
    expect(getBookNarrative(true, false, undefined)).toBe('account');
    expect(getBookNarrative(false, false, undefined)).toBe('demo');
    expect(getBookNarrative(false, true, 'shared_demo')).toBe('neutral');
    expect(getBookNarrative(false, false, 'shared_demo', true)).toBe('neutral');
    expect(getBookNarrative(false, false, 'shared_demo', false, true)).toBe('neutral');
  });

  it('sums only finite, non-negative market values with finite current prices', () => {
    expect(estimatedLivePositionsValue([
      { current_price: 10, market_value: 25 },
      { current_price: null, market_value: 99 },
      { current_price: Number.POSITIVE_INFINITY, market_value: 30 },
      { current_price: 20, market_value: Number.NaN },
      { current_price: 20, market_value: -5 },
    ] as never)).toBe(25);
    expect(estimatedLivePositionsValue([
      { current_price: Number.NaN, market_value: 99 },
      { current_price: 15, market_value: -1 },
    ] as never)).toBeNull();
  });
});
