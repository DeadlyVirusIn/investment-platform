import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

export default function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  contentClassName,
}: CardProps) {
  return (
    <section
      className={cn('overflow-hidden', className)}
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-card)',
      }}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between px-5 py-3"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="min-w-0">
            {title && (
              <h2 className="text-[11px] font-semibold tracking-[0.08em] uppercase"
                  style={{ color: 'var(--text-secondary)' }}>
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-xs mt-0.5 truncate"
                 style={{ color: 'var(--text-muted)' }}>{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn('px-5 py-4', contentClassName)}>{children}</div>
    </section>
  );
}
