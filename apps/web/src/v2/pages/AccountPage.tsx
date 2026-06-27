// M2 — minimal account surface: sign in / sign up / signed-in state.
// Reuses the existing design tokens + ArthosPage shell. No onboarding,
// no profile, no personalization — just authentication.

import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { useSession } from '../state/SessionContext';
import { login as apiLogin, signup as apiSignup } from '../../lib/auth';
import { getProfile } from '../../lib/profile';
import { sendSignal } from '../../lib/feedback';

const MIN_PASSWORD = 8; // matches backend hash_password minimum

type Mode = 'login' | 'signup';

export function AccountPage() {
  const navigate = useNavigate();
  const { user, authenticated, loading: sessionLoading, refresh, signOut } = useSession();

  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileComplete, setProfileComplete] = useState<boolean | null>(null);
  const [betaSent, setBetaSent] = useState(false);

  useEffect(() => {
    if (!authenticated) { setProfileComplete(null); return; }
    let alive = true;
    getProfile().then((r) => { if (alive) setProfileComplete(r.complete); }).catch(() => {});
    return () => { alive = false; };
  }, [authenticated]);

  const emailValid = /\S+@\S+/.test(email.trim());
  const passwordValid = password.length >= MIN_PASSWORD;
  const canSubmit = emailValid && passwordValid && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'signup') {
        await apiSignup(email.trim(), password, displayName.trim() || undefined);
      } else {
        await apiLogin(email.trim(), password);
      }
      await refresh();
      // New users go to onboarding; returning users back to their portfolio.
      navigate(mode === 'signup' ? '/profile' : '/portfolio');
    } catch {
      // Generic error — never reveal whether the email exists or is locked out.
      setError(
        mode === 'signup'
          ? "Couldn't create that account. Try a different email."
          : 'Invalid email or password.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  // Already signed in → show account state + sign out.
  if (authenticated && user) {
    return (
      <ArthosPage topBarEyebrow="Account">
        <div className="max-w-md mx-auto">
          <h1 className="font-display ink-primary" style={{ fontSize: 28, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif" }}>
            Your account
          </h1>
          <p className="ink-muted mt-2" style={{ fontSize: 14 }}>
            Signed in as <span className="ink-primary font-medium">{user.email ?? user.display_name ?? 'you'}</span>.
            Your practice portfolio is private to this account.
          </p>
          {profileComplete === false && (
            <Link
              to="/profile"
              className="block mt-5 rounded-xl p-4"
              style={{ border: '1px solid var(--border)', backgroundColor: 'color-mix(in oklch, var(--brand) 6%, transparent)' }}
            >
              <p className="font-medium ink-primary" style={{ fontSize: 14 }}>Complete your profile →</p>
              <p className="ink-muted mt-1" style={{ fontSize: 12.5 }}>
                A few quick questions so ArthOS can tailor what it shows you. Optional.
              </p>
            </Link>
          )}
          {profileComplete === true && (
            <p className="ink-muted mt-4" style={{ fontSize: 13 }}>
              Profile complete. <Link to="/profile" className="ink-primary underline">Edit</Link>
            </p>
          )}
          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={() => navigate('/portfolio')}
              className="rounded-lg px-4 h-10 font-medium"
              style={{ backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)', fontSize: 14 }}
            >
              Go to my portfolio
            </button>
            <button
              onClick={async () => { await signOut(); navigate('/discover'); }}
              className="rounded-lg px-4 h-10 font-medium"
              style={{ border: '1px solid var(--border)', color: 'var(--muted-foreground)', fontSize: 14 }}
            >
              Log out
            </button>
          </div>
          {/* M5 — lightweight beta-interest signal (collect-only; non-blocking). */}
          <div className="mt-8 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
            {betaSent ? (
              <p className="ink-muted" style={{ fontSize: 13 }}>Thanks — we'll keep you posted on beta access.</p>
            ) : (
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="ink-muted" style={{ fontSize: 13 }}>Interested in early beta access?</p>
                <button
                  onClick={() => { setBetaSent(true); sendSignal('account', 'beta_interest', 'yes').catch(() => {}); }}
                  className="rounded-lg px-4 h-9 font-medium"
                  style={{ border: '1px solid var(--border)', color: 'var(--foreground)', fontSize: 13 }}
                >
                  I'm interested
                </button>
              </div>
            )}
          </div>
        </div>
      </ArthosPage>
    );
  }

  return (
    <ArthosPage topBarEyebrow="Account">
      <div className="max-w-md mx-auto">
        <h1 className="font-display ink-primary" style={{ fontSize: 28, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif" }}>
          {mode === 'login' ? 'Sign in' : 'Create your account'}
        </h1>
        <p className="ink-muted mt-2" style={{ fontSize: 14 }}>
          {mode === 'login'
            ? 'Access your private practice portfolio.'
            : 'Free practice account — nothing real at risk.'}
        </p>

        <div className="mt-6 space-y-4">
          {mode === 'signup' && (
            <Field label="Name (optional)">
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
                style={inputStyle}
              />
            </Field>
          )}
          <Field label="Email">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              inputMode="email"
              style={inputStyle}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmit(); }}
            />
          </Field>
          <Field label="Password" hint={mode === 'signup' ? `At least ${MIN_PASSWORD} characters` : undefined}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              style={inputStyle}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmit(); }}
            />
          </Field>

          {error && (
            <p role="alert" style={{ fontSize: 13, color: 'oklch(0.70 0.14 25)' }}>
              {error}
            </p>
          )}

          <button
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            className="w-full rounded-lg h-11 font-semibold transition-opacity"
            style={{
              backgroundColor: 'var(--brand)',
              color: 'var(--brand-foreground)',
              fontSize: 14,
              opacity: canSubmit ? 1 : 0.5,
              cursor: canSubmit ? 'pointer' : 'not-allowed',
            }}
          >
            {submitting ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>

          <p className="ink-muted text-center" style={{ fontSize: 13 }}>
            {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button
              onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(null); }}
              className="ink-primary font-medium underline"
              style={{ fontSize: 13 }}
            >
              {mode === 'login' ? 'Sign up' : 'Sign in'}
            </button>
          </p>
        </div>

        {sessionLoading && (
          <p className="ink-fainter text-center mt-4" style={{ fontSize: 12 }}>Checking session…</p>
        )}
      </div>
    </ArthosPage>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  height: 44,
  padding: '0 14px',
  fontSize: 14,
  borderRadius: 8,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--surface)',
  color: 'var(--foreground)',
};

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block font-medium ink-primary mb-1.5" style={{ fontSize: 12.5 }}>{label}</span>
      {children}
      {hint && <span className="block ink-fainter mt-1" style={{ fontSize: 11.5 }}>{hint}</span>}
    </label>
  );
}
