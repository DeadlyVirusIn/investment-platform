// V2 Catalysts — forward-looking "why now" surface.
//
// P6E.2B truth pass: the fabricated CATALYSTS_AHEAD events and the
// static MarketPulse strip are no longer rendered. The page keeps its
// route and shell, and states honestly that catalyst tracking is not
// wired to the live engine yet. A live API exists (`/catalysts/top`,
// see `lib/catalysts/hooks.ts`) — wiring it is the follow-up.

import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';

function FadeIn({
  delay = 0,
  children,
}: {
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function Catalysts() {
  return (
    <ArthosPage maxWidth="max-w-6xl">
      <FadeIn>
        <header className="mb-10">
          <MetaLabel>Catalysts</MetaLabel>
          <h1 className="font-serif text-masthead ink-primary mt-3 mb-4 max-w-[20ch]">
            Why now.
          </h1>
          <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
            The events ahead that could move what we hold or what we're
            considering. Every event carries our disposition — what we're
            doing about it — so the page reads as decisions, not as a calendar.
          </p>
        </header>
      </FadeIn>

      {/* Honest empty state — no live data source connected yet */}
      <FadeIn delay={0.06}>
        <div className="border-t border-hairline pt-12">
          <p className="font-serif italic ink-muted text-[18px] leading-relaxed max-w-narrative">
            Catalyst tracking is not yet connected to the live engine.
          </p>
          <p className="ink-fainter leading-relaxed max-w-narrative mt-4 text-[14px]">
            When it is, the events shown here will come from the same engine
            that produces today's recommendations — nothing illustrative,
            nothing hand-written.
          </p>
        </div>
      </FadeIn>

      {/* Footer doctrine */}
      <FadeIn delay={0.12}>
        <div className="border-t border-hairline pt-12 mt-16">
          <p className="font-serif italic ink-muted text-[16px] leading-relaxed max-w-narrative">
            A catalyst is not a trade. It is a moment that updates a thesis.
            The work is knowing which one — before the date arrives.
          </p>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
