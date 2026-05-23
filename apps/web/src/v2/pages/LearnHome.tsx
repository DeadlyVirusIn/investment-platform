// V2 Learn Home — daily landing. Hero lesson + week dots + Today's
// Briefing card + Paper Book teaser + Continue your path + All paths
// + This week stats + What is ArthOS footer.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowUpRight, BookOpen, Sparkles, Wallet } from 'lucide-react';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { Sparkline, sparkFromSymbol } from '../components/Sparkline';
import { PATHS, LESSONS, GLOSSARY, PORTFOLIO } from '../data/arthosData';
import { usePaperBook } from '../state/PaperBook';

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

function timeOfDayGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return 'Late evening';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  if (h < 21) return 'Good evening';
  return 'Late evening';
}

export function LearnHome() {
  const { bookValue, positions, startingCash } = usePaperBook();
  const featuredLesson = LESSONS.find(
    (l) => l.slug === 'why-great-investors-do-nothing-most-days'
  )!;
  const featuredPath = PATHS.find((p) => p.slug === 'risk-literacy')!;
  const featuredPathLessons = LESSONS.filter(
    (l) => l.pathSlug === featuredPath.slug
  );
  const readInPath = featuredPathLessons.filter((l) => l.read).length;
  const totalInPath = featuredPath.lessonSlugs.length;
  const lifetimePct = ((bookValue - startingCash) / startingCash) * 100;
  const totalLessonsRead = LESSONS.filter((l) => l.read).length;
  const weekProgress = 4;
  const dayCount = 12;

  return (
    <ArthosPage>
      <FadeIn>
        <section className="flex items-end justify-between mb-12 sm:mb-14 flex-wrap gap-y-6">
          <div>
            <div className="text-meta ink-fainter mb-2">
              Day {dayCount} of reading
            </div>
            <h1 className="font-serif text-headline ink-primary leading-[1.05]">
              {timeOfDayGreeting()}.
            </h1>
          </div>
          <WeekProgress filled={weekProgress} total={7} />
        </section>
      </FadeIn>

      <FadeIn delay={0.06}>
        <Link
          to={`/v2/learn/lesson/${featuredLesson.slug}`}
          className="block card-elevated p-7 sm:p-10 mb-5 group relative overflow-hidden"
        >
          <div className="flex items-start justify-between gap-6 mb-7">
            <div className="text-meta ink-fainter flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />
              Today's lesson
            </div>
            <span className="text-meta ink-fainter">
              {featuredLesson.readMinutes} min
            </span>
          </div>
          <h2 className="font-serif text-masthead ink-primary leading-[1.05] mb-6 max-w-[18ch]">
            {featuredLesson.title}
          </h2>
          <p className="ink-muted leading-relaxed max-w-narrative mb-6 text-[15px]">
            While you were away, we trimmed AMAT. Here's the idea behind why we
            did it — and why it's the most underused habit a beginner has.
          </p>
          <div className="inline-flex items-center gap-1.5 ink-primary text-meta group-hover:opacity-70 transition-opacity">
            Read this
            <ArrowUpRight
              className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
              strokeWidth={1.5}
            />
          </div>
          <div
            className="absolute -top-20 -right-20 w-72 h-72 rounded-full pointer-events-none"
            style={{
              background:
                'radial-gradient(circle, var(--warm-glow), transparent 70%)',
              opacity: 0.6,
            }}
            aria-hidden
          />
        </Link>
      </FadeIn>

      <FadeIn delay={0.12}>
        <div className="grid sm:grid-cols-2 gap-5 mb-16 sm:mb-20">
          <Link
            to="/v2/today"
            className="block card-elevated p-7 group relative overflow-hidden"
          >
            <div className="flex items-center justify-between mb-5">
              <div className="text-meta ink-fainter flex items-center gap-2">
                <BookOpen className="w-3.5 h-3.5" strokeWidth={1.5} />
                Today's briefing
              </div>
              <span className="text-meta ink-fainter">
                Edition #{PORTFOLIO.edition}
              </span>
            </div>
            <div className="font-serif text-subhead ink-primary leading-snug mb-4">
              5 placements on the desk
            </div>
            <p className="ink-muted text-[14px] leading-relaxed mb-6">
              {PORTFOLIO.dateLong}. The portfolio held twelve positions and
              trimmed one. New ideas are on the desk for paper-trading.
            </p>
            <div className="flex items-center gap-2 text-meta ink-primary group-hover:opacity-70 transition-opacity">
              <span className="tabular-nums">
                <span className="mr-1">▲</span>+
                {PORTFOLIO.dayMovePct.toFixed(2)}% on the day
              </span>
              <span className="ml-auto inline-flex items-center gap-1.5">
                Open <ArrowUpRight className="w-3.5 h-3.5" strokeWidth={1.5} />
              </span>
            </div>
          </Link>

          <Link
            to="/v2/portfolio"
            className="block card-elevated p-7 group relative overflow-hidden"
          >
            <div className="flex items-center justify-between mb-5">
              <div className="text-meta ink-fainter flex items-center gap-2">
                <Wallet className="w-3.5 h-3.5" strokeWidth={1.5} />
                Your paper book
              </div>
              <span className="text-meta ink-fainter">$100k start</span>
            </div>
            <div className="font-serif text-subhead ink-primary leading-snug mb-1 tabular-nums">
              $
              {bookValue.toLocaleString(undefined, {
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
              })}
            </div>
            <div className="text-[13px] ink-muted tabular-nums mb-5">
              {positions.length} open · {lifetimePct >= 0 ? '+' : '−'}
              {Math.abs(lifetimePct).toFixed(2)}% since Day 1
            </div>
            <div className="h-6 ink-muted mb-5">
              <Sparkline
                values={sparkFromSymbol('PAPER-BOOK', 28)}
                width={220}
                height={24}
                strokeWidth={1}
                filled
              />
            </div>
            <div className="flex items-center gap-2 text-meta ink-primary group-hover:opacity-70 transition-opacity">
              {positions.length === 0
                ? 'Place your first trade'
                : 'Open your book'}
              <ArrowUpRight className="w-3.5 h-3.5 ml-auto" strokeWidth={1.5} />
            </div>
          </Link>
        </div>
      </FadeIn>

      <FadeIn delay={0.18}>
        <section className="mb-16">
          <MetaLabel>Continue your path</MetaLabel>
          <div className="block card-elevated p-7 mt-5">
            <div className="flex items-baseline justify-between gap-6 mb-5 flex-wrap">
              <div>
                <div className="text-meta ink-fainter mb-2">
                  {featuredPath.tier}
                </div>
                <h3 className="font-serif text-subhead ink-primary leading-snug">
                  {featuredPath.title}
                </h3>
              </div>
              <div className="text-[13px] ink-muted tabular-nums">
                {readInPath} of {totalInPath} read
              </div>
            </div>
            <div className="h-[3px] bg-hairline rounded-full overflow-hidden mb-5">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${(readInPath / Math.max(1, totalInPath)) * 100}%`,
                  backgroundColor: 'var(--ink-primary)',
                }}
              />
            </div>
            <p className="ink-muted text-[14px] leading-relaxed max-w-narrative mb-5">
              {featuredPath.synopsis}
            </p>
            <Link
              to={`/v2/learn/lesson/${featuredLesson.slug}`}
              className="inline-flex items-center gap-1.5 ink-primary text-meta hover:opacity-70 transition-opacity"
            >
              Continue
              <ArrowUpRight className="w-3.5 h-3.5" strokeWidth={1.5} />
            </Link>
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.24}>
        <section className="mb-16">
          <div className="flex items-baseline justify-between mb-5">
            <MetaLabel>All paths</MetaLabel>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {PATHS.filter((p) => p.slug !== featuredPath.slug).map((path) => {
              const lessonsInPath = LESSONS.filter(
                (l) => l.pathSlug === path.slug
              );
              const readCount = lessonsInPath.filter((l) => l.read).length;
              const total = path.lessonSlugs.length;
              const firstLesson = lessonsInPath[0];
              const target = firstLesson
                ? `/v2/learn/lesson/${firstLesson.slug}`
                : '/v2/learn';
              return (
                <Link
                  key={path.slug}
                  to={target}
                  className="block card-elevated p-6 group"
                >
                  <div className="text-meta ink-fainter mb-3">{path.tier}</div>
                  <h4 className="font-serif text-[20px] ink-primary leading-snug mb-3">
                    {path.title}
                  </h4>
                  <p className="ink-muted text-[13px] leading-relaxed mb-5 line-clamp-2">
                    {path.synopsis}
                  </p>
                  <div className="flex items-center justify-between text-meta ink-fainter">
                    <span>
                      {total === 0 ? 'Coming soon' : `${readCount} of ${total}`}
                    </span>
                    <ArrowUpRight
                      className="w-3.5 h-3.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform"
                      strokeWidth={1.5}
                    />
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.3}>
        <section className="mb-16">
          <MetaLabel>This week</MetaLabel>
          <div className="grid grid-cols-3 gap-px bg-hairline mt-5 rounded-2xl overflow-hidden">
            <Stat label="Lessons read" value={String(totalLessonsRead)} />
            <Stat
              label="Days reading"
              value={String(weekProgress)}
              suffix="of 7"
            />
            <Stat label="Glossary terms" value={String(GLOSSARY.length)} />
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.36}>
        <section className="border-t border-hairline pt-12">
          <MetaLabel>What is ArthOS</MetaLabel>
          <p className="ink-muted leading-relaxed max-w-narrative mt-5 text-[15px]">
            A learning-first investing product. Every weekday we publish a
            briefing — the actual decisions of a model portfolio, written as
            editorial prose — and every concept inside it links to a lesson
            that teaches the idea behind it. No real money is involved. We
            don't promise returns. We promise literacy.
          </p>
        </section>
      </FadeIn>
    </ArthosPage>
  );
}

function WeekProgress({ filled }: { filled: number; total: number }) {
  const days = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
  return (
    <div className="flex items-center gap-3">
      <div className="text-meta ink-fainter">This week</div>
      <div className="flex gap-1.5">
        {days.map((d, i) => (
          <div key={i} className="flex flex-col items-center gap-1">
            <div
              className={`w-2 h-2 rounded-full ${i < filled ? '' : 'opacity-30'}`}
              style={{ backgroundColor: 'var(--ink-primary)' }}
            />
            <span className="text-[9px] ink-fainter tracking-wider">{d}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string;
  suffix?: string;
}) {
  return (
    <div className="surface-drawer p-6 sm:p-7">
      <div className="text-meta ink-fainter mb-3">{label}</div>
      <div className="font-serif text-[28px] ink-primary leading-none tabular-nums">
        {value}
        {suffix && (
          <span className="text-[14px] ink-fainter ml-1.5 font-sans">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}
