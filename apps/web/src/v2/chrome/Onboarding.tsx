// MVP Phase A — Onboarding stripped to 1 welcome screen.
//
// Prior 4-screen flow (Welcome / Level / Topics / Time) collected
// preferences the product never read. Phase B will wire those when
// personalization is implemented. Until then: 1 screen, promise lands,
// then the user is routed into the guided Day 1 flow (/v2/start).

import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useUserPrefs } from '../state/UserPrefsContext';
import { PromiseLine } from '../components/PromiseLine';

export function Onboarding() {
  const { hasOnboarded, completeOnboarding } = useUserPrefs();
  const navigate = useNavigate();

  // Screenshot bypass for headless capture.
  const skip =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('skipOnboarding') === '1';

  if (hasOnboarded || skip) return null;

  const finish = () => {
    // Provide neutral defaults; level/topics/time are unread in Phase A.
    completeOnboarding('building', [], '07:00');
    // UX Phase 2 — drop the first-time visitor into the guided Day 1
    // flow rather than the magazine-style Learn home. Returning visitors
    // (hasOnboarded=true) skip this gate and land on whichever route
    // they navigated to directly.
    navigate('/start');
  };

  // First-run escape hatch — reviewers / curious visitors who want to see
  // today's idea + the track record immediately, without the guided lesson.
  const seeIdea = () => {
    completeOnboarding('building', [], '07:00');
    navigate('/discover');
  };

  return (
    <AnimatePresence>
      {!hasOnboarded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 z-[100] surface-base flex items-start sm:items-center justify-center px-5 pt-8 pb-10 overflow-y-auto"
          style={{ backgroundColor: 'var(--surface-base)' }}
        >
          <div className="w-full max-w-2xl">
            <div
              className="inline-block px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest mb-5"
              style={{
                backgroundColor: 'color-mix(in oklch, var(--brand) 12%, transparent)',
                color: 'var(--brand)',
              }}
            >
              Welcome
            </div>
            <h2 className="font-serif text-masthead ink-primary leading-[1.05] mb-4 max-w-[20ch]">
              Your AI Investing Copilot.
            </h2>

            <p className="ink-muted leading-relaxed text-[16px] mb-3 max-w-narrative">
              ArthOS walks you through one investing idea every day. We read
              the market, write the thesis, and explain the reasoning in
              plain English — so you build the investing instincts a great
              copilot needs.
            </p>
            <p className="ink-muted leading-relaxed text-[16px] mb-6 max-w-narrative">
              Nothing real is at stake. We don't promise returns. We promise
              literacy — by Day 90, you'll understand how an investor thinks
              about risk, sizing, and the days when there's nothing to do.
            </p>

            {/* P1 — CTA above the value-prop atmosphere so "Begin Day 1" is
                visible without scrolling on mobile. PromiseLine moves below.
                Primary = guided lesson; secondary = jump straight to today's
                idea (reviewers / curious visitors). */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
              <button
                onClick={finish}
                className="h-12 px-7 rounded-full text-[15px] font-semibold tracking-tight transition-colors hover:opacity-92"
                style={{
                  backgroundColor: 'var(--brand)',
                  color: 'var(--brand-foreground)',
                }}
              >
                Begin Day 1 →
              </button>
              <button
                onClick={seeIdea}
                className="text-[14px] font-semibold transition-colors hover:opacity-80"
                style={{ color: 'var(--brand)', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                See today's idea first →
              </button>
            </div>
            <p className="mt-3 ink-fainter text-[13px] leading-relaxed max-w-narrative">
              <strong className="ink-muted">Begin Day 1</strong> is a guided first session — four short
              steps, about 27 minutes in total. Stop at any step; progress is saved on this device.
              Paper-only; nothing real is at stake.
            </p>

            <div className="mt-10 max-w-narrative">
              <PromiseLine variant="hero" />
            </div>

            {/* Trust strip — anchors the page and states the three promises
                up front (presentation only; all from existing messaging). */}
            <div className="mt-12 pt-6 border-t border-hairline grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-2xl">
              {[
                { k: 'Plain English', v: 'Every idea — the thesis, both sides, and the risks — explained without jargon.' },
                { k: 'Paper-only', v: 'Practice money, nothing real at stake. We never promise returns.' },
                { k: 'Your own proof', v: 'A real, auditable track record that grows as your ideas resolve.' },
              ].map((f) => (
                <div key={f.k}>
                  <div className="text-[12px] font-semibold uppercase tracking-wide ink-primary mb-1.5">{f.k}</div>
                  <p className="ink-muted text-[13.5px] leading-snug">{f.v}</p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
