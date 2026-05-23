// RiskBadge — 3-tone risk indicator pill with leading dot.
//
// Phase A visual-parity primitive. Logic-free.

import { cn } from '@/lib/cn';

type Risk = 'low' | 'medium' | 'high';

const TONE_STYLE: Record<Risk, React.CSSProperties> = {
  low: {
    backgroundColor: 'color-mix(in oklch, var(--brand) 15%, transparent)',
    color: 'var(--brand)',
  },
  medium: {
    backgroundColor: 'color-mix(in oklch, var(--accent) 20%, transparent)',
    color: 'var(--accent-foreground)',
  },
  high: {
    backgroundColor:
      'color-mix(in oklch, var(--destructive) 15%, transparent)',
    color: 'var(--destructive)',
  },
};

export function RiskBadge({
  risk,
  className,
}: {
  risk: Risk;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.14em]',
        className,
      )}
      style={TONE_STYLE[risk]}
    >
      <span
        className="size-1.5 rounded-full"
        style={{ backgroundColor: 'currentColor' }}
        aria-hidden
      />
      {risk} risk
    </span>
  );
}
