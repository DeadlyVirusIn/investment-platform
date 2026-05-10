// UX-13 — ActivityStream component.
//
// Restores operational gravity. The AI's actual recent ACTIONS,
// not its philosophy. Each event clickable → opens that ticker's
// drawer. Hover an event → corresponding hero/sub block highlights
// (CSS data-active-ticker driven).
//
// Live timestamp tick: every 60s relative-time string recomputes
// via parent's useTickEverySecond hook driving re-render.

import type { ActivityEvent } from "@/lib/copilot/living_compose";


export interface ActivityStreamProps {
  events: ActivityEvent[];
  onEventClick: (ticker: string) => void;
  onEventHover: (ticker: string | null) => void;
}


function eventGlyph(type: ActivityEvent["type"]): string {
  switch (type) {
    case "conviction-up":     return "↑";
    case "conviction-down":   return "↓";
    case "thesis-strengthen": return "+";
    case "thesis-weaken":     return "−";
    case "catalyst-approach": return "◇";
    case "watchlist-warm":    return "◦";
    case "review-stale":      return "·";
  }
}


function eventTone(type: ActivityEvent["type"]): "up" | "down" | "neutral" {
  switch (type) {
    case "conviction-up":
    case "thesis-strengthen":
    case "watchlist-warm":
      return "up";
    case "conviction-down":
    case "thesis-weaken":
      return "down";
    default:
      return "neutral";
  }
}


function relativeTime(hoursAgo: number): string {
  if (hoursAgo === 0) return "now";
  if (hoursAgo < 1) return `${Math.max(1, Math.round(hoursAgo * 60))}m`;
  if (hoursAgo < 24) return `${Math.round(hoursAgo)}h`;
  return `${Math.round(hoursAgo / 24)}d`;
}


export default function ActivityStream({ events, onEventClick, onEventHover }: ActivityStreamProps) {
  if (events.length === 0) return null;

  return (
    <aside
      className="ux13-activity"
      data-test="ux13-activity"
      aria-label="AI activity since your last visit"
    >
      <h4 className="ux13-activity-label">AI activity</h4>
      <ul className="ux13-activity-list">
        {events.map(ev => (
          <li
            key={ev.id}
            className="ux13-activity-event"
            data-tone={eventTone(ev.type)}
            data-ticker={ev.ticker}
            onMouseEnter={() => onEventHover(ev.ticker)}
            onMouseLeave={() => onEventHover(null)}
            onClick={() => onEventClick(ev.ticker)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onEventClick(ev.ticker);
              }
            }}
            role="button"
            tabIndex={0}
            aria-label={`${ev.text} on ${ev.ticker}, ${relativeTime(ev.hoursAgo)} ago. Open reasoning.`}
          >
            <span className="ux13-activity-glyph" aria-hidden="true">
              {eventGlyph(ev.type)}
            </span>
            <span className="ux13-activity-ticker">{ev.ticker}</span>
            <span className="ux13-activity-text">{ev.text}</span>
            <span className="ux13-activity-time">{relativeTime(ev.hoursAgo)}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
