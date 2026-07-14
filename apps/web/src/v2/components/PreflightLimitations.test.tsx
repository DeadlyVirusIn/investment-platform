// Preflight limitation chips — beginner surface only ever sees the redacted
// projection; HOLD/BLOCKED never reach the list, so the component renders
// nothing without a READY_WITH_LIMITATIONS projection.

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PreflightLimitations } from './PreflightLimitations';
import type { RecApi } from '@/lib/operator/hooks';

function rec(preflight: RecApi['preflight']): RecApi {
  return { id: 'r1', preflight } as unknown as RecApi;
}

describe('PreflightLimitations', () => {
  it('renders nothing when the API sent no projection (flag off)', () => {
    const { container } = render(<PreflightLimitations rec={rec(undefined)} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for plain READY', () => {
    const { container } = render(
      <PreflightLimitations rec={rec({
        verdict: 'READY', limitations: [], evaluated_at: null,
        freshness_summary: null,
      })} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('READY_WITH_LIMITATIONS shows the chip and discloses beginner text', () => {
    render(
      <PreflightLimitations rec={rec({
        verdict: 'READY_WITH_LIMITATIONS',
        limitations: ['Confidence wording is based on rules whose real-world accuracy is still being measured.'],
        evaluated_at: new Date().toISOString(),
        freshness_summary: null,
      })} />,
    );
    const btn = screen.getByRole('button', { name: /published with limitations/i });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/still being measured/i)).toBeInTheDocument();
  });

  it('never renders developer diagnostics fields', () => {
    const { container } = render(
      <PreflightLimitations rec={rec({
        verdict: 'READY_WITH_LIMITATIONS',
        limitations: ['A limitation.'],
        evaluated_at: null, freshness_summary: null,
      })} />,
    );
    const html = container.innerHTML;
    for (const leak of ['input_hash', 'check_id', 'git_sha', 'BLOCKED']) {
      expect(html).not.toContain(leak);
    }
  });
});
