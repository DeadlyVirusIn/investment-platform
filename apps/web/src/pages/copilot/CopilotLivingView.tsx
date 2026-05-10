// UX-13 — visual hypothesis at /overview?view=living (TRANSFORMATION PASS).
//
// Brutal-analysis fixes applied:
//   - Killed ConvictionTile chrome → HeroBlock + SubBlock (text in space)
//   - Killed VerbGlyph (Codex R4 was right; floating word IS dashboard)
//   - Killed watchlist column → inline prose ("Watching AAPL (near $172)…")
//   - Killed market band → italic continuation paragraph
//   - Warmer palette + paper-warm text + 3% amber stage tint
//   - Posture sentence dramatic clamp(40px, 5vw, 72px) Source Serif 4 light
//   - 60s ambient breath on stage tint (proves attending without stealing)
//   - Drawer opens → page blurs + dims + scales (immersive transition)
//
// Default /overview UNCHANGED. ?view=working/stream/conviction/copilot
// UNCHANGED. URL switches preserved:
//   ?view=living                   defaults to Duet
//   ?view=living&room=solo|duet|field
//   ?view=living&room=duet&drawer=NVDA   opens drawer first paint

import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";

import AIRead13 from "@/components/copilot/AIRead13";
import RoomSolo from "@/components/copilot/RoomSolo";
import RoomDuet from "@/components/copilot/RoomDuet";
import RoomField from "@/components/copilot/RoomField";
import ReasoningDrawer from "@/components/copilot/ReasoningDrawer";

import {
  composeLivingPage, PROOF_DRAWER_PAYLOADS, type RoomMode,
} from "@/lib/copilot/living_compose";
import { useDrawerUrlState } from "@/lib/copilot/useDrawerUrlState";


function parseRoom(value: string | null): RoomMode {
  if (value === "solo" || value === "duet" || value === "field") return value;
  return "duet";
}


export default function CopilotLivingView() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const room = parseRoom(params.get("room"));

  const data = useMemo(() => composeLivingPage(room), [room]);

  const { openTicker, openDrawer, closeDrawer } = useDrawerUrlState();
  const openCard = openTicker ? PROOF_DRAWER_PAYLOADS[openTicker] ?? null : null;
  const isOpen = openCard !== null;

  return (
    <div
      className={`ux13-living ux13-room-${room}`}
      data-test="ux13-living-root"
      data-room={room}
      data-drawer-open={isOpen ? "true" : "false"}
    >
      {/* Ambient breath layer (60s sine on stage tint) */}
      <div className="ux13-stage-bg" aria-hidden="true" />

      <div className="ux13-frame">
        {/* AI Read header */}
        <AIRead13 data={data} />

        {/* Room composition */}
        {room === "solo" && <RoomSolo data={data} onTileClick={openDrawer} />}
        {room === "duet" && <RoomDuet data={data} onTileClick={openDrawer} />}
        {room === "field" && <RoomField data={data} onTileClick={openDrawer} />}

        {/* Switcher (force-state nav, only in this proof) */}
        <nav className="ux13-switcher" data-test="ux13-switcher" style={{ marginTop: "var(--living-space-xl)" }}>
          <span style={{ color: "var(--living-ink-recede)" }}>force room</span>
          {(["solo", "duet", "field"] as RoomMode[]).map(r => (
            <Link
              key={r}
              to={`/overview?view=living&room=${r}`}
              data-active={room === r ? "true" : "false"}
            >
              {r}
            </Link>
          ))}
          <span style={{ color: "var(--living-ink-recede)" }}>·</span>
          <Link to="/overview?view=working">see the working →</Link>
        </nav>

        {/* Footer */}
        <footer className="ux13-footer">
          Read-only research · paper trading only · not financial advice.
          <br />
          <span style={{ opacity: 0.6 }}>
            UX-13 living-environment visual hypothesis · transformation pass · master at <code>docs/research/UX_13_LIVING_ENVIRONMENT.md</code>
          </span>
        </footer>
      </div>

      <ReasoningDrawer card={openCard} isOpen={isOpen} onClose={closeDrawer} />
    </div>
  );
}
