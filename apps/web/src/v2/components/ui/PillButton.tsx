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
  // Phase A visual-parity — primary now uses brand color; outline +
  // ghost use sage-light hover wash to match Lovable's universal
  // hover pattern.
  const variantClass =
    variant === 'primary'
      ? 'bg-[var(--brand)] text-[var(--brand-foreground)] hover:opacity-92'
      : variant === 'outline'
      ? 'border border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--sage-light)]'
      : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--sage-light)]';
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full text-[13.5px] font-semibold tracking-tight transition-colors min-h-11 focus-visible:outline-none focus-visible:ring-2',
        variantClass,
        className,
      )}
      style={{
        // Brand-tinted focus ring per Lovable
        ['--tw-ring-color' as string]: 'var(--ring)',
      }}
      {...props}
    />
  );
}
