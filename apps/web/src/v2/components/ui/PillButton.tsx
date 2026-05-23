// Editorial pill button — primary CTA inside V2 surfaces.
//
// Ported (Phase 5) from wise-start-bloom-31433ca8/src/components/primitives.tsx.
// Token classes retargeted from Lovable's `bg-brand` / `text-ink/70` /
// `bg-sage-light/60` to V2's CSS variables. Used inside .v2-root so
// the variables resolve via the scoped palette.

import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

export function PillButton({
  className,
  variant = 'primary',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'outline';
}) {
  const variantClass =
    variant === 'primary'
      ? 'bg-[var(--ink-primary)] text-[var(--surface-base)] hover:opacity-90'
      : variant === 'outline'
      ? 'border border-[var(--hairline)] text-[var(--ink-primary)] hover:bg-[var(--surface-drawer)]'
      : 'text-[var(--ink-muted)] hover:text-[var(--ink-primary)] hover:bg-[var(--surface-drawer)]';
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full text-[13.5px] font-semibold tracking-tight transition-colors min-h-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ink-muted)]',
        variantClass,
        className,
      )}
      {...props}
    />
  );
}
