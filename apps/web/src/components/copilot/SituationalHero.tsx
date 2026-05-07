// UX-3D Phase A — Situational Hero.
//
// One of the 5 signature elements (UX-3C §3a). Renders the single
// editorial sentence at the top of Copilot home.
//
// Pure render: receives a HeroCopy envelope from derive.deriveHero()
// and renders the dot + sentence with the matching pacing state.
// Never animated. Length capped upstream by deriveHero. Carries the
// data-source attribute for audit.

import ToneDot from "./ToneDot";
import type { HeroCopy } from "@/lib/copilot/types";


export interface SituationalHeroProps {
  hero: HeroCopy;
  /** Optional small meta line beneath the hero (e.g. session marker). */
  meta?: string;
  className?: string;
}


export default function SituationalHero(
  { hero, meta, className }: SituationalHeroProps,
) {
  return (
    <header
      data-test="copilot-situational-hero"
      data-pacing={hero.pacing}
      data-tone={hero.tone}
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        paddingBlock: "var(--copilot-negative-space-baseline)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <ToneDot tone={hero.tone} />
        <p
          data-test="copilot-situational-hero-sentence"
          data-source={hero.dataSource}
          style={{
            margin: 0,
            fontSize: "var(--copilot-pacing-hero-size)",
            fontWeight: "var(--copilot-pacing-hero-weight)" as
              unknown as number,
            lineHeight: 1.4,
            color: "inherit",
            maxWidth: "var(--copilot-prose-max-width)",
          }}
        >
          {hero.sentence}
        </p>
      </div>
      {meta && (
        <div
          data-test="copilot-situational-hero-meta"
          style={{
            fontSize: "var(--copilot-type-12)",
            opacity: 0.6,
            paddingLeft: 20,  // dot width + gap, keeps meta aligned
          }}
        >
          {meta}
        </div>
      )}
    </header>
  );
}
