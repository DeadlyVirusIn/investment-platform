// V2 Track Record — lifetime equity, hand-rolled SVG equity curve,
// drawdown markup, hit-rate / expectancy / median-hold stats, honest
// losses, quarterly retrospectives, full closed list. No chart lib.

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { PromiseLine } from '../components/PromiseLine';
import {
  TRACK_RECORD_CLOSED,
  EQUITY_TIMELINE,
  QUARTERLY_RETROS,
  STARTING_EQUITY,
  type ClosedTrade,
} from '../data/arthosData';

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
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.32, 0.72, 0, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

interface Stats {
  total: number;
  wins: number;
  losses: number;
  hitRate: number;
  avgWinPct: number;
  avgLossPct: number;
  expectancy: number;
  largestWinPct: number;
  largestLossPct: number;
  medianHoldDays: number;
}

function computeStats(trades: ClosedTrade[]): Stats {
  const wins = trades.filter((t) => t.outcome === 'win');
  const losses = trades.filter((t) => t.outcome === 'loss');
  const hitRate = trades.length === 0 ? 0 : wins.length / trades.length;
  const avgWinPct =
    wins.length === 0
      ? 0
      : wins.reduce((s, t) => s + t.movePct, 0) / wins.length;
  const avgLossPct =
    losses.length === 0
      ? 0
      : losses.reduce((s, t) => s + t.movePct, 0) / losses.length;
  const expectancy = hitRate * avgWinPct + (1 - hitRate) * avgLossPct;
  const moves = trades.map((t) => t.movePct);
  const largestWinPct = Math.max(...moves, 0);
  const largestLossPct = Math.min(...moves, 0);
  const hold = [...trades.map((t) => t.daysHeld)].sort((a, b) => a - b);
  const medianHoldDays =
    hold.length === 0 ? 0 : hold[Math.floor(hold.length / 2)];
  return {
    total: trades.length,
    wins: wins.length,
    losses: losses.length,
    hitRate,
    avgWinPct,
    avgLossPct,
    expectancy,
    largestWinPct,
    largestLossPct,
    medianHoldDays,
  };
}

interface DrawdownPoint {
  date: string;
  equity: number;
  peak: number;
  ddPct: number;
}

function computeDrawdowns(): {
  points: DrawdownPoint[];
  maxDD: {
    depthPct: number;
    startDate: string;
    troughDate: string;
    daysToRecover?: number;
  };
} {
  let peak = EQUITY_TIMELINE[0].equity;
  const points: DrawdownPoint[] = EQUITY_TIMELINE.map((p) => {
    peak = Math.max(peak, p.equity);
    const ddPct = ((p.equity - peak) / peak) * 100;
    return { date: p.date, equity: p.equity, peak, ddPct };
  });
  let trough = points[0];
  points.forEach((p) => {
    if (p.ddPct < trough.ddPct) trough = p;
  });
  let startDate = points[0].date;
  for (let i = points.indexOf(trough); i >= 0; i--) {
    if (points[i].equity === points[i].peak) {
      startDate = points[i].date;
      break;
    }
  }
  let daysToRecover: number | undefined;
  const peakValue = trough.peak;
  for (let i = points.indexOf(trough); i < points.length; i++) {
    if (points[i].equity >= peakValue) {
      const startMs = new Date(trough.date).getTime();
      const endMs = new Date(points[i].date).getTime();
      daysToRecover = Math.round((endMs - startMs) / (1000 * 60 * 60 * 24));
      break;
    }
  }
  return {
    points,
    maxDD: {
      depthPct: trough.ddPct,
      startDate,
      troughDate: trough.date,
      daysToRecover,
    },
  };
}

