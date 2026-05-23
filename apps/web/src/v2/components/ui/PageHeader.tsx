// PageHeader primitive — canonical page-top pattern.
//
// Layout: brand-pill eyebrow + display-serif masthead + muted
// description + optional progress bar. Replaces the per-page
// MetaLabel + h1 + p improvisation across the V2 surface.
//
// Phase A visual-parity primitive. Logic-free.

import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface PageHeaderProps {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  progress?: number; // 0-100 inclusive
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  progress,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn('mb-8 lg:mb-12', className)}>
      {eyebrow && (
        <span
          className="inline-block px-3.5 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-[0.16em] mb-5"
          style={{
            backgroundColor:
              'color-mix(in oklch, var(--brand) 14%, transparent)',
            color: 'var(--brand)',
          }}
        >
          {eyebrow}
        </span>
      )}
      <h1 className="font-display text-4xl sm:text-5xl lg:text-[56px] leading-[1.05] mb-4 text-balance ink-primary">
        {title}
      </h1>
      {description && (
        <p className="text-base lg:text-lg ink-muted leading-relaxed max-w-narrative">
          {description}
        </p>
      )}
      {typeof progress === 'number' && (
        <div className="mt-5 flex items-center gap-3">
          <div
            className="h-1 w-32 rounded-full overflow-hidden"
            style={{ backgroundColor: 'var(--sage-light)' }}
          >
            <div
              className="h-full transition-all duration-700"
              style={{
                width: `${Math.max(0, Math.min(100, progress))}%`,
                backgroundColor: 'var(--brand)',
              }}
            />
          </div>
          <span className="text-[11px] font-mono ink-muted tabular-nums">
            {Math.round(progress)}%
          </span>
        </div>
      )}
    </header>
  );
}
