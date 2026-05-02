// Phase 11W (Phase F.1) — frontend tier resolver + fetch helper.
//
// Reads `import.meta.env.VITE_RESEARCH_PREMIUM_TIER`. Default 'free'.
// NEVER claims a higher tier than the env declares. Server is the
// authoritative gate (see apps/api/src/research/premium_tier.py);
// the frontend value is sent as `X-Research-Tier` so the server can
// honor a lower-than-cap tier hint, but the server caps elevation.

export type ResearchTier = 'free' | 'pro' | 'enterprise';

// Phase G — env-based tier is local-dev fallback only. Production
// reads the effective tier from `GET /api/auth/me`.
export function getResearchTier(): ResearchTier {
  const raw = (
    (import.meta.env.VITE_RESEARCH_PREMIUM_TIER as string | undefined) || ''
  ).trim().toLowerCase();
  if (raw === 'pro' || raw === 'enterprise') return raw;
  return 'free';
}

export interface MeResponse {
  user: null | {
    id: string; email: string;
    display_name: string | null; auth_provider: string;
    disabled: boolean;
  };
  effective_tier: ResearchTier;
  reason: string;
}

export async function fetchMe(): Promise<MeResponse | null> {
  try {
    const res = await fetch('/api/auth/me', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return null;
    return (await res.json()) as MeResponse;
  } catch {
    return null;
  }
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
