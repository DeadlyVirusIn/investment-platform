import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

type Tone = 'neutral' | 'positive' | 'negative' | 'warning' | 'info' | 'accent' | 'muted';

interface BadgeProps {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}

const TONE: Record<Tone, string> = {
  neutral:  'bg-surface-hover text-text-primary border-surface-border',
  positive: 'bg-success/10 text-success border-success/30',
  negative: 'bg-danger/10 text-danger border-danger/30',
  warning:  'bg-warning/10 text-warning border-warning/30',
  info:     'bg-info/10 text-info border-info/30',
  accent:   'bg-accent/10 text-accent border-accent/30',
  muted:    'bg-surface-hover text-text-muted border-surface-border',
};

export default function Badge({ children, tone = 'neutral', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border leading-tight uppercase tracking-wider',
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function actionTone(action: string): Tone {
  switch (action) {
    case 'Buy': return 'positive';
    case 'Sell': return 'negative';
    case 'Trim': return 'warning';
    case 'Watch': return 'info';
    case 'Hold': return 'muted';
    default: return 'neutral';
  }
}

export function confidenceTone(label: string | null | undefined): Tone {
  switch (label) {
    case 'High': return 'positive';
    case 'Medium': return 'warning';
    case 'Low': return 'muted';
    default: return 'neutral';
  }
}
