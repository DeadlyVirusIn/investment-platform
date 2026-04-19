import { cn } from '@/lib/cn';

export type FreshnessStatus = 'fresh' | 'stale' | 'failed' | 'unknown';

interface FreshnessBadgeProps {
  status: FreshnessStatus;
  /** Optional ISO timestamp of last successful fetch */
  lastUpdated?: string;
  className?: string;
}

const STATUS_CONFIG: Record<
  FreshnessStatus,
  { label: string; classes: string }
> = {
  fresh: {
    label: 'Fresh',
    classes: 'bg-success/15 text-success border-success/30',
  },
  stale: {
    label: 'Stale',
    classes: 'bg-warning/15 text-warning border-warning/30',
  },
  failed: {
    label: 'Failed',
    classes: 'bg-danger/15 text-danger border-danger/30',
  },
  unknown: {
    label: 'Unknown',
    classes: 'bg-surface-hover text-text-muted border-surface-border',
  },
};

export default function FreshnessBadge({
  status,
  lastUpdated,
  className,
}: FreshnessBadgeProps) {
  const { label, classes } = STATUS_CONFIG[status];

  const title = lastUpdated
    ? `Last updated: ${new Date(lastUpdated).toLocaleString()}`
    : undefined;

  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border',
        classes,
        className
      )}
    >
      {/* Dot indicator */}
      <span
        className={cn('w-1.5 h-1.5 rounded-full', {
          'bg-success': status === 'fresh',
          'bg-warning': status === 'stale',
          'bg-danger': status === 'failed',
          'bg-text-muted': status === 'unknown',
        })}
      />
      {label}
    </span>
  );
}
