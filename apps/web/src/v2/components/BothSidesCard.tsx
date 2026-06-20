// Bull-vs-Bear "both sides" card (P0-1, investor-demo flagship).
//
// Shows, for one recommendation: Why bulls like it / Why bears worry /
// Why ArthOS still likes it — all derived from the recommendation's REAL
// stored evidence (see bullBear deriver). Beginner-legible plain language;
// no raw engine jargon. If there is no usable evidence, renders nothing.

import { MetaLabel } from '../chrome/ArthosChrome';
import { bullBear, type SidePoint } from '../lib/bullBear';
import type { RecApi } from '@/lib/operator/hooks';

const BULL = 'var(--brand)';
const BEAR = 'oklch(0.70 0.14 75)';

function actionTone(action: string): string {
  const a = action.toLowerCase();
  if (a === 'buy') return BULL;
  if (a === 'sell' || a === 'trim') return BEAR;
  return 'var(--ink-muted, #6b6b6b)';
}

function Side({
  title, count, unit, color, glyph, points,
}: { title: string; count: number; unit: string; color: string; glyph: string; points: SidePoint[] }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <span aria-hidden style={{ color, fontSize: 11 }}>{glyph}</span>
        <span className="text-[13px] font-semibold ink-primary">{title}</span>
        <span
          className="tabular-nums text-[11px] px-1.5 py-0.5 rounded-full"
          style={{ color, background: 'color-mix(in oklab, currentColor 12%, transparent)' }}
        >
          {count} {unit}{count === 1 ? '' : 's'}
        </span>
      </div>
      {points.length === 0 ? (
        <p className="ink-muted text-[14px] leading-relaxed">None flagged for this idea.</p>
      ) : (
        <ul className="space-y-2.5">
          {points.slice(0, 4).map((p) => (
            <li key={p.key} className="flex items-baseline gap-2.5">
              <span aria-hidden className="shrink-0 mt-[3px] rounded-full" style={{ width: 5, height: 5, background: color }} />
              <span className="ink-primary text-[14.5px] leading-snug">{p.phrase}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function BothSidesCard({ rec }: { rec: RecApi }) {
  const bb = bullBear(rec);
  // Nothing usable to show — stay honest, render nothing.
  if (bb.bull.length === 0 && bb.bear.length === 0) return null;
  const tone = actionTone(bb.action);

  return (
    <section className="mb-12">
      <div className="flex items-center justify-between mb-1">
        <MetaLabel>Bulls vs bears</MetaLabel>
        <span
          className="text-[11px] font-semibold tracking-wide px-2 py-1 rounded-full"
          style={{ color: tone, background: 'color-mix(in oklab, currentColor 12%, transparent)' }}
        >
          ArthOS: {bb.action}
        </span>
      </div>
      <p className="ink-muted text-[14px] leading-relaxed mb-5 max-w-narrative">
        Every idea has two sides. Here's the case for and against — then where ArthOS lands.
      </p>

      <div className="rounded-xl border border-hairline overflow-hidden">
        <div className="grid sm:grid-cols-2">
          <div className="p-5 sm:p-6 border-b sm:border-b-0 sm:border-r border-hairline">
            <Side title="Why bulls like it" count={bb.bullCount} unit="signal" color={BULL} glyph="▲" points={bb.bull} />
          </div>
          <div className="p-5 sm:p-6">
            <Side title="Why bears worry" count={bb.bearCount} unit="risk" color={BEAR} glyph="▼" points={bb.bear} />
          </div>
        </div>

        <div className="border-t border-hairline p-5 sm:p-6" style={{ borderLeft: `3px solid ${tone}` }}>
          <div className="text-[12px] font-semibold uppercase tracking-wide ink-fainter mb-2">{bb.verdictLabel}</div>
          <p className="ink-primary text-[15px] leading-relaxed">{bb.verdict}</p>
          {bb.dampers.length > 0 && (
            <p className="ink-fainter text-[12.5px] mt-2.5">
              Adjusted for {bb.dampers.join(' · ')} — the call was trimmed, not taken at face value.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
