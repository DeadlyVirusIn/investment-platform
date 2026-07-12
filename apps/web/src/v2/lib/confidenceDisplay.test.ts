// Confidence presentation mapping — owner decision 2026-07-09: High and
// Medium collapse to "meets the buy bar" by default (audit C2). Numeric
// conviction is untouched; VITE_MEETS_BUY_BAR=0 restores legacy copy.

import { describe, it, expect, afterEach, vi } from 'vitest';
import { confidenceDisplay, confidenceNarrativeSuffix, meetsBuyBarEnabled } from './confidenceDisplay';

afterEach(() => vi.unstubAllEnvs());

describe('confidenceDisplay (default: approved copy ON)', () => {
  it('is enabled by default', () => {
    expect(meetsBuyBarEnabled()).toBe(true);
  });

  it('collapses High and Medium to the approved label', () => {
    expect(confidenceDisplay('High')).toBe('meets the buy bar');
    expect(confidenceDisplay('Medium')).toBe('meets the buy bar');
  });

  it('leaves other labels in the legacy form', () => {
    expect(confidenceDisplay('Low')).toBe('low confidence');
  });

  it('null label defaults to Medium → approved label', () => {
    expect(confidenceDisplay(null)).toBe('meets the buy bar');
  });

  it('narrative suffix follows the same collapse', () => {
    expect(confidenceNarrativeSuffix('High')).toBe(' — it meets the buy bar');
    expect(confidenceNarrativeSuffix('Low')).toBe(' at low confidence');
    expect(confidenceNarrativeSuffix(null)).toBe('');
  });

  it('VITE_MEETS_BUY_BAR=0 restores the legacy presentation', () => {
    vi.stubEnv('VITE_MEETS_BUY_BAR', '0');
    expect(meetsBuyBarEnabled()).toBe(false);
    expect(confidenceDisplay('High')).toBe('high confidence');
  });
});
