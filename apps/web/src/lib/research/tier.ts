// Phase 11W (Phase F.1) — frontend tier resolver + fetch helper.
//
// Reads `import.meta.env.VITE_RESEARCH_PREMIUM_TIER`. Default 'free'.
// NEVER claims a higher tier than the env declares. Server is the
// authoritative gate (see apps/api/src/research/premium_tier.py);
// the frontend value is sent as `X-Research-Tier` so the server can
// honor a lower-than-cap tier hint, but the server caps elevation.

export type ResearchTier = 'free' | 'pro' | 'enterprise';

export function getResearchTier(): ResearchTier {
  const raw = (
    (import.meta.env.VITE_RESEARCH_PREMIUM_TIER as string | undefined) || ''
  ).trim().toLowerCase();
  if (raw === 'pro' || raw === 'enterprise') return raw;
  return 'free';
}

/**
 * GET wrapper that always sends the X-Research-Tier header.
 * NEVER POSTs. NEVER mutates server state.
 */
export async function tierFetch(path: string): Promise<Response> {
  return fetch(path, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      'X-Research-Tier': getResearchTier(),
    },
  });
}

export const RESEARCH_LOCKED_COPY = {
  full_note:
    'Upgrade to view the full research note and supporting evidence.',
  history:
    'Pro includes research history, source references, and freshness tracking.',
  enterprise:
    'Enterprise adds audit visibility and compliance export.',
} as const;
