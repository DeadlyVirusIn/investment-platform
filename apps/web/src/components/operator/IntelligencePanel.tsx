import { useAnomalySummary } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";
import type { AnomalyEvent, AnomalySeverity } from "@/lib/operator/types";

function severityGlyph(s: AnomalySeverity): string {
  return s === "critical" ? "▲" : s === "warning" ? "◆" : "●";
}

function severityTone(s: AnomalySeverity) {
  return s === "critical" ? "text-danger"
    : s === "warning" ? "text-warning" : "text-info";
}

function AnomalyItem({ a }: { a: AnomalyEvent }) {
  const isShadow = a.category === "shadow";
  return (
    <div className={cn(
      "py-4 border-b border-surface-border/50 last:border-b-0 first:pt-0",
      isShadow && "opacity-75",
    )}>
      <div className="flex items-start gap-3">
        <span className={cn("text-base leading-none mt-1",
          severityTone(a.severity))}>
          {severityGlyph(a.severity)}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-label font-medium text-text-primary">
              {a.title}
            </span>
            {isShadow && (
              <span className="chip text-[9px] bg-warning-muted text-warning
                                border-warning/40">
                DIAGNOSTIC
              </span>
            )}
          </div>
          <p className="text-tiny text-text-secondary leading-relaxed">
            {a.description}
          </p>
          <div className="text-tiny text-text-faint mt-1.5 font-mono">
            {a.category} · {a.as_of_date}
            {a.related_engine && ` · Engine ${a.related_engine}`}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function IntelligencePanel() {
  const { data, isLoading } = useAnomalySummary();

  if (isLoading || !data) {
    return (
      <div className="card">
        <div className="h-48 bg-surface-elev/40 animate-pulse rounded-md" />
      </div>
    );
  }

  const { by_severity, total_open, top3 } = data;
  const isQuiet = total_open === 0;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="section-label mb-1">System Intelligence</h2>
          <p className="text-tiny text-text-muted">
            Pattern detection across decisions, trades, regime, and data integrity.
          </p>
        </div>
        <div className="flex gap-2">
          <SevBadge n={by_severity?.critical ?? 0} label="critical" tone="danger" />
          <SevBadge n={by_severity?.warning ?? 0} label="warning" tone="warning" />
          <SevBadge n={by_severity?.info ?? 0} label="info" tone="info" />
        </div>
      </div>

      {isQuiet ? (
        <div className="py-10 text-center">
          <div className="text-success text-3xl mb-2 opacity-70">✓</div>
          <div className="text-body text-text-primary font-medium">
            No anomalies detected.
          </div>
          <p className="text-tiny text-text-muted mt-1.5">
            System is operating within expected parameters.
          </p>
        </div>
      ) : (
        <div>
          <div className="section-label mb-3">Top Concerns</div>
          <div>
            {(top3 ?? []).map(a => <AnomalyItem key={a.id} a={a} />)}
          </div>
          {total_open > (top3?.length ?? 0) && (
            <div className="text-tiny text-text-muted mt-4 pt-4 divider">
              {total_open - (top3?.length ?? 0)} more open —
              review in <span className="text-text-secondary">Operator → Anomalies</span>.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SevBadge({
  n, label, tone,
}: {
  n: number; label: string; tone: "danger" | "warning" | "info";
}) {
  const tones = {
    danger:  { on: "text-danger border-danger/50 bg-danger-muted" },
    warning: { on: "text-warning border-warning/50 bg-warning-muted" },
    info:    { on: "text-info border-info/50 bg-info-muted" },
  }[tone];
  return (
    <div className={cn(
      "flex flex-col items-center px-3 py-2 rounded-md border min-w-[56px]",
      n === 0
        ? "opacity-30 border-surface-border text-text-muted bg-surface-muted/40"
        : tones.on,
    )}>
      <span className="text-num-md font-semibold tabular-nums leading-none">
        {n}
      </span>
      <span className="text-tiny uppercase tracking-wider mt-1 font-medium">
        {label}
      </span>
    </div>
  );
}
