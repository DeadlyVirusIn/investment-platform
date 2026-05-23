// Polish pass — CollapsibleOnMobile.
//
// Wraps any downstream Today section. On desktop (>=md) renders children
// as-is. On mobile (<md) renders a calm button-row header; children
// collapse by default, expand on tap.
//
// Visual: editorial italic label + plain count, with a + / – glyph.
// No animation library. <details>/<summary> not used so we can fully
// suppress the affordance on desktop.

import { useState } from 'react';
import { useMediaQuery } from '../hooks/useMediaQuery';

interface Props {
  label: string;
  /** Optional count or short hint shown right of the label */
  hint?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export function CollapsibleOnMobile({
  label,
  hint,
  defaultOpen = false,
  children,
}: Props) {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const [open, setOpen] = useState(defaultOpen);
  const showContent = !isMobile || open;

  return (
    <section className="mb-12 md:mb-16">
      {isMobile && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-baseline justify-between gap-4 py-3 border-t border-hairline"
          aria-expanded={open}
        >
          <span className="flex items-baseline gap-3">
            <span
              className="ink-muted"
              style={{
                fontSize: '12px',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                fontWeight: 500,
              }}
            >
              {label}
            </span>
            {hint && (
              <span className="text-[12px] ink-fainter tabular-nums">
                {hint}
              </span>
            )}
          </span>
          <span
            aria-hidden
            className="ink-fainter text-[20px] leading-none transition-transform"
            style={{
              transform: open ? 'rotate(45deg)' : 'rotate(0deg)',
              transition: 'transform 220ms cubic-bezier(0.32, 0.72, 0, 1)',
            }}
          >
            +
          </span>
        </button>
      )}
      {showContent && <div className={isMobile ? 'pt-4' : ''}>{children}</div>}
    </section>
  );
}
