// Phase UI-TERMINAL-LAYERS — Layer 5: live trade blotter feed.
// Merged event stream derived from trades + anomalies + summary.

import { useMemo } from "react";
import {
  usePaperTrades, useAnomalies, usePaperSummary,
} from "@/lib/operator/hooks";
import { Label, fmtPct } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

type EventType = "enter" | "exit" | "skip" | "anom" | "run";

interface BlotterEvent {
  ts: string;           // sort key — ISO or YYYY-MM-DD
  timeLabel: string;    // short display
  type: EventType;
  actor: string;
  detail: string;
  amt?: string;
  amtTone?: "pos" | "neg" | "neutral";
}

export default function TradeBlotter() {
  const { data: trades } = usePaperTrades();
  const { data: anomalies } = useAnomalies("open");
  const { data: summary } = usePaperSummary();

  const events = useMemo<BlotterEvent[]>(() => {
    const out: BlotterEvent[] = [];

    // Trade entries
    for (const t of trades ?? []) {
      out.push({
        ts: t.entry_date,
        timeLabel: t.entry_date.slice(5),   // MM-DD
        type: "enter",
        actor: `Engine ${t.engine}`,
        detail: `long · ${t.regime_at_entry} regime`,
        amt: undefined,
      });
      if (t.exit_date && t.net_ret_pct !== null) {
        const tone = t.net_ret_pct > 0 ? "pos"
          : t.net_ret_pct < 0 ? "neg" : "neutral";
        out.push({
          ts: t.exit_date,
          timeLabel: t.exit_date.slice(5),
          type: "exit",
          actor: `Engine ${t.engine}`,
          detail: `closed after ${t.days_held}d`,
          amt: fmtPct(t.net_ret_pct),
          amtTone: tone as "pos" | "neg",
        });
      }
    }

    // Anomalies
    for (const a of anomalies ?? []) {
      out.push({
        ts: a.as_of_date,
        timeLabel: a.as_of_date.slice(5),
        type: "anom",
        actor: a.severity.toUpperCase(),
        detail: a.title,
      });
    }

    // Last pipeline run
    if (summary?.last_decision_ts) {
      const d = new Date(summary.last_decision_ts);
      out.push({
        ts: summary.last_decision_ts,
        timeLabel: `${String(d.getHours()).padStart(2, "0")}:${
                     String(d.getMinutes()).padStart(2, "0")}`,
        type: "run",
        actor: "Pipeline",
        detail: summary.pipeline_status === "success"
          ? "daily run complete"
          : `run ${summary.pipeline_status}`,
      });
    }

    // Sort desc by ts string (lexicographic works on ISO)
    out.sort((a, b) => b.ts.localeCompare(a.ts));
    return out.slice(0, 10);
  }, [trades, anomalies, summary]);

  return (
    <div className="u-card" style={{ padding: 0 }}>
      <div className="flex items-center justify-between px-4 py-3
                        border-b border-b1">
        <div>
          <Label>Live blotter</Label>
          <div className="u-caption-2 mt-0.5">
            Last {events.length} system events
          </div>
        </div>
        <span className="u-chip u-chip-accent">
          <span className="u-dot u-dot-accent u-dot-pulse" />
          stream
        </span>
      </div>
      {events.length === 0 ? (
        <div className="px-4 py-6 u-caption-2 italic">
          No events yet. Feed populates on first pipeline run.
        </div>
      ) : (
        <div className="u-blotter">
          {events.map((e, i) => <BlotterRow key={`${e.ts}-${i}`} e={e} />)}
        </div>
      )}
    </div>
  );
}

function BlotterRow({ e }: { e: BlotterEvent }) {
  // Phase 11K.1 — neutralised state-transition labels.
  // Internal type codes (enter/exit/skip/anom/run) unchanged.
  const label = {
    enter: "STATE TRANSITION RECORDED",
    exit:  "STATE TRANSITION RECORDED",
    skip:  "Conditions not satisfied",
    anom:  "ANOMALY",
    run:   "EVALUATION CYCLE COMPLETED",
  }[e.type];
  const amtCls = e.amtTone === "pos" ? "text-success"
    : e.amtTone === "neg" ? "text-danger"
    : "text-fg-2";
  return (
    <div className="u-blotter-row">
      <span className="u-blotter-ts">{e.timeLabel}</span>
      <span className={cn("u-blotter-type", `is-${e.type}`)}>{label}</span>
      <span className="u-blotter-actor">{e.actor}</span>
      <span className="u-blotter-detail">{e.detail}</span>
      <span className={cn("u-blotter-amt", amtCls)}>{e.amt ?? "—"}</span>
    </div>
  );
}
