// UX-13 — visual hypothesis at /overview?view=living.
//
// VISUAL HYPOTHESIS for review — NOT final truth.
//
// Default /overview UNCHANGED. ?view=working / stream / conviction
// / copilot UNCHANGED. This is an isolated parallel route for
// visual validation of UX-12 substrate + UX-13 composition.
//
// URL switches:
//   ?view=living                  → defaults to Duet room
//   ?view=living&room=solo        → force Solo composition
//   ?view=living&room=duet        → force Duet (default)
//   ?view=living&room=field       → force Field composition
//   ?view=living&glyph=off        → kill verb-glyph (Codex R4 drift trigger)
//   ?view=living&room=duet&drawer=NVDA → opens drawer on first paint
//
// Tile click → drawer opens (UX-11 ReasoningDrawer reused).

import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";

import AIRead13 from "@/components/copilot/AIRead13";
import VerbGlyph from "@/components/copilot/VerbGlyph";
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
  const glyphKilled = params.get("glyph") === "off";

  const data = useMemo(() => composeLivingPage(room), [room]);

  const { openTicker, openDrawer, closeDrawer } = useDrawerUrlState();
  const openCard = openTicker ? PROOF_DRAWER_PAYLOADS[openTicker] ?? null : null;
  const isOpen = openCard !== null;

  return (
    <div
      className={`ux13-living ux13-room-${room}`}
      data-test="ux13-living-root"
      data-room={room}
    >
      <div
        style={{
          maxWidth: "var(--living-page-max)",
          margin: "0 auto",
          padding: "var(--living-page-pad-y) var(--living-page-pad-x)",
          position: "relative",
        }}
      >
        {/* Page header (Today + date + force-state nav) */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: "var(--living-space-md)",
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: 24,
                fontWeight: 500,
                fontFamily: "var(--living-font-sans)",
                color: "var(--living-ink-hero)",
                letterSpacing: "-0.01em",
              }}
            >
              Today
            </h1>
            <p
              style={{
                margin: "4px 0 0",
                fontSize: "var(--living-type-meta)",
                color: "var(--living-ink-meta)",
                fontFamily: "var(--living-font-mono)",
              }}
            >
              {data.date}
            </p>
          </div>

          {/* Force-state quick nav (visible only in this hypothesis route) */}
          <nav
            style={{
              display: "flex",
              gap: 16,
              fontSize: "var(--living-type-meta)",
              fontFamily: "var(--living-font-mono)",
              alignItems: "baseline",
            }}
            data-test="ux13-room-switcher"
          >
            <span style={{ color: "var(--living-ink-recede)" }}>force room:</span>
            {(["solo", "duet", "field"] as RoomMode[]).map(r => (
              <Link
                key={r}
                to={`/overview?view=living&room=${r}${glyphKilled ? "&glyph=off" : ""}`}
                style={{
                  color: room === r ? "var(--living-ink-hero)" : "var(--living-ink-meta)",
                  textDecoration: room === r ? "underline" : "none",
                  textUnderlineOffset: 4,
                }}
              >
                {r}
              </Link>
            ))}
            <span style={{ color: "var(--living-ink-recede)", marginLeft: 16 }}>·</span>
            <Link
              to={`/overview?view=living&room=${room}${glyphKilled ? "" : "&glyph=off"}`}
              style={{
                color: glyphKilled ? "var(--living-amber)" : "var(--living-ink-meta)",
              }}
            >
              {glyphKilled ? "glyph killed" : "kill glyph"}
            </Link>
            <Link
              to="/overview?view=working"
              style={{
                color: "var(--living-ink-meta)",
                marginLeft: 16,
              }}
            >
              See the working →
            </Link>
          </nav>
        </div>

        {/* AI Read header (page-state + ambient + posture + since-you-left) */}
        <AIRead13 data={data} />

        {/* Room composition */}
        {room === "solo" && (
          <RoomSolo data={data} onTileClick={openDrawer} openTicker={openTicker} />
        )}
        {room === "duet" && (
          <RoomDuet data={data} onTileClick={openDrawer} openTicker={openTicker} />
        )}
        {room === "field" && (
          <RoomField data={data} onTileClick={openDrawer} openTicker={openTicker} />
        )}

        {/* Verb-glyph (page chrome focal — separate from tile pill).
            Anchored absolute at fixed (x, y) below 40vh hairline.
            Solo 48pt / Duet 36pt / Field absent.
            Killed via ?glyph=off (Codex R4 drift trigger). */}
        {data.heroTile && (
          <VerbGlyph
            verb={data.heroTile.verb}
            room={room}
            killed={glyphKilled}
          />
        )}

        {/* Below-fold deep zone */}
        <div className="ux13-deep-zone" data-test="ux13-deep-zone">
          Deeper research available below — {room === "field" ? "5" : "3"} additional
          theses, regime detail, sector flows. (Stub for visual proof.)
        </div>

        {/* Footer */}
        <footer
          style={{
            marginTop: "var(--living-space-lg)",
            paddingTop: "var(--living-space-md)",
            borderTop: "1px solid var(--living-hairline)",
            fontSize: "var(--living-type-meta)",
            color: "var(--living-ink-recede)",
            lineHeight: 1.6,
          }}
        >
          Read-only research · paper trading only · not financial advice.
          <br />
          <span style={{ opacity: 0.7 }}>
            UX-13 living-environment visual hypothesis at{" "}
            <code>/overview?view=living</code> · master at{" "}
            <code>docs/research/UX_13_LIVING_ENVIRONMENT.md</code>
          </span>
        </footer>
      </div>

      <ReasoningDrawer card={openCard} isOpen={isOpen} onClose={closeDrawer} />
    </div>
  );
}
