// M3 — minimal profile onboarding. Collect-only: stores the user's investing
// profile so ArthOS can personalize HONESTLY later. Does NOT change any
// recommendation today. Reuses existing tokens + ArthosPage shell.

import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { useSession } from '../state/SessionContext';
import { getProfile, saveProfile, type ProfileData } from '../../lib/profile';

type Opt = { value: string; label: string };
type Question = {
  key: keyof ProfileData; title: string; options: Opt[]; required?: boolean;
  /** Beginner-facing "why we ask" (audit H6) — every question explains itself. */
  why: string;
};

const QUESTIONS: Question[] = [
  { key: 'investing_experience', title: 'How much investing experience do you have?', required: true,
    why: 'So explanations match your level — more plain-English guidance if you are new, less hand-holding if you are not.',
    options: [
    { value: 'none', label: 'New to investing' },
    { value: 'beginner', label: 'Beginner' },
    { value: 'intermediate', label: 'Intermediate' },
    { value: 'experienced', label: 'Experienced' },
  ] },
  { key: 'investing_goal', title: 'What are you here to do?', required: true,
    why: 'Different goals call for different ideas — learning favors variety; income and preservation favor steadier names.',
    options: [
    { value: 'learn', label: 'Learn the ropes' },
    { value: 'grow_wealth', label: 'Grow wealth' },
    { value: 'income', label: 'Generate income' },
    { value: 'preserve', label: 'Preserve capital' },
    { value: 'retirement', label: 'Retirement' },
  ] },
  { key: 'risk_comfort', title: 'How much risk are you comfortable with?', required: true,
    why: 'Risk means how much an investment can swing in value. Knowing your comfort keeps suggestions inside it.',
    options: [
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
  ] },
  { key: 'time_horizon', title: 'What is your time horizon?', required: true,
    why: 'How long you plan to stay invested. Short horizons need caution; long ones can ride out dips.',
    options: [
    { value: 'short', label: 'Short (under 1 yr)' },
    { value: 'medium', label: 'Medium (1–5 yrs)' },
    { value: 'long', label: 'Long (5+ yrs)' },
  ] },
  { key: 'preferred_style', title: 'Which style fits you?', required: true,
    why: 'Steady leans on established companies; growth accepts bigger swings chasing faster gains; balanced sits between.',
    options: [
    { value: 'steady', label: 'Steady' },
    { value: 'balanced', label: 'Balanced' },
    { value: 'growth', label: 'Growth' },
  ] },
  { key: 'liquidity_need', title: 'How soon might you need the money? (optional)',
    why: 'Money you may need soon should not sit in swingy investments.',
    options: [
    { value: 'low', label: 'Not soon' },
    { value: 'medium', label: 'Maybe' },
    { value: 'high', label: 'Could be soon' },
  ] },
  { key: 'options_experience', title: 'Options experience? (optional)',
    why: 'Options are an advanced, higher-risk practice area — ArthOS only surfaces it if you want it.',
    options: [
    { value: 'none', label: 'None' },
    { value: 'learning', label: 'Learning' },
    { value: 'experienced', label: 'Experienced' },
  ] },
];

const REQUIRED = QUESTIONS.filter((q) => q.required).map((q) => q.key);

export function ProfilePage() {
  const navigate = useNavigate();
  const { authenticated, loading: sessionLoading } = useSession();

  const [values, setValues] = useState<Partial<ProfileData>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (sessionLoading) return;
    if (!authenticated) { setLoading(false); return; }
    getProfile()
      .then((r) => { if (alive) setValues(r.profile); })
      .catch(() => {})
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [authenticated, sessionLoading]);

  const canSave = REQUIRED.every((k) => values[k]) && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await saveProfile(values);
      navigate('/portfolio');
    } catch {
      setError("Couldn't save your profile. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  if (!sessionLoading && !authenticated) {
    return (
      <ArthosPage topBarEyebrow="Profile">
        <div className="max-w-md mx-auto">
          <h1 className="font-display ink-primary" style={{ fontSize: 26, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif" }}>
            Sign in to set up your profile
          </h1>
          <p className="ink-muted mt-2" style={{ fontSize: 14 }}>
            Your profile is private to your account.
          </p>
          <Link to="/account" className="inline-block mt-5 rounded-lg px-4 h-10 leading-10 font-medium"
            style={{ backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)', fontSize: 14 }}>
            Sign in
          </Link>
        </div>
      </ArthosPage>
    );
  }

  return (
    <ArthosPage topBarEyebrow="Profile">
      <div className="max-w-xl mx-auto">
        <h1 className="font-display ink-primary" style={{ fontSize: 28, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif" }}>
          A few questions
        </h1>
        <p className="ink-muted mt-2" style={{ fontSize: 14 }}>
          This helps ArthOS tailor what it shows you later. Practice only — nothing here is financial advice, and nothing real is at risk.
        </p>

        {loading ? (
          <p className="ink-fainter mt-8" style={{ fontSize: 13 }}>Loading…</p>
        ) : (
          <div className="mt-8 space-y-7">
            {QUESTIONS.map((q) => (
              <div key={q.key} role="radiogroup" aria-label={q.title}>
                <p className="font-medium ink-primary mb-1" style={{ fontSize: 14 }}>{q.title}</p>
                <p className="ink-fainter mb-2.5" style={{ fontSize: 12, lineHeight: 1.5 }}>
                  {q.why}
                </p>
                <div className="flex flex-wrap gap-2">
                  {q.options.map((o) => {
                    const active = values[q.key] === o.value;
                    return (
                      <button
                        key={o.value}
                        role="radio"
                        aria-checked={active}
                        onClick={() => setValues((v) => ({ ...v, [q.key]: o.value }))}
                        className="rounded-full px-3.5 h-9 font-medium transition-colors"
                        style={{
                          fontSize: 13,
                          border: active ? '1px solid var(--brand)' : '1px solid var(--border)',
                          backgroundColor: active ? 'var(--brand)' : 'transparent',
                          color: active ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
                        }}
                      >
                        {active && <span aria-hidden>✓ </span>}
                        {o.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            {error && (
              <p role="alert" style={{ fontSize: 13, color: 'oklch(0.70 0.14 25)' }}>{error}</p>
            )}

            <p className="ink-fainter" style={{ fontSize: 12 }} aria-live="polite">
              {REQUIRED.filter((k) => values[k]).length} of {REQUIRED.length} required questions answered.
            </p>
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => void handleSave()}
                disabled={!canSave}
                className="rounded-lg px-5 h-11 font-semibold transition-opacity"
                style={{
                  backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)', fontSize: 14,
                  opacity: canSave ? 1 : 0.5, cursor: canSave ? 'pointer' : 'not-allowed',
                }}
              >
                {saving ? 'Saving…' : 'Save profile'}
              </button>
              <button
                onClick={() => navigate('/discover')}
                className="rounded-lg px-4 h-11 font-medium"
                style={{ color: 'var(--muted-foreground)', fontSize: 14 }}
              >
                Skip for now
              </button>
            </div>
          </div>
        )}
      </div>
    </ArthosPage>
  );
}
