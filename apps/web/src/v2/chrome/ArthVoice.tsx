// Arth voice primitive — glyph + first-person line.
// Three voice modes: opening (top of chapter), advisory (inside rec),
// responsive (after user action).

import type { ReactNode } from 'react';

export type ArthVoiceMode = 'opening' | 'advisory' | 'responsive';

interface ArthVoiceProps {
  mode?: ArthVoiceMode;
  children: ReactNode;
  className?: string;
}

export function ArthVoice({
  mode = 'opening',
  children,
  className = '',
}: ArthVoiceProps) {
  const modeStyles: Record<ArthVoiceMode, { size: number; lineHeight: number }> = {
    opening:    { size: 17,   lineHeight: 1.5 },
    advisory:   { size: 14.5, lineHeight: 1.55 },
    responsive: { size: 13.5, lineHeight: 1.5 },
  };
  const ms = modeStyles[mode];

  return (
    <div className={`flex items-start gap-3 ${className}`} role="note"
         aria-label="Arth says">
      <ArthGlyph />
      <p
        className="ink-primary"
        style={{
          fontSize: ms.size,
          lineHeight: ms.lineHeight,
          fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <span
          className="font-semibold uppercase mr-2"
          style={{
            fontSize: 10,
            letterSpacing: '0.16em',
            color: 'var(--brand)',
          }}
        >
          Arth
        </span>
        <span style={{ color: 'var(--foreground)' }}>{children}</span>
      </p>
    </div>
  );
}

export function ArthGlyph({ size = 24 }: { size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-flex items-center justify-center shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        backgroundColor: 'color-mix(in oklch, var(--brand) 14%, transparent)',
        color: 'var(--brand)',
        fontFamily: "'Fraunces', ui-serif, Georgia, serif",
        fontStyle: 'italic',
        fontWeight: 400,
        fontSize: Math.round(size * 0.62),
        lineHeight: 1,
        border: '1px solid color-mix(in oklch, var(--brand) 22%, transparent)',
      }}
    >
      A
    </span>
  );
}
