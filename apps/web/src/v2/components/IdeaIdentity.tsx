// IdeaIdentity — shared, beginner-safe identity bits for a stock/option idea.
//
// TickerBadge:  a clear, standalone ticker chip (e.g. "JBHT") so a first-time
//   investor spots the symbol immediately, instead of it hiding inside the
//   company-name parentheses. Filled high-contrast pill = unmistakable.
// FreshnessLine: honest "Idea generated <date>" + a subtle, non-scary
//   "Awaiting next market close" note when the idea isn't from the latest
//   trading day. Never fabricates a market-data date the payload doesn't carry.

type BadgeSize = 'sm' | 'md' | 'lg';

export function TickerBadge({
  symbol,
  size = 'md',
}: {
  symbol?: string | null;
  size?: BadgeSize;
}) {
  if (!symbol) return null;
  const dims =
    size === 'lg'
      ? { padding: '5px 11px', fontSize: 15 }
      : size === 'sm'
        ? { padding: '2px 7px', fontSize: 11 }
        : { padding: '3px 9px', fontSize: 12.5 };
  return (
    <span
      className="inline-flex items-center font-mono font-semibold rounded-md uppercase"
      style={{
        ...dims,
        letterSpacing: '0.03em',
        lineHeight: 1,
        backgroundColor: 'var(--foreground)',
        color: 'var(--background)',
        whiteSpace: 'nowrap',
      }}
    >
      {symbol.toUpperCase()}
    </span>
  );
}

/** Hours after which an idea reads as "not from the latest trading day". */
const STALE_HOURS = 30;

function isOlderThanLatestClose(generatedAt?: string | null, stale?: boolean | null): boolean {
  if (stale === true) return true;
  if (!generatedAt) return false;
  const t = new Date(generatedAt).getTime();
  if (!Number.isFinite(t)) return false;
  return (Date.now() - t) / 3_600_000 > STALE_HOURS;
}

function shortDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return null;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function FreshnessLine({
  generatedAt,
  stale,
  className,
}: {
  generatedAt?: string | null;
  stale?: boolean | null;
  className?: string;
}) {
  const gen = shortDate(generatedAt);
  const awaiting = isOlderThanLatestClose(generatedAt, stale);
  if (!gen && !awaiting) return null;
  return (
    <div
      className={`flex items-center gap-x-2.5 gap-y-1 flex-wrap ${className ?? ''}`.trim()}
      style={{ fontSize: 11, color: 'var(--muted-foreground)' }}
    >
      {gen && (
        <span className="tabular-nums">
          Idea generated <span style={{ color: 'var(--foreground)' }}>{gen}</span>
        </span>
      )}
      {awaiting && (
        <span
          className="inline-flex items-center rounded-full"
          style={{
            fontSize: 10.5,
            padding: '1px 8px',
            // Soft amber — informative, not alarming.
            color: 'oklch(0.62 0.12 75)',
            backgroundColor: 'color-mix(in oklch, oklch(0.70 0.14 75) 12%, transparent)',
            border: '1px solid color-mix(in oklch, oklch(0.70 0.14 75) 26%, transparent)',
          }}
        >
          Awaiting next market close
        </span>
      )}
    </div>
  );
}
