// OptionsResearchUnderlyingCard — one underlying tile for the
// Research universe surface. Renders calm one-line read + posture
// chip + iv tier + next catalyst + click-through to deep dive.

import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";
import { fmtUSD } from "@/components/ui/primitives";
import OptionsCatalystChip from "./OptionsCatalystChip";


export interface ResearchUniverseRow {
  symbol: string;
  spot: number | null;
  ai_posture: string;
  iv_rank_252d: number | null;
  premium_tier: string;
  candidate_count: number;
  next_event: {
    event_type: string;
    event_date: string;
    importance: string;
    title: string;
    days_away: number;
  } | null;
}


function postureTone(p: string): "pos" | "neg" | "warn" | "neutral" {
  if (p.startsWith("bullish")) return "pos";
  if (p.startsWith("bearish")) return "neg";
  if (p === "event-driven") return "warn";
  if (p === "neutral-leaning") return "neutral";
  return "neutral";
}


export default function OptionsResearchUnderlyingCard({
  row,
}: { row: ResearchUniverseRow }) {
  const tone = postureTone(row.ai_posture);
  return (
    <Link
      to={`/options/research/${row.symbol}`}
      className={cn("opt-research-card", `opt-research-tone-${tone}`)}
      data-test={`opt-research-card-${row.symbol}`}
    >
      <header className="opt-research-card-head">
        <span className="opt-research-symbol">{row.symbol}</span>
        {row.spot != null && (
          <span className="opt-research-spot">{fmtUSD(row.spot, 2)}</span>
        )}
      </header>
      <div className="opt-research-card-posture">
        <span className="opt-research-posture-eyebrow">AI posture</span>
        <span className="opt-research-posture-value">{row.ai_posture}</span>
      </div>
      <div className="opt-research-card-meta">
        <span className="opt-caption-muted">
          Premium <strong>{row.premium_tier}</strong>
          {row.iv_rank_252d != null && (
            <> · IV rank {row.iv_rank_252d.toFixed(0)}</>
          )}
        </span>
        <span className="opt-caption-muted">
          {row.candidate_count} candidate{row.candidate_count === 1 ? "" : "s"}
        </span>
      </div>
      {row.next_event && (
        <div className="opt-research-card-event">
          <OptionsCatalystChip
            eventType={row.next_event.event_type}
            eventDate={row.next_event.event_date}
            daysAway={row.next_event.days_away}
            importance={row.next_event.importance}
            title={row.next_event.title} />
        </div>
      )}
    </Link>
  );
}
