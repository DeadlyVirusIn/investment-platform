// EvidenceBadge + StatusPanel — the shared honesty/state primitives.
// Guarantees under test: never color-only (glyph + spelled-out text),
// unknown labels degrade safely, panels expose the right a11y roles.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EvidenceBadge, toEvidenceState } from './EvidenceBadge';
import { StatusPanel } from './StatusPanel';

describe('EvidenceBadge', () => {
  it.each([
    ['proven', 'Proven'],
    ['preliminary', 'Preliminary'],
    ['insufficient_data', 'Insufficient data'],
    ['not_yet_evaluated', 'Not evaluated'],
    ['degraded', 'Degraded'],
    ['unavailable', 'Unavailable'],
  ])('renders %s as spelled-out text', (state, text) => {
    render(<EvidenceBadge state={state} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('exposes the plain-English meaning to assistive tech', () => {
    render(<EvidenceBadge state="preliminary" />);
    const el = screen.getByLabelText(/research data, not a production statistic/i);
    expect(el).toBeInTheDocument();
  });

  it('unknown backend labels degrade to not_yet_evaluated, never crash', () => {
    expect(toEvidenceState('brand_new_label')).toBe('not_yet_evaluated');
    expect(toEvidenceState(null)).toBe('not_yet_evaluated');
    render(<EvidenceBadge state="brand_new_label" />);
    expect(screen.getByText('Not evaluated')).toBeInTheDocument();
  });
});

describe('StatusPanel', () => {
  it('renders title, detail, and action', () => {
    render(
      <StatusPanel variant="warn" title="Snapshot from Jul 8 — 3 days old" action={<a href="/discover">Back</a>}>
        Nothing is lost.
      </StatusPanel>,
    );
    expect(screen.getByText(/Snapshot from Jul 8/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is lost/)).toBeInTheDocument();
    expect(screen.getByRole('link')).toBeInTheDocument();
  });

  it('passes through the a11y role for dynamic announcements', () => {
    render(<StatusPanel variant="error" title="Something went wrong" role="alert" />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('every variant carries a glyph so state is not color-only', () => {
    for (const variant of ['info', 'success', 'warn', 'error'] as const) {
      const { container, unmount } = render(<StatusPanel variant={variant} title="t" />);
      const glyph = container.querySelector('[aria-hidden]');
      expect(glyph?.textContent?.trim()).toBeTruthy();
      unmount();
    }
  });
});
