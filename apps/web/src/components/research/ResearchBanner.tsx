// Phase 11W (Phase B) - mandatory banner on every research surface.
// Required prop on every research-aware component. Render-time guard
// throws if the prop is missing (enforced by client tests).
//
// Wording is FROZEN. Any change requires a Phase audit + sign-off.

import { RESEARCH_BANNER_TEXT } from '@/lib/research/forbiddenTokens';

export interface ResearchBannerProps {
  // Must be passed explicitly. The presence of the prop signals that
  // the consuming component knowingly handles research-only data.
  context: 'tab' | 'pulse' | 'jobs-health';
}

export default function ResearchBanner({ context }: ResearchBannerProps) {
  if (!context) {
    // Defensive: TS already enforces this, but render-time check keeps
    // a hard failure path for dynamic JSX.
    throw new Error(
      'ResearchBanner requires a `context` prop (tab | pulse | jobs-health).',
    );
  }
  return (
    <div
      role="note"
      aria-label="Research note safety banner"
      className="research-banner"
      data-research-context={context}
      style={{
        backgroundColor: '#fff8e1',
        border: '1px solid #ffd54f',
        borderRadius: 4,
        color: '#5d4037',
        fontSize: 13,
        padding: '8px 12px',
        marginBottom: 12,
      }}
    >
      <strong>⚠ </strong>
      {RESEARCH_BANNER_TEXT}
    </div>
  );
}
