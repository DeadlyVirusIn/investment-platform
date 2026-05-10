// UX-13 — VerbGlyph component (R4 Phase 13C deliverable).
//
// 36-48pt page-chrome verb-glyph anchored at fixed (x, y) below
// 40vh hairline. SEPARATE visual category from tile schema 11px
// verb-pill (pill stays unchanged on the tile).
//
// Solo: 48pt. Duet: 36pt. Field: not rendered.
// Body-text color (NOT red/green/amber) — anti-casino mitigation.
//
// KILL-SWITCH: ?glyph=off in URL hides this entirely (Codex R4
// drift trigger — if visual validation shows action-pressure vibe,
// kill via URL flag in staging then bake into code).

import type { Verb } from "@/lib/copilot/conviction_card_schema";
import type { RoomMode } from "@/lib/copilot/living_compose";


export interface VerbGlyphProps {
  verb: Verb;
  room: RoomMode;
  killed?: boolean;
}


export default function VerbGlyph({ verb, room, killed = false }: VerbGlyphProps) {
  if (killed) return null;
  if (room === "field") return null;

  return (
    <div
      className="ux13-verb-glyph"
      data-room={room}
      data-test="ux13-verb-glyph"
      aria-hidden="true"  // tile pill is the semantic verb; this is page chrome
    >
      {verb}
    </div>
  );
}
