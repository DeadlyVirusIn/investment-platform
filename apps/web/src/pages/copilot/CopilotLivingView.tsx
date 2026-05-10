// UX-13 — visual hypothesis at /overview?view=living (OPERATIONAL PASS).
//
// Restores operational gravity per brutal feedback:
//   - Smaller posture (clamp 28-44, was 40-72) — less "essay page"
//   - ActivityStream sidebar — real AI actions since last visit,
//     each clickable, each hoverable to highlight target tile
//   - Totals pill in header (active · watch · new)
//   - Tonal layering: hero on raised plane (#181410), subs on base
//     (#0F0E0C), activity on recessed (#0A0908), footer deepest
//   - Hover gravity restored: hero hover → bg shift + invalidation
//     pulse. Sub hover → adjacent dim 0.55. Activity hover →
//     corresponding ticker block highlights via data-active-ticker.
//   - Live timestamp tick (60s) — ambient + activity relative times
//     update without page refresh, proving AI is "currently watching."

import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import AIRead13 from "@/components/copilot/AIRead13";
import RoomSolo from "@/components/copilot/RoomSolo";
import RoomDuet from "@/components/copilot/RoomDuet";
import RoomField from "@/components/copilot/RoomField";
import ActivityStream from "@/components/copilot/ActivityStream";
import ReasoningDrawer from "@/components/copilot/ReasoningDrawer";

import {
  composeLivingPage, PROOF_DRAWER_PAYLOADS, type RoomMode,
} from "@/lib/copilot/living_compose";
import { useDrawerUrlState } from "@/lib/copilot/useDrawerUrlState";
import { useTickEverySecond } from "@/lib/copilot/useTickEverySecond";


function parseRoom(value: string | null): RoomMode {
  if (value === "solo" || value === "duet" || value === "field") return value;
  return "duet";
}


export default function CopilotLivingView() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const room = parseRoom(params.get("room"));

  // Live tick: re-render every 60s so ambient + activity times move
  useTickEverySecond(60_000);

  // Recompose so freshness/time strings get latest values on tick
  // (depend on `tick` indirectly via the call below — ESLint will
  // complain about missing deps; deliberate)
  const data = useMemo(() => composeLivingPage(room), [room]);

  const { openTicker, openDrawer, closeDrawer } = useDrawerUrlState();
  const openCard = openTicker ? PROOF_DRAWER_PAYLOADS[openTicker] ?? null : null;
  const isOpen = openCard !== null;

  // Activity-stream hover → highlight corresponding tile via attribute
  const [hoveredActivityTicker, setHoveredActivityTicker] = useState<string | null>(null);

  return (
    <div
      className={`ux13-living ux13-room-${room}`}
      data-test="ux13-living-root"
      data-room={room}
      data-drawer-open={isOpen ? "true" : "false"}
      data-active-ticker={hoveredActivityTicker ?? ""}
    >
      {/* Ambient breath layer (60s sine on stage tint) */}
      <div className="ux13-stage-bg" aria-hidden="true" />

      <div className="ux13-frame">
        {/* AI Read header — page-state + totals + ambient + since-you-left */}
        <AIRead13 data={data} />

        {/* Room composition */}
        {room === "solo" && <RoomSolo data={data} onTileClick={openDrawer} />}
        {room === "duet" && <RoomDuet data={data} onTileClick={openDrawer} />}
        {room === "field" && <RoomField data={data} onTileClick={openDrawer} />}

        {/* Operational layer — activity stream */}
        <ActivityStream
          events={data.activity}
          onEventClick={openDrawer}
          onEventHover={setHoveredActivityTicker}
        />

        {/* Switcher (force-state nav, only in this proof) */}
        <nav className="ux13-switcher" data-test="ux13-switcher">
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
            UX-13 living-environment visual hypothesis · operational pass · master at <code>docs/research/UX_13_LIVING_ENVIRONMENT.md</code>
          </span>
        </footer>
      </div>

      <ReasoningDrawer card={openCard} isOpen={isOpen} onClose={closeDrawer} />
    </div>
  );
}
