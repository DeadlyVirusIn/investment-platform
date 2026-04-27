import { cn } from "@/lib/cn";
import { usePaperSummary, useCurrentState, useAnomalySummary } from "@/lib/operator/hooks";
import { deriveSystemNarrative } from "@/lib/operator/narrative";

export default function SystemStatusCard() {
  const { data: summary, dataUpdatedAt } = usePaperSummary();
  const { data: state } = useCurrentState();
  const { data: anomalies } = useAnomalySummary();

  const n = deriveSystemNarrative(summary, state, anomalies);

  const toneMap = {
    healthy: {
      border: "border-success/40",
      glow:   "shadow-status-glow",
      dotBg:  "bg-success",
      label:  "HEALTHY",
      labelCls: "text-success",
    },
    warning: {
      border: "border-warning/40",
      glow:   "",
      dotBg:  "bg-warning",
      label:  "WARNING",
      labelCls: "text-warning",
    },
    degraded: {
      border: "border-danger/50",
      glow:   "",
      dotBg:  "bg-danger",
      label:  "DEGRADED",
      labelCls: "text-danger",
    },
    critical: {
      border: "border-danger/70",
      glow:   "",
      dotBg:  "bg-danger",
      label:  "CRITICAL",
      labelCls: "text-danger",
    },
  }[n.tone];

  const timeLabel = dataUpdatedAt
    ? relativeTime(dataUpdatedAt)
    : "idle";

  return (
    <div className={cn(
      "card-lg bg-surface-card/95", toneMap.border, toneMap.glow,
    )}>
      {/* TOP ROW — status dot + label + timestamp */}
      <div className="flex items-center gap-3 mb-6">
        <span className="relative inline-flex w-2.5 h-2.5">
          <span className={cn(
            "absolute inset-0 rounded-full animate-ping opacity-40",
            toneMap.dotBg,
          )} />
          <span className={cn(
            "relative inline-flex w-2.5 h-2.5 rounded-full", toneMap.dotBg,
          )} />
        </span>
        <span className={cn("text-micro font-bold tracking-[0.22em]",
          toneMap.labelCls)}>
          SYSTEM STATUS
        </span>
        <span className="ml-auto text-tiny text-text-muted font-mono tabular-nums">
          updated {timeLabel}
        </span>
      </div>

      {/* HEADLINE — large status word */}
      <h1 className={cn(
        "text-[28px] font-semibold tracking-tight leading-[32px] mb-4",
        toneMap.labelCls,
      )}>
        {toneMap.label}
      </h1>

      {/* BODY — one-sentence summary */}
      <p className="text-headline font-semibold text-text-primary
                     leading-[30px] mb-3">
        {n.headline}
      </p>

      {/* DETAIL — secondary narrative */}
      <p className="text-body text-text-secondary leading-relaxed">
        {n.body}
      </p>

      {/* DIVIDER */}
      <div className="my-8 divider" />

      {/* ACTION */}
      <div>
        <div className="stat-label mb-2">Suggested Action</div>
        <p className="text-body text-text-primary">{n.action}</p>
      </div>
    </div>
  );
}

function relativeTime(ts: number): string {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
