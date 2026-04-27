import { useShadowSignals } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";
import type { Status } from "@/lib/operator/types";

function StatusBadge({ status }: { status: Status }) {
  const cls = status === "production"
    ? "bg-success-muted text-success border-success/40"
    : status === "candidate"
      ? "bg-warning-muted text-warning border-warning/40"
      : "bg-danger-muted text-danger border-danger/40";
  return (
    <span className={cn("chip", cls)}>{status}</span>
  );
}

export default function ShadowPanel() {
  const { data, isLoading } = useShadowSignals();

  return (
    <div className="card border-warning/30 border-dashed
                    bg-warning-muted/[0.35]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="section-label text-warning">
            Shadow Signals
          </h3>
          <span className="chip bg-warning-muted text-warning border-warning/50
                            text-[9px] tracking-[0.15em]">
            NOT USED IN PRODUCTION
          </span>
        </div>
      </div>

      <p className="text-tiny text-text-muted mb-4 leading-relaxed">
        Diagnostic + candidate observatory. These signals are observed in
        parallel but NEVER affect Engine A / Engine B / selector decisions.
      </p>

      <div className="space-y-2.5">
        {isLoading && !data ? (
          <div className="h-20 bg-surface-elev/40 animate-pulse rounded-md" />
        ) : (data ?? []).length === 0 ? (
          <div className="text-tiny text-text-muted italic py-4 text-center">
            No shadow signals registered.
          </div>
        ) : (data ?? []).map(s => (
          <div key={s.name}
               className="rounded-md bg-surface-card/80 border border-surface-border/60
                           p-3.5 flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-label font-mono text-text-primary">
                  {s.name}
                </span>
                <StatusBadge status={s.status} />
              </div>
              <div className="text-tiny text-text-secondary leading-snug">
                {s.notes}
              </div>
              <div className="text-tiny text-text-faint mt-1 font-mono">
                {s.source} · {s.last_updated}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="stat-label">Value</div>
              <div className="text-num-sm font-mono text-text-primary tabular-nums">
                {s.value_display}
              </div>
              {s.context_flag !== null && (
                <div className={cn(
                  "text-tiny mt-0.5",
                  s.context_flag ? "text-warning" : "text-text-muted",
                )}>
                  flag: {s.context_flag ? "TRUE" : "false"}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
