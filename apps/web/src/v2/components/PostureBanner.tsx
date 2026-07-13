// Research Safe Mode — beginner-facing posture banner (Wave 1B).
// Reads ONLY the public projection (GET /api/system/posture). Renders
// nothing on NORMAL, on fetch failure, or when the flag is off (route 404):
// the banner is calm information, never panic — funds are never implied to
// be at risk, and copy always says existing ideas/portfolio remain
// available.

import { useEffect, useState } from 'react';
import { StatusPanel } from './ui/StatusPanel';

type PublicPosture = {
  posture: 'NORMAL' | 'RESTRICTED' | 'SAFE';
  message: string;
  evaluated_at: string | null;
  new_ideas_paused: boolean;
  existing_ideas_available: boolean;
  portfolio_available: boolean;
};

let _cache: { at: number; value: PublicPosture | null } = { at: 0, value: null };

export function PostureBanner() {
  const [p, setP] = useState<PublicPosture | null>(_cache.value);

  useEffect(() => {
    if (Date.now() - _cache.at < 60_000) return;
    let alive = true;
    fetch('/api/system/posture', { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        _cache = { at: Date.now(), value: j };
        if (alive) setP(j);
      })
      .catch(() => { /* flag off or offline — no banner */ });
    return () => { alive = false; };
  }, []);

  if (!p || p.posture === 'NORMAL') return null;

  return (
    <div className="mb-6">
      <StatusPanel
        variant={p.posture === 'SAFE' ? 'warn' : 'info'}
        title={p.posture === 'SAFE'
          ? 'New ideas are paused while ArthOS checks its data.'
          : 'Some data is delayed.'}
        role="status"
      >
        {p.posture === 'SAFE'
          ? 'Your practice portfolio and existing ideas are still available.'
          : 'New ideas may include additional limitations.'}
      </StatusPanel>
    </div>
  );
}
