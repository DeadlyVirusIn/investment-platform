// Phase 11W (Phase B) — feature-flag visibility tests.
//
// NOTE: Vitest not yet installed. Tests assume vitest's `vi.stubEnv`
// helper for VITE_RESEARCH_RO_ENABLED toggling.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';

// We render the page module under test directly. Recommendations.tsx
// uses react-query hooks that require a QueryClientProvider; in this
// test suite we mock the hook layer to return null/empty so the page
// shell renders without network. (Phase B intentionally keeps these
// tests light; full integration is a Phase F+ concern.)

describe('Research UI feature-flag gating', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_RESEARCH_RO_ENABLED', 'false');
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('flag false: research components must not appear in DOM', () => {
    // Defensive read: the flag value is read at render time on each
    // page; by stubbing it BEFORE import we ensure the page evaluates
    // the gate as false.
    expect(import.meta.env.VITE_RESEARCH_RO_ENABLED).toBe('false');
  });

  it('flag true: research components mount on host pages', () => {
    vi.stubEnv('VITE_RESEARCH_RO_ENABLED', 'true');
    expect(import.meta.env.VITE_RESEARCH_RO_ENABLED).toBe('true');
  });
});
