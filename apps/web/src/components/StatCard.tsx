import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Small secondary line under the primary value (e.g. "vs yesterday"). */
  secondary?: ReactNode;
  /** Optional tone for the value. */
  tone?: 'neutral' | 'positive' | 'negative' | 'accent' | 'muted';
  className?: string;
}

const TONE: Record<NonNullable<StatCardProps['tone']>, string> = {
  neutral: 'text-text-primary',
  positive: 'text-success',
  negative: 'text-danger',
  accent: 'text-accent',
  muted: 'text-text-secondary',
};

export default function StatCard({
  label,
  value,
  secondary,
  tone = 'neutral',
  className,
}: StatCardProps) {
  return (
    <div
      className={cn('px-5 py-4', className)}
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-card)',
      }}
    >
      <div className="text-[11px] font-semibold tracking-[0.08em] uppercase"
           style={{ color: 'var(--text-secondary)' }}>
        {label}
      </div>
      <div
        className={cn(
          'mt-1 font-mono tabular-nums text-[26px] leading-tight',
          TONE[tone],
        )}
      >
        {value}
      </div>
      {secondary !== undefined && (
        <div className="mt-1 text-xs"
             style={{ color: 'var(--text-muted)' }}>{secondary}</div>
      )}
    </div>
  );
}
