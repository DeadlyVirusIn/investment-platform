// UX-10 Phase 10A — VerbPill primitive.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 3.2 (verb visual treatment)
//
// 11px uppercase, monochrome, sharp corners. Single neutral
// color regardless of verb. The verb is a label of state, NOT
// a button. Does not navigate. Does not trigger orders. The
// Cockpit page handles all interaction.

import type { Verb } from "@/lib/copilot/conviction_card_schema";


export interface VerbPillProps {
  verb: Verb;
}


export default function VerbPill({ verb }: VerbPillProps) {
  return (
    <span
      className="ux10-verb"
      data-verb={verb}
      data-test="ux10-verb-pill"
      aria-label={`AI recommendation: ${verb}`}
    >
      {verb}
    </span>
  );
}