export function TrackRecord() {
  const stats = useMemo(() => computeStats(TRACK_RECORD_CLOSED), []);
  const drawdownData = useMemo(computeDrawdowns, []);
  const lifetime = useMemo(() => {
    const final = EQUITY_TIMELINE[EQUITY_TIMELINE.length - 1].equity;
    return ((final - STARTING_EQUITY) / STARTING_EQUITY) * 100;
  }, []);
  const finalEquity = EQUITY_TIMELINE[EQUITY_TIMELINE.length - 1].equity;

  return (
    <ArthosPage maxWidth="max-w-copy">
      <header className="mb-14 sm:mb-16">
        <MetaLabel>Track Record</MetaLabel>
        <h1 className="font-serif text-masthead ink-primary mt-3 mb-6 max-w-[20ch]">
          The honest math.
        </h1>
        <p className="ink-muted leading-relaxed max-w-narrative mb-5">
          We show the losses with the same weight as the wins. Calibration,
          drawdowns, and the named trades that taught us something. There is
          no point to a track record that is not honest.
        </p>
        {/* MVP Phase A — promise subtitle */}
        <PromiseLine
          variant="subtitle"
          before="This is the math behind the promise:"
        />
      </header>

      <FadeIn delay={0.04}>
        <section className="mb-16">
          <MetaLabel>Lifetime</MetaLabel>
          <div className="font-serif text-headline ink-primary mt-3 tabular-nums mb-2">
            {lifetime >= 0 ? '+' : '−'}
            {Math.abs(lifetime).toFixed(2)}%
          </div>
          <p className="ink-muted text-[15px] leading-relaxed">
            From ${STARTING_EQUITY.toLocaleString()} to{' '}
            <span className="ink-primary tabular-nums">
              ${finalEquity.toLocaleString()}
            </span>{' '}
            across {EQUITY_TIMELINE.length} weeks of operation.
          </p>
        </section>
      </FadeIn>

      <FadeIn delay={0.08}>
        <section className="mb-20">
          <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
            <MetaLabel>Equity curve · weekly</MetaLabel>
            <span className="text-meta ink-fainter">
              Worst drawdown {drawdownData.maxDD.depthPct.toFixed(1)}%
              {drawdownData.maxDD.daysToRecover != null &&
                ` · recovered in ${drawdownData.maxDD.daysToRecover} days`}
            </span>
          </div>
          <EquityChart points={drawdownData.points} />
        </section>
      </FadeIn>

      <FadeIn delay={0.14}>
        <section className="mb-20">
          <MetaLabel>The numbers</MetaLabel>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-hairline mt-5 rounded-2xl overflow-hidden">
            <StatCell
              label="Hit rate"
              value={`${(stats.hitRate * 100).toFixed(0)}%`}
              sub={`${stats.wins} of ${stats.total}`}
            />
            <StatCell label="Avg win" value={`+${stats.avgWinPct.toFixed(1)}%`} />
            <StatCell label="Avg loss" value={`${stats.avgLossPct.toFixed(1)}%`} />
            <StatCell
              label="Expectancy"
              value={`${stats.expectancy >= 0 ? '+' : ''}${stats.expectancy.toFixed(2)}%`}
              sub="per trade"
            />
            <StatCell
              label="Largest win"
              value={`+${stats.largestWinPct.toFixed(1)}%`}
            />
            <StatCell
              label="Largest loss"
              value={`${stats.largestLossPct.toFixed(1)}%`}
            />
            <StatCell
              label="Median hold"
              value={`${stats.medianHoldDays}`}
              sub="days"
            />
            <StatCell label="Closed trades" value={String(stats.total)} />
          </div>
          <p className="text-[13px] ink-fainter italic leading-relaxed mt-5 max-w-narrative">
            Expectancy is the average dollar-weighted outcome per trade.
            Positive means the strategy edges in our favor on average; it does
            not promise the next trade.
          </p>
        </section>
      </FadeIn>

      <FadeIn delay={0.2}>
        <section className="mb-20">
          <MetaLabel>Honest losses</MetaLabel>
          <p className="ink-muted leading-relaxed max-w-narrative mt-5 mb-7 text-[15px]">
            These are the trades where the thesis broke or the entry was
            wrong. A track record without these is not a track record.
          </p>
          <div className="space-y-px bg-hairline">
            {TRACK_RECORD_CLOSED.filter((t) => t.outcome === 'loss').map(
              (trade) => (
                <article
                  key={`${trade.symbol}-${trade.closed}`}
                  className="surface-drawer py-7 px-7"
                >
                  <div className="flex items-baseline justify-between gap-4 mb-3 flex-wrap">
                    <div className="flex items-baseline gap-3">
                      <span className="font-mono ink-primary">
                        {trade.symbol}
                      </span>
                      <span className="ink-muted">·</span>
                      <span className="font-serif text-[18px] ink-primary">
                        {trade.company}
                      </span>
                    </div>
                    <div className="text-meta ink-fainter tabular-nums">
                      {trade.opened} → {trade.closed} · {trade.daysHeld} days
                    </div>
                  </div>
                  <div className="ink-muted text-[15px] tabular-nums mb-3">
                    <span className="ink-primary mr-1">▼</span>
                    {trade.movePct.toFixed(1)}%
                  </div>
                  <p className="ink-muted leading-relaxed max-w-narrative">
                    {trade.exitReason}
                  </p>
                </article>
              )
            )}
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.26}>
        <section className="mb-20">
          <MetaLabel>Quarterly retrospectives</MetaLabel>
          <p className="ink-muted leading-relaxed max-w-narrative mt-5 mb-9 text-[15px]">
            Once a quarter, we write what we got right, what we got wrong, and
            what we changed. The point of a retrospective is not to feel good.
            It is to learn.
          </p>
          <div className="space-y-14">
            {QUARTERLY_RETROS.map((retro) => (
              <article key={retro.quarter}>
                <div className="text-meta ink-fainter mb-2">{retro.label}</div>
                <h3 className="font-serif text-subhead ink-primary leading-snug mb-4">
                  {retro.theme}
                </h3>
                {retro.body.map((p, i) => (
                  <p
                    key={i}
                    className="ink-muted leading-relaxed max-w-narrative mb-3 text-[15px]"
                  >
                    {p}
                  </p>
                ))}
                <div className="mt-5 pl-4 border-l-2 border-hairline">
                  <div className="text-meta ink-fainter mb-1.5">
                    What we got wrong
                  </div>
                  <p className="ink-muted text-[14px] leading-relaxed max-w-narrative italic">
                    {retro.honestMiss}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </section>
      </FadeIn>

      <FadeIn delay={0.32}>
        <section className="mb-20">
          <MetaLabel>All closed positions</MetaLabel>
          <ul className="mt-7 space-y-px bg-hairline">
            {TRACK_RECORD_CLOSED.slice()
              .sort((a, b) => b.closed.localeCompare(a.closed))
              .map((trade) => (
                <li
                  key={`${trade.symbol}-${trade.closed}`}
                  className="surface-base py-5 flex items-baseline justify-between gap-4 flex-wrap"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-3 mb-1.5">
                      <span className="font-mono ink-primary text-[14px]">
                        {trade.symbol}
                      </span>
                      <span className="ink-muted text-[13px] truncate">
                        {trade.company}
                      </span>
                    </div>
                    <div className="text-meta ink-fainter tabular-nums">
                      {trade.closed} · {trade.daysHeld} days ·{' '}
                      {trade.statedHorizon}-horizon
                    </div>
                  </div>
                  <div className="text-right tabular-nums shrink-0">
                    <div className="ink-primary text-[14px]">
                      <span className="mr-1">
                        {trade.movePct >= 0 ? '▲' : '▼'}
                      </span>
                      {trade.movePct >= 0 ? '+' : ''}
                      {trade.movePct.toFixed(1)}%
                    </div>
                    <div className="text-meta ink-fainter mt-1">
                      {trade.outcome}
                    </div>
                  </div>
                </li>
              ))}
          </ul>
        </section>
      </FadeIn>

      <div className="border-t border-hairline pt-12">
        <p className="font-serif italic ink-muted text-[18px] leading-[1.6] max-w-narrative">
          The number that matters most in a track record is not the return. It
          is how we behaved on the worst day.
        </p>
      </div>
    </ArthosPage>
  );
}

function StatCell({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="surface-drawer p-5 sm:p-6">
      <div className="text-meta ink-fainter mb-2.5">{label}</div>
      <div className="font-serif text-[24px] sm:text-[28px] ink-primary leading-none tabular-nums">
        {value}
      </div>
      {sub && <div className="text-[11px] ink-fainter mt-1.5">{sub}</div>}
    </div>
  );
}

function EquityChart({ points }: { points: DrawdownPoint[] }) {
  const width = 800;
  const height = 240;
  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const equities = points.map((p) => p.equity);
  const min = Math.min(...equities);
  const max = Math.max(...equities);
  const range = max - min || 1;
  const ySteps = 4;
  const x = (i: number) => pad.left + (i / (points.length - 1)) * innerW;
  const y = (eq: number) =>
    pad.top + innerH - ((eq - min) / range) * innerH;
  const linePoints = points
    .map((p, i) => `${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`)
    .join(' ');
  const areaPoints = `${pad.left},${pad.top + innerH} ${linePoints} ${pad.left + innerW},${pad.top + innerH}`;
  const troughIdx = points.findIndex(
    (p) => p.ddPct === Math.min(...points.map((pt) => pt.ddPct))
  );
  const trough = points[troughIdx];
  return (
    <div className="overflow-x-auto -mx-2 sm:mx-0">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full min-w-[600px] ink-primary"
        style={{ height: 'auto' }}
      >
        {Array.from({ length: ySteps + 1 }).map((_, i) => {
          const eq = min + (range / ySteps) * i;
          const yy = y(eq);
          return (
            <g key={i}>
              <line
                x1={pad.left}
                x2={pad.left + innerW}
                y1={yy}
                y2={yy}
                stroke="currentColor"
                strokeOpacity={0.08}
                strokeWidth={1}
              />
              <text
                x={pad.left - 10}
                y={yy + 4}
                textAnchor="end"
                fill="currentColor"
                fillOpacity={0.5}
                fontSize="10"
                fontFamily="Inter"
              >
                ${(eq / 1000).toFixed(0)}k
              </text>
            </g>
          );
        })}

        <polygon points={areaPoints} fill="currentColor" opacity={0.06} />
        <polyline
          points={linePoints}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.9}
        />

        {trough && (
          <g>
            <circle
              cx={x(troughIdx)}
              cy={y(trough.equity)}
              r={4}
              fill="currentColor"
              opacity={0.4}
            />
            <circle
              cx={x(troughIdx)}
              cy={y(trough.equity)}
              r={2.5}
              fill="currentColor"
            />
            <text
              x={x(troughIdx)}
              y={y(trough.equity) + 20}
              textAnchor="middle"
              fill="currentColor"
              fillOpacity={0.6}
              fontSize="10"
              fontFamily="Inter"
            >
              −{Math.abs(trough.ddPct).toFixed(1)}%
            </text>
          </g>
        )}

        {[0, Math.floor(points.length / 2), points.length - 1].map((i) => (
          <text
            key={i}
            x={x(i)}
            y={height - 8}
            textAnchor="middle"
            fill="currentColor"
            fillOpacity={0.5}
            fontSize="10"
            fontFamily="Inter"
          >
            {points[i].date.slice(5)}
          </text>
        ))}
      </svg>
    </div>
  );
}
