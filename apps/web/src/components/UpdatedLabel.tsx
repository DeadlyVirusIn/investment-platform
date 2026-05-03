import { useEffect, useState } from 'react';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/cn';

interface UpdatedLabelProps {
  /** When the underlying data was fetched. TanStack Query's `dataUpdatedAt`
   * (ms epoch) or an ISO string. */
  at: number | string | Date | null | undefined;
  className?: string;
  /** Re-tick the label every N ms so "just now" → "1m ago" updates. */
  tickMs?: number;
}

/**
 * Subtle "Updated Xm ago" timestamp. Visually quiet — secondary color, 10px,
 * uppercase-tracking to blend with card-header style. Updates on an interval
 * so the relative phrase stays current without refetching data.
 */
export default function UpdatedLabel({
  at,
  className,
  tickMs = 30_000,
}: UpdatedLabelProps) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick(t => t + 1), tickMs);
    return () => window.clearInterval(id);
  }, [tickMs]);

  if (at === null || at === undefined || at === 0) return null;

  return (
    <span
      className={cn(
        'text-[10px] uppercase tracking-wider text-text-muted font-normal',
        className,
      )}
      title={new Date(at).toLocaleString()}
    >
      Updated {formatRelative(at)}
    </span>
  );
}
