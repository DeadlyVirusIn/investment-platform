// MVP Phase A — Onboarding stripped to 1 welcome screen.
//
// Prior 4-screen flow (Welcome / Level / Topics / Time) collected
// preferences the product never read. Phase B will wire those when
// personalization is implemented. Until then: 1 screen, promise lands,
// user drops into Today.

import { motion, AnimatePresence } from 'framer-motion';
import { useUserPrefs } from '../state/UserPrefsContext';
import { PromiseLine } from '../components/PromiseLine';

export function Onboarding() {
  const { hasOnboarded, completeOnboarding } = useUserPrefs();

  // Screenshot bypass for headless capture.
  const skip =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('skipOnboarding') === '1';

  if (hasOnboarded || skip) return null;

  const finish = () => {
    // Provide neutral defaults; level/topics/time are unread in Phase A.
    completeOnboarding('building', [], '07:00');
  };

  return (
    <AnimatePresence>
      {!hasOnboarded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 z-[100] surface-base flex items-center justify-center px-5 py-10 overflow-y-auto"
          style={{ backgroundColor: 'var(--surface-base)' }}
        >
          <div className="w-full max-w-2xl">
            <div className="text-meta ink-fainter mb-4">Welcome</div>
            <h2 className="font-serif text-masthead ink-primary leading-[1.05] mb-7 max-w-[20ch]">
              ArthOS, briefly.
            </h2>

            <p className="ink-muted leading-relaxed text-[17px] mb-4 max-w-narrative">
              Every weekday we publish a briefing — the actual decisions of a
              model portfolio, written as editorial prose. Every concept
              inside links to a lesson that teaches the idea behind it.
            </p>
            <p className="ink-muted leading-relaxed text-[17px] mb-10 max-w-narrative">
              No real money. We don't promise returns. We promise literacy —
              by Day 90, you'll understand how an investor thinks about risk,
              sizing, and the days when there's nothing to do.
            </p>

            <div className="mb-12 max-w-narrative">
              <PromiseLine variant="hero" />
            </div>

            <button
              onClick={finish}
              className="px-7 py-3.5 rounded-full font-serif text-[17px] transition-opacity"
              style={{
                backgroundColor: 'var(--ink-primary)',
                color: 'var(--surface-base)',
              }}
            >
              Begin Day 1 →
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
