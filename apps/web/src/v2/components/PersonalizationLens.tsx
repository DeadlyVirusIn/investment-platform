// M4 — Personalization lens card. EXPLANATION ONLY. Renders honest fit/caution
// context for one recommendation, computed purely from the user's profile +
// metadata already on the idea. Never changes the recommendation.
//
// Visibility: anonymous/demo users see nothing (existing experience preserved);
// logged-in users with an incomplete profile get a gentle complete-profile
// prompt; logged-in users with a complete profile see the lens.

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MetaLabel } from '../chrome/ArthosChrome';
import { useSession } from '../state/SessionContext';
import { getProfile } from '../../lib/profile';
import { computeLens, type RecMeta, type ProfileLensInput } from '../lib/personalization';

const CAUTION_TONE = 'oklch(0.70 0.14 75)';

export function PersonalizationLens({ meta }: { meta: RecMeta }) {
  const { authenticated, loading } = useSession();
  const [profile, setProfile] = useState<ProfileLensInput | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!authenticated) { setLoaded(true); return; }
    let alive = true;
    getProfile()
      .then((r) => { if (alive) setProfile(r.profile); })
      .catch(() => {})
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; };
  }, [authenticated, loading]);

  // Anonymous / demo users → keep the existing experience untouched.
  if (!loading && !authenticated) return null;
  if (!loaded) return null;

  const lens = computeLens(profile, meta);

  if (lens.fit_label === 'Not enough profile') {
    return (
      <section className="mb-12 max-w-narrative">
        <div className="rounded-xl border border-hairline p-5 sm:p-6">
          <MetaLabel>Personalization lens</MetaLabel>
          <p className="ink-primary text-[15px] mt-2">Complete your profile to see fit context.</p>
          <p className="ink-muted text-[13px] leading-relaxed mt-1">{lens.limitations}</p>
          <Link to="/profile" className="text-meta ink-primary mt-3 inline-block" style={{ fontWeight: 600 }}>
            Complete profile →
          </Link>
        </div>
      </section>
    );
  }

  const tone =
    lens.fit_label === 'Strong fit' ? 'var(--brand)' :
    lens.fit_label === 'Caution' ? CAUTION_TONE : 'var(--foreground)';

  return (
    <section className="mb-12 max-w-narrative">
      <div className="rounded-xl border border-hairline p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <MetaLabel>Personalization lens</MetaLabel>
          <span className="font-semibold" style={{ fontSize: 12.5, color: tone }}>{lens.fit_label}</span>
        </div>
        <p className="ink-muted text-[13px] leading-relaxed mt-2">
          Based on your profile, ArthOS flags where this idea may or may not fit you. The recommendation
          engine itself has not been changed by your profile yet — this is context, not advice.
        </p>

        {lens.fit_reasons.length > 0 && (
          <div className="mt-4">
            <p className="text-[12px] font-semibold uppercase tracking-wide ink-fainter mb-1.5">Why it may fit you</p>
            <ul className="space-y-1.5">
              {lens.fit_reasons.map((r, i) => (
                <li key={i} className="flex items-baseline gap-2 ink-primary text-[14px] leading-snug">
                  <span aria-hidden style={{ color: 'var(--brand)', fontSize: 11 }}>▲</span>{r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {lens.caution_reasons.length > 0 && (
          <div className="mt-4">
            <p className="text-[12px] font-semibold uppercase tracking-wide ink-fainter mb-1.5">Worth a closer look</p>
            <ul className="space-y-1.5">
              {lens.caution_reasons.map((r, i) => (
                <li key={i} className="flex items-baseline gap-2 ink-primary text-[14px] leading-snug">
                  <span aria-hidden style={{ color: CAUTION_TONE, fontSize: 11 }}>▼</span>{r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {lens.profile_fields_used.length > 0 && (
          <p className="ink-fainter text-[12px] leading-relaxed mt-4">
            Profile used: {lens.profile_fields_used.map((f) => f.replace(/_/g, ' ')).join(', ')}.
          </p>
        )}
      </div>
    </section>
  );
}
