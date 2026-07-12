// Route error boundary — no white screens, data-safety reassurance,
// working retry, navigation reset, bounded logging.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useState } from 'react';
import { RouteErrorBoundary } from './RouteErrorBoundary';

let consoleSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => consoleSpy.mockRestore());

function Bomb({ message = 'boom' }: { message?: string }) {
  throw new Error(message);
}

function renderWithRouter(ui: React.ReactNode, path = '/portfolio') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RouteErrorBoundary>{ui}</RouteErrorBoundary>
    </MemoryRouter>,
  );
}

describe('RouteErrorBoundary', () => {
  it('catches a thrown render error — no white screen, alert announced', () => {
    renderWithRouter(<Bomb />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/practice portfolio data is safe/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try this page again/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to discover/i })).toHaveAttribute('href', '/discover');
  });

  it('renders children normally when nothing throws', () => {
    renderWithRouter(<p>healthy page</p>);
    expect(screen.getByText('healthy page')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('retry remounts the subtree and recovers once the fault is gone', () => {
    // Throws on first mount only — models a transient failure (e.g. a
    // lazy chunk that loads on the second attempt).
    let shouldThrow = true;
    function Flaky() {
      const [, force] = useState(0);
      void force;
      if (shouldThrow) throw new Error('transient');
      return <p>recovered</p>;
    }
    renderWithRouter(<Flaky />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: /try this page again/i }));
    expect(screen.getByText('recovered')).toBeInTheDocument();
  });

  it('logs bounded context — name/message, never a payload dump', () => {
    const bigSecretPayload = 'x'.repeat(5000);
    renderWithRouter(<Bomb message={bigSecretPayload} />);
    const logged = consoleSpy.mock.calls.find((c) => String(c[0]).includes('[route-error]'));
    expect(logged).toBeTruthy();
    expect(String(logged![0]).length).toBeLessThan(1000);
  });

  it('moves keyboard focus to the announcement', () => {
    renderWithRouter(<Bomb />);
    const focused = document.activeElement as HTMLElement;
    expect(focused?.textContent ?? '').toMatch(/hit a snag|practice portfolio/i);
  });
});
