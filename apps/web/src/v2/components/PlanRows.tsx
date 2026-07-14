// PlanRows — beginner-safe "Plan" block for a stock idea (Sprint K).
// Renders Entry / Target / Exit if wrong / Timeframe from ideaPlan(rec).
// Shared by LiveTodayHero, Opportunities RecCard, and PickPage so the four
// labels and the estimate disclaimer stay identical everywhere.

import { ideaPlan } from '../lib/ideaPlan';
import type { RecApi } from '@/lib/operator/hooks';

const ROWS: { key: 'entry' | 'target' | 'exit' | 'timeframe'; label: string }[] = [
  { key: 'entry', label: 'Entry' },
  { key: 'target', label: 'Target' },
  { key: 'exit', label: 'Exit if wrong' },
  { key: 'timeframe', label: 'Timeframe' },
];

export function PlanRows({
  rec, compact = false,
}: {
  rec: RecApi;
  compact?: boolean;
}) {
  const plan = ideaPlan(rec);
  const valueSize = compact ? 12.5 : 13.5;
  const labelSize = compact ? 11 : 11.5;

  return (
    <div>
      <ul className="space-y-0">
        {plan.lastClose && (
          <li
            className="grid grid-cols-[88px_1fr] gap-3 items-baseline py-2"
            style={{ borderTop: '1px solid var(--border)' }}>
            <span className="font-semibold uppercase"
              style={{ fontSize: labelSize, letterSpacing: '0.08em', color: 'var(--muted-foreground)' }}>
              Last close
            </span>
            <span className="ink-primary tabular-nums" style={{ fontSize: valueSize, lineHeight: 1.5 }}>
              {plan.lastClose}
            </span>
          </li>
        )}
        {ROWS.map(({ key, label }) => (
          <li key={key}
            className="grid grid-cols-[88px_1fr] gap-3 items-baseline py-2"
            style={{ borderTop: '1px solid var(--border)' }}>
            <span className="font-semibold uppercase"
              style={{ fontSize: labelSize, letterSpacing: '0.08em', color: 'var(--muted-foreground)' }}>
              {label}
            </span>
            <span className="ink-primary tabular-nums" style={{ fontSize: valueSize, lineHeight: 1.5 }}>
              {plan[key]}
            </span>
          </li>
        ))}
      </ul>
      <p className="ink-fainter mt-2" style={{ fontSize: 11, lineHeight: 1.5 }}>
        {plan.estimate
          ? 'Paper planning estimate from price and how much it typically moves — not investment advice. Practice it in paper first.'
          : 'ArthOS gives the decision, not exact prices yet — choose your own levels and practice in paper first.'}
      </p>
    </div>
  );
}
