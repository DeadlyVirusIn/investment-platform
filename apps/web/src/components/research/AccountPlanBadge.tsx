// Phase G — read-only account-plan badge. Calls GET /api/auth/me
// once on mount and renders the server-resolved tier.
//
// NEVER trusts the env value in production paths. NEVER renders
// any action wording / signal language / trading copy.

import { useEffect, useState } from 'react';
import { fetchMe, MeResponse } from '../../lib/research/tier';

const _LABEL: Record<string, string> = {
  free: 'Free',
  pro: 'Pro',
  enterprise: 'Enterprise',
};

const _STYLES: Record<string, { bg: string; fg: string }> = {
  free: { bg: '#f5f5f5', fg: '#616161' },
  pro: { bg: '#e3f2fd', fg: '#1565c0' },
  enterprise: { bg: '#ede7f6', fg: '#4527a0' },
};

export default function AccountPlanBadge() {
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMe().then((m) => {
      if (!cancelled) setMe(m);
    });
    return () => { cancelled = true; };
  }, []);

  const tier = me?.effective_tier ?? 'free';
  const style = _STYLES[tier];
  const label = _LABEL[tier] ?? 'Free';

  return (
    <span
      className={`account-plan-badge plan-${tier}`}
      data-effective-tier={tier}
      title={
        me?.user?.email
          ? `${me.user.email} (${label})`
          : `Plan: ${label}`
      }
      style={{
        background: style.bg,
        color: style.fg,
        fontSize: 11,
        padding: '2px 8px',
        borderRadius: 3,
        fontWeight: 600,
        letterSpacing: 0.4,
        textTransform: 'uppercase',
      }}
    >
      {label}
    </span>
  );
}
