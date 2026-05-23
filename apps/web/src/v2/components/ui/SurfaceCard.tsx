// SurfaceCard primitive — replaces ad-hoc `surface-drawer` utility
// styling across V2 pages. Three variants mirror Lovable:
//   default   — bg-card border-ink/5
//   muted     — sage-light wash with subtle border
//   highlight — primary card with brand-tinted ring
//
// Phase A visual-parity primitive. Logic-free.

import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';

type Variant = 'default' | 'muted' | 'highlight';

export interface SurfaceCardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  as?: 'div' | 'section' | 'article' | 'aside';
  children: ReactNode;
}

const VARIANT_CLASS: Record<Variant, string> = {
  default: 'card-elevated',
  muted: 'card-muted',
  highlight: 'card-highlight',
};

export function SurfaceCard({
  variant = 'default',
  as = 'div',
  className,
  children,
  ...rest
}: SurfaceCardProps) {
  const Comp = as as 'div';
  return (
    <Comp
      className={cn(VARIANT_CLASS[variant], 'p-5 sm:p-6', className)}
      {...rest}
    >
      {children}
    </Comp>
  );
}
