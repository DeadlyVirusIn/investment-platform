// StatusPanel — reusable state panel for the global UX states (loading /
// empty / stale / degraded / error / success / owner-only). Every panel
// answers: what happened, is anything unsafe or lost, what to do next.
// Never color-only: each variant pairs its tone with a glyph + explicit text.

import type { ReactNode } from 'react';

export type StatusVariant = 'info' | 'success' | 'warn' | 'error';

const TONES: Record<StatusVariant, { color: string; glyph: string }> = {
  info: { color: 'var(--muted-foreground)', glyph: 'ℹ' },
  success: { color: 'var(--brand)', glyph: '✓' },
  warn: { color: 'oklch(0.70 0.14 75)', glyph: '⚠' },
  error: { color: 'oklch(0.62 0.19 25)', glyph: '⚠' },
};

export function StatusPanel({
  variant = 'info', title, children, action, role,
}: {
  variant?: StatusVariant;
  /** One-line "what happened". */
  title: string;
  /** Detail: whether anything is unsafe/lost + what to do next. */
  children?: ReactNode;
  /** Optional CTA (link/button) rendered under the copy. */
  action?: ReactNode;
  /** a11y role — pass "status" (polite) or "alert" (assertive) when the
   *  panel appears dynamically. */
  role?: 'status' | 'alert';
}) {
  const t = TONES[variant];
  return (
    <div role={role} className="rounded-xl px-4 py-3 max-w-narrative" style={{
      backgroundColor: `color-mix(in oklch, ${t.color} 8%, transparent)`,
      border: `1px solid color-mix(in oklch, ${t.color} 26%, transparent)`,
    }}>
      <p className="text-[13.5px] font-semibold flex items-start gap-2" style={{ color: 'var(--foreground)' }}>
        <span aria-hidden style={{ color: t.color }}>{t.glyph}</span>
        <span>{title}</span>
      </p>
      {children && (
        <div className="ink-muted text-[12.5px] leading-relaxed mt-1 pl-6">{children}</div>
      )}
      {action && <div className="mt-2.5 pl-6">{action}</div>}
    </div>
  );
}
