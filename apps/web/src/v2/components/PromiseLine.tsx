// MVP Phase A — PromiseLine.
//
// Three placements only:
//   - onboarding screen 1     (variant="hero", 16px ink-warm)
//   - Today hero bottom        (variant="signature", 13px ink-fainter, centered)
//   - Track Record subtitle    (variant="subtitle", 17px ink-muted, max-w-narrative)
//
// No bold. No quote marks. No accompanying CTA.

import { type ReactNode } from 'react';

type Variant = 'hero' | 'signature' | 'subtitle';

const STYLES: Record<Variant, { className: string; size: string }> = {
  hero: {
    className: 'font-serif italic ink-warm leading-snug max-w-narrative',
    size: 'text-[16px]',
  },
  signature: {
    className: 'font-serif italic ink-fainter leading-relaxed text-center',
    size: 'text-[13px]',
  },
  subtitle: {
    className: 'font-serif italic ink-muted leading-relaxed max-w-narrative',
    size: 'text-[17px]',
  },
};

export function PromiseLine({
  variant = 'signature',
  before,
}: {
  variant?: Variant;
  /** Optional prefix copy that grounds the promise in context.
   *  e.g. "This is the math behind the promise:" on Track Record. */
  before?: ReactNode;
}) {
  const s = STYLES[variant];
  return (
    <p className={`${s.className} ${s.size}`}>
      {before && <span className="not-italic ink-muted">{before} </span>}
      Watch an AI invest. Learn how it thinks.
    </p>
  );
}
