/**
 * Compact horizontal bar showing per-factor contributions to the composite
 * score. Positive contributions are green, negative red. Widths are
 * proportional to |contribution| within the row (max 100%).
 */

type Contrib = Record<string, number>;


const FACTOR_LABELS: Record<string, string> = {
  rm60: 'Mom 60d',
  rm20: 'Mom 20d',
  sector: 'Sector',
  trend: 'Trend',
  vol: 'Vol',
};


export default function FactorContribBar({
  contributions,
}: {
  contributions: Contrib | null | undefined;
}) {
  if (!contributions || Object.keys(contributions).length === 0) {
    return null;
  }

  const entries = Object.entries(contributions).filter(([_, v]) =>
    Number.isFinite(v),
  );
  if (entries.length === 0) return null;

  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v))) || 1;

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {entries.map(([key, value]) => {
        const pct = Math.round((Math.abs(value) / maxAbs) * 100);
        const isPos = value >= 0;
        const barCls = isPos
          ? 'bg-success/70 border-success/30'
          : 'bg-danger/70 border-danger/30';
        const label = FACTOR_LABELS[key] ?? key;
        const tip = `${label}: ${value >= 0 ? '+' : ''}${value.toFixed(3)}`;
        return (
          <div
            key={key}
            className="flex items-center gap-1 text-[10px] text-text-muted"
            title={tip}
          >
            <span className="w-12">{label}</span>
            <div className="w-16 h-1.5 bg-surface-hover rounded-sm overflow-hidden">
              <div
                className={`h-full border-r ${barCls}`}
                style={{ width: `${Math.max(pct, 4)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}


export function parseContributions(
  factorBreakdown: unknown,
): Contrib | null {
  if (!factorBreakdown || typeof factorBreakdown !== 'object') return null;
  const fb = factorBreakdown as Record<string, unknown>;
  const raw = fb.contributions;
  if (!raw || typeof raw !== 'object') return null;
  const out: Contrib = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    const n = Number(v);
    if (Number.isFinite(n)) out[k] = n;
  }
  return Object.keys(out).length > 0 ? out : null;
}
