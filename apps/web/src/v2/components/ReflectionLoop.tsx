// Reflection Loop (P0-4, investor-demo).
//
// For every COMPLETED recommendation (a closed paper position joined back to
// the recommendation that opened it): What we expected / What happened /
// What we learned. Every line is templated from REAL stored outcome fields
// (action, confidence, hold days, realized P/L, exit reason) — NOT LLM prose,
// no fabricated commentary.

import { MetaLabel } from '../chrome/ArthosChrome';
import {
  useCanonicalStockPortfolio,
  useClosedRecommendations,
  type ClosedRecommendation,
} from '@/lib/operator/hooks';

const POS = 'var(--brand)';
const NEG = 'oklch(0.70 0.14 75)';

function usd(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const s = n < 0 ? '-' : '+';
  return `${s}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function humanizeExit(reason: string | null): string | null {
  if (!reason) return null;
  const r = reason.toLowerCase();
  if (r.includes('stop_loss') || r.includes('stop loss')) return 'it hit its stop-loss';
  if (r.includes('flipped to trim') || r.includes('flipped to sell')) return 'the engine flipped the call to step back';
  if (r.includes('take_profit') || r.includes('target')) return 'it reached the profit target';
  if (r.includes('max_hold') || r.includes('time')) return 'the holding window ran out';
  if (r.includes('flipped')) return 'the signals reversed';
  return null;
}

function expected(it: ClosedRecommendation): string {
  const action = (it.action ?? 'position').toLowerCase();
  const conf = it.confidence != null ? `${Math.round(it.confidence)}% confidence` : null;
  return `A ${action}${conf ? ` at ${conf}` : ''} — ArthOS expected this to work out over the coming weeks.`;
}

function happened(it: ClosedRecommendation): string {
  const win = (it.realized_pnl ?? 0) >= 0;
  const days = it.hold_days;
  const held = days == null ? '' : ` after ${days} day${days === 1 ? '' : 's'}`;
  const exit = humanizeExit(it.exit_reason);
  return `It closed ${win ? 'up' : 'down'} ${usd(it.realized_pnl)}${held}${exit ? `, when ${exit}` : ''}.`;
}

function learned(it: ClosedRecommendation): string {
  const win = (it.realized_pnl ?? 0) >= 0;
  const r = (it.exit_reason ?? '').toLowerCase();
  if (r.includes('stop_loss') || r.includes('stop loss'))
    return 'The stop-loss did its job — the loss was capped when the price broke its line. Cutting losers fast is the discipline that protects the book.';
  if (r.includes('flipped'))
    return 'The engine reversed its own call when the evidence changed, instead of clinging to a thesis that had broken. Updating on new data beats stubbornness.';
  if (win)
    return 'The thesis played out — letting a working idea run paid off. Logged so the engine keeps weighting setups like this.';
  return 'It underperformed. The outcome is logged so the engine can learn which setups to trust less next time.';
}

function Block({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div className="text-meta ink-fainter mb-1">{label}</div>
      <p className="ink-primary text-[14px] leading-snug">{text}</p>
    </div>
  );
}

export function ReflectionLoop() {
  const { data: book } = useCanonicalStockPortfolio();
  const { data } = useClosedRecommendations(book?.portfolio_id);
  const items = data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <section className="mb-12">
      <MetaLabel>Reflections</MetaLabel>
      <p className="ink-muted text-[14px] leading-relaxed mt-2 mb-5 max-w-narrative">
        What we learned from closed ideas — {items.length} resolved. Every line is built
        from the real recorded outcome, not after-the-fact commentary.
      </p>

      <div className="space-y-7">
        {items.map((it) => {
          const win = (it.realized_pnl ?? 0) >= 0;
          return (
            <div key={it.rec_id} className="border-t border-hairline pt-4">
              <div className="flex items-baseline justify-between mb-3">
                <span className="font-serif ink-primary text-[17px]">
                  {it.symbol}{it.name ? ` · ${it.name}` : ''}
                </span>
                <span className="tabular-nums text-[14px] font-medium" style={{ color: win ? POS : NEG }}>
                  {usd(it.realized_pnl)}
                </span>
              </div>
              <div className="grid sm:grid-cols-3 gap-x-6 gap-y-4">
                <Block label="What we expected" text={expected(it)} />
                <Block label="What happened" text={happened(it)} />
                <Block label="What we learned" text={learned(it)} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
