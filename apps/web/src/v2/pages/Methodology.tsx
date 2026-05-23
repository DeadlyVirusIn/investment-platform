// V2 Methodology — transparency surface.
//
// Editorial prose. Five sections explaining how ArthOS reaches its
// decisions, in plain English. No data dependencies, no engine reads —
// this is a written-once document the novice can trust because the
// rules are listed where they can see them.
//
// Route: /v2/methodology

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';

function FadeIn({
  delay = 0,
  children,
  className,
}: {
  delay?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.32, 0.72, 0, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function Section({
  n,
  title,
  children,
  delay,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
  delay: number;
}) {
  return (
    <FadeIn delay={delay}>
      <section className="mb-10 sm:mb-12">
        <div className="text-meta ink-fainter tabular-nums mb-2">
          {String(n).padStart(2, '0')}
        </div>
        <h2 className="font-serif ink-primary text-[24px] sm:text-[28px] leading-tight mb-4 max-w-[22ch]">
          {title}
        </h2>
        <div className="ink-muted leading-[1.7] text-[16px] sm:text-[17px] space-y-4 max-w-narrative">
          {children}
        </div>
      </section>
    </FadeIn>
  );
}

export function Methodology() {
  return (
    <ArthosPage maxWidth="max-w-3xl">
      <FadeIn>
        <PageHeader
          eyebrow="Methodology"
          title="How ArthOS reaches its decisions"
          description="The rules are listed below. They are short on purpose. If you can read the rule, you can read the trade."
        />
        <p className="ink-fainter leading-relaxed text-[14px] -mt-4 mb-12 sm:mb-16">
          5 sections · about 4 minutes
        </p>
      </FadeIn>

      <Section n={1} title="What we watch" delay={0.1}>
        <p>
          A signal is a present-tense fact — not a forecast. Six-week
          momentum has outpaced the broader index. Implied volatility
          sits in the 78th percentile of trailing prints. A cohort has
          quietly re-rated while the headlines moved elsewhere.
        </p>
        <p>
          We watch dozens of these every morning. Most do not become
          trades. Watching is cheap; trading is not.
        </p>
      </Section>

      <Section n={2} title="What turns a signal into a trade" delay={0.15}>
        <p>
          Three things must be defined without ambiguity before a
          position opens:
        </p>
        <ul className="list-disc pl-5 marker:ink-fainter space-y-2">
          <li>
            <strong className="ink-primary">Position size</strong> —
            measured against the loss we can survive, not the gain we
            can imagine.
          </li>
          <li>
            <strong className="ink-primary">Entry price</strong> — a
            specific number, not a range. If the price runs ahead of
            it, we do not chase.
          </li>
          <li>
            <strong className="ink-primary">Invalidation level</strong>{' '}
            — the line that, if crossed, retires the thesis. The exit
            decision is made before the position opens.
          </li>
        </ul>
        <p>
          If any of the three cannot be written down, the signal does
          not become a trade.
        </p>
      </Section>

      <Section n={3} title="What we don't do" delay={0.2}>
        <ul className="list-disc pl-5 marker:ink-fainter space-y-2">
          <li>We do not predict prices.</li>
          <li>
            We do not hold a position because we are up on it. Profit is
            not a thesis.
          </li>
          <li>
            We do not trade against our own written thesis. If the
            thesis is intact, we hold. If it breaks, we exit.
          </li>
          <li>
            We do not use personal data, demographics, or behavior to
            tailor what you see. Every reader sees the same lessons in
            the same order.
          </li>
        </ul>
      </Section>

      <Section n={4} title="What changes our mind" delay={0.25}>
        <p>
          The second-order assumption breaking. When the thing the
          thesis quietly depended on stops being true.
        </p>
        <p>
          Example: a regional-bank thesis depended on deposit costs
          lagging the rate cycle. When the earnings call showed
          deposit costs moving the wrong way, the thesis ended — even
          though the price had not yet moved. We exited on the
          catalyst, not the chart.
        </p>
        <p>
          We write the second-order assumption down so we can recognize
          when it breaks. Most exits should not require new
          information; they should require already-stated information
          contradicting what we expected.
        </p>
      </Section>

      <Section n={5} title="Why this is paper-only" delay={0.3}>
        <p>
          ArthOS teaches discipline. Real money distorts the lessons —
          loss aversion turns a clean exit into a held loser; greed
          turns a sized trim into a doubled-down mistake.
        </p>
        <p>
          Paper trading lets you practice the call without the
          neurochemistry. The point is not to discover whether the
          engine is right; the point is to build the muscles you will
          need before any number on the screen represents your savings.
        </p>
        <p className="ink-fainter italic">
          Nothing on this product places live orders. Nothing here is
          financial advice.
        </p>
      </Section>

      <FadeIn delay={0.4}>
        <div className="mt-16 pt-10 border-t border-hairline flex flex-wrap gap-3">
          <Link
            to="/v2/start"
            className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
          >
            Start the Day 1 flow
          </Link>
          <Link
            to="/v2/today"
            className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
          >
            Today's briefing
          </Link>
          <Link
            to="/v2/learn"
            className="inline-flex items-center px-4 py-2 surface-drawer rounded-full text-meta ink-muted hover:ink-primary transition-colors"
          >
            Browse lessons
          </Link>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
