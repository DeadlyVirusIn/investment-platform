// UX-3D Phase A — single tone dot.
//
// One of the 5 signature elements (UX-3C §3a). Single-hue, no
// animation, no breathing, no pulse. Renders as an 8px filled
// circle. The aria-label names the tone for screen readers; the
// visible dot is the brand.

import { TONE_LABELS } from "@/lib/copilot/copy";
import type { ToneKind } from "@/lib/copilot/types";


export interface ToneDotProps {
  tone: ToneKind;
  /** Optional className passthrough; should never carry color
   *  overrides — the tone is the source of truth. */
  className?: string;
}


const TONE_TO_VAR: Record<ToneKind, string> = {
  calm: "var(--copilot-dot-calm)",
  healthy: "var(--copilot-dot-healthy)",
  waiting: "var(--copilot-dot-waiting)",
  attention: "var(--copilot-dot-attention)",
  insight: "var(--copilot-dot-insight)",
};


export default function ToneDot({ tone, className }: ToneDotProps) {
  return (
    <span
      data-test="copilot-tone-dot"
      data-tone={tone}
      role="img"
      aria-label={TONE_LABELS[tone]}
      className={className}
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: TONE_TO_VAR[tone],
        verticalAlign: "middle",
      }}
    />
  );
}
