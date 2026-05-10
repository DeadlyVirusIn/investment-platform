// UX-13 cinematic — directional pressure glyph.
//
// Single character: ↗ strengthening / ↘ weakening / · stable.
// Color matches tone tokens. Static, no animation. Communicates
// direction at scan speed without sparkline width.

import type { PressureDirection } from "@/lib/copilot/living_compose";


export interface PressureGlyphProps {
  pressure: PressureDirection;
}


export default function PressureGlyph({ pressure }: PressureGlyphProps) {
  const glyph = pressure === "strengthening" ? "↗"
              : pressure === "weakening"     ? "↘"
              : "·";

  const cls = `ux13-pressure ux13-pressure-${pressure}`;

  return (
    <span
      className={cls}
      aria-label={`Pressure ${pressure}`}
      data-test="ux13-pressure-glyph"
    >
      {glyph}
    </span>
  );
}
