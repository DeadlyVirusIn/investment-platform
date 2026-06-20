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

function SideList({ points, color, glyph }: { points: SidePoint[]; color: string; glyph: string }) {
  if (points.length === 0) {
    return <p className="ink-muted text-[14px] leading-relaxed mt-3">None flagged for this idea.</p>;
  }
  return (
    <ul className="space-y-3 mt-3">
      {points.slice(0, 4).map((p) => (
        <li key={p.key} className="flex items-baseline gap-3 border-t border-hairline pt-3">
          <span aria-hidden style={{ color, fontSize: 12 }}>{glyph}</span>
          <span className="ink-primary text-[15px] leading-snug">{p.phrase}</span>
        </li>
      ))}
    </ul>
  );
}

export function BothSidesCard({ rec }: { rec: RecApi }) {
  const bb = bullBear(rec);
  // Nothing usable to show — stay honest, render nothing.
  if (bb.bull.length === 0 && bb.bear.length === 0) return null;

  return (
    <section className="mb-12">
      <MetaLabel>Bulls vs bears</MetaLabel>
      <p className="ink-muted text-[14px] leading-relaxed mt-2 mb-5 max-w-narrative">
        Every idea has two sides. Here is the case for and against — then where
        ArthOS lands and why.
      </p>

      <div className="grid sm:grid-cols-2 gap-x-8 gap-y-6">
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[13px] font-medium" style={{ color: BULL }}>
              Why bulls like it
            </span>
            <span className="ink-fainter tabular-nums text-[12px]">
              {bb.bullCount} signal{bb.bullCount === 1 ? '' : 's'}
            </span>
          </div>
          <SideList points={bb.bull} color={BULL} glyph="▲" />
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[13px] font-medium" style={{ color: BEAR }}>
              Why bears worry
            </span>
            <span className="ink-fainter tabular-nums text-[12px]">
              {bb.bearCount} risk{bb.bearCount === 1 ? '' : 's'}
            </span>
          </div>
          <SideList points={bb.bear} color={BEAR} glyph="▼" />
        </div>
      </div>

      <div className="mt-7 rounded-lg border border-hairline p-5 max-w-narrative">
        <div className="text-[13px] font-medium ink-primary mb-2">{bb.verdictLabel}</div>
        <p className="ink-muted text-[15px] leading-relaxed">{bb.verdict}</p>
      </div>
    </section>
  );
}
