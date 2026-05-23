// Section primitive — canonical vertical rhythm + optional title/action.
//
// Phase A visual-parity primitive. Logic-free.

import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface SectionProps {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Section({ title, action, children, className }: SectionProps) {
  return (
    <section className={cn('mb-10 lg:mb-14', className)}>
      {(title || action) && (
        <div className="flex items-end justify-between mb-4 gap-3">
          {title && (
            <h2 className="font-display text-[22px] lg:text-2xl ink-primary leading-tight">
              {title}
            </h2>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
