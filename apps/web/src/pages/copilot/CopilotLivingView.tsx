// UX-13 — visual hypothesis at /overview?view=living (CINEMATIC + HEAT PASS).
//
// Adds: MarketPulseBar (top), CatalystStrip (above hero), conviction
// sparklines + pressure glyphs in tile eyebrows. Activity stream
// retained from operational pass. Live tick (60s) keeps relative-
// times moving without animation.

import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import AIRead13 from "@/components/copilot/AIRead13";
import RoomSolo from "@/components/copilot/RoomSolo";
import RoomDuet from "@/components/copilot/RoomDuet";
import RoomField from "@/components/copilot/RoomField";
import ActivityStream from "@/components/copilot/ActivityStream";
import MarketPulseBar from "@/components/copilot/MarketPulseBar";
import CatalystStrip from "@/components/copilot/CatalystStrip";
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

  useTickEverySecond(60_000);

  const data = useMemo(() => composeLivingPage(room), [room]);

  const { openTicker, openDrawer, closeDrawer } = useDrawerUrlState();
  const openCard = openTicker ? PROOF_DRAWER_PAYLOADS[openTicker] ?? null : null;
  const isOpen = openCard !== null;

  const [hoveredActivityTicker, setHoveredActivityTicker] = useState<string | null>(null);

  return (
    <div
      className={`ux13-living ux13-room-${room}`}
      data-test="ux13-living-root"
      data-room={room}
      data-drawer-open={isOpen ? "true" : "false"}
      data-active-ticker={hoveredActivityTicker ?? ""}
    >
      <div className="ux13-stage-bg" aria-hidden="true" />

      <div className="ux13-frame">
        {/* Market pulse — first line of operational atmosphere */}
        <MarketPulseBar pulse={data.marketPulse} />

        {/* AI Read header — page-state + totals + ambient + since-you-left */}
        <AIRead13 data={data} />

        {/* Catalyst strip — upcoming events, clickable */}
        <CatalystStrip catalysts={data.catalysts} onCatalystClick={openDrawer} />

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
            UX-13 living-environment visual hypothesis · cinematic + heat pass · master at <code>docs/research/UX_13_LIVING_ENVIRONMENT.md</code>
          </span>
        </footer>
      </div>

      <ReasoningDrawer card={openCard} isOpen={isOpen} onClose={closeDrawer} />
    </div>
  );
}
