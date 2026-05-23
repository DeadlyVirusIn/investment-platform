// SetupStrength — 0-5 dot rating + expandable criterion list.
// Educational: each dot is a verifiable criterion the user can learn.
// No "AI confidence", no opinion — only objective signal-quality reads.

import { useState } from 'react';
import type { SetupStrength as SetupStrengthType } from '../data/arthosData';

interface Props {
  setup: SetupStrengthType;
  /** Compact = dots + score only (for tracking-list rows).
   *  Full    = dots + score + expandable criterion list (default). */
  variant?: 'full' | 'compact';
}

export function SetupStrength({ setup, variant = 'full' }: Props) {
  const [open, setOpen] = useState(false);

  const Dots = (
    <span className="inline-flex items-center gap-1" aria-hidden>
      {Array.from({ length: 5 }).map((_, i) => (
        <span
          key={i}
          className="block w-[7px] h-[7px] rounded-full"
          style={{
            backgroundColor:
              i < setup.score ? 'var(--ink-primary)' : 'transparent',
            border:
              i < setup.score ? 'none' : '1px solid var(--ink-fainter)',
          }}
        />
      ))}
    </span>
  );

  if (variant === 'compact') {
    return (
      <span
        className="inline-flex items-center gap-2 ink-fainter text-meta"
        aria-label={`Setup strength ${setup.score} of 5`}
      >
        {Dots}
        <span className="tabular-nums">
          {setup.score}/5
        </span>
      </span>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left flex items-baseline justify-between gap-4 py-3 transition-colors hover:opacity-80"
        aria-expanded={open}
      >
        <span className="text-meta ink-fainter">Setup strength</span>
        <span className="inline-flex items-center gap-3">
          {Dots}
          <span className="ink-primary text-meta tabular-nums">
            {setup.score} of 5
          </span>
          <span
            className="ink-fainter text-meta"
            aria-hidden
            style={{
              transition: 'transform 250ms',
              transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
              display: 'inline-block',
            }}
          >
            ›
          </span>
        </span>
      </button>

      {open && (
        <ul className="space-y-2 pt-3 pl-1 border-t border-hairline">
          {setup.criteria.map((c, i) => (
            <li
              key={i}
              className="flex items-baseline gap-3 text-[13px] leading-relaxed"
            >
              <span
                aria-hidden
                className={c.met ? 'ink-primary' : 'ink-fainter'}
                style={{
                  fontFamily: 'ui-monospace, monospace',
                  width: '14px',
                  flexShrink: 0,
                }}
              >
                {c.met ? '✓' : '○'}
              </span>
              <span className={c.met ? 'ink-primary' : 'ink-fainter'}>
                <span className={c.met ? '' : 'line-through opacity-70'}>
                  {c.label}
                </span>
                <span className="ink-muted ml-2">— {c.note}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
