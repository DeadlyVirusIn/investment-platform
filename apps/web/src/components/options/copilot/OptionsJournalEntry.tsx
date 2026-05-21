// OptionsJournalEntry — single timeline row primitive.
//
// Color-coded by entry_type. Clickable when linkage IDs allow
// drill-through to Research / Positions / Opportunities. Calm
// strategist tone; no execution affordance.

import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";


export interface JournalEntryPayload {
  entry_id: string;
  entry_type: string;
  entry_at_utc: string;
  underlying: string;
  title: string;
  summary: string;
  importance: string;
  trade_id: number | null;
  candidate_id: number | null;
  observation_id: number | null;
  strategy_name: string | null;
  diagnostics: Record<string, unknown>;
}


function entryTone(t: string): "pos" | "neg" | "warn" | "neutral" | "info" {
  if (t === "lifecycle_closed")       return "pos";
  if (t === "lifecycle_filled")       return "pos";
  if (t === "lifecycle_assigned")     return "warn";
  if (t === "lifecycle_expired")      return "warn";
  if (t === "lifecycle_force_closed") return "neg";
  if (t === "lifecycle_pin_risk")     return "neg";
  if (t === "lifecycle_early_assign_risk") return "neg";
  if (t === "lifecycle_expiring_flagged")  return "warn";
  if (t === "lifecycle_mtm")          return "neutral";
  if (t === "candidate_emitted")      return "info";
  if (t === "trade_proposed")         return "info";
  if (t === "shadow_observation")     return "neutral";
  return "neutral";
}


function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}


export default function OptionsJournalEntry({
  item, onOpenEvolution,
}: {
  item: JournalEntryPayload;
  onOpenEvolution?: (tradeId: number) => void;
}) {
  const tone = entryTone(item.entry_type);
  const hasEvolution = item.trade_id != null;

  return (
    <article
      className={cn("opt-journal-entry",
                    `opt-journal-tone-${tone}`,
                    `opt-journal-importance-${item.importance}`)}
      data-test={`opt-journal-entry-${item.entry_type}`}
    >
      <div className="opt-journal-marker" />
      <div className="opt-journal-body">
        <div className="opt-journal-row-1">
          <span className="opt-journal-time">
            {formatTime(item.entry_at_utc)}
          </span>
          <span className="opt-journal-type">
            {item.entry_type.replace(/_/g, " ")}
          </span>
          {item.underlying && (
            <Link
              to={`/options/research/${item.underlying}`}
              className="opt-journal-underlying"
              data-test={`opt-journal-underlying-${item.underlying}`}
            >
              {item.underlying}
            </Link>
          )}
        </div>
        <h4 className="opt-journal-title">{item.title}</h4>
        <p className="opt-journal-summary">{item.summary}</p>
        {(hasEvolution || item.candidate_id) && (
          <div className="opt-journal-actions">
            {hasEvolution && (
              <button
                type="button"
                className="opt-action-pill"
                onClick={() => onOpenEvolution
                  && item.trade_id != null
                  && onOpenEvolution(item.trade_id)}
                data-test="opt-journal-evolution"
              >
                Thesis evolution
              </button>
            )}
            {item.candidate_id && (
              <Link
                to="/options/opportunities"
                className="opt-action-pill"
                data-test="opt-journal-opp-link"
              >
                Open in Opportunities
              </Link>
            )}
            {item.trade_id && (
              <Link
                to="/options/positions"
                className="opt-action-pill"
                data-test="opt-journal-pos-link"
              >
                Open in Positions
              </Link>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
