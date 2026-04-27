import { useSystemHealth, useAnomalySummary } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

export default function HealthBanner() {
  const { data } = useSystemHealth();
  const { data: anomalies } = useAnomalySummary();

  const hasSystemIssues = data && data.items.length > 0;
  const anomCrit = anomalies?.by_severity?.critical ?? 0;
  const anomWarn = anomalies?.by_severity?.warning ?? 0;
  const anomInfo = anomalies?.by_severity?.info ?? 0;
  const hasAnomalies = (anomalies?.total_open ?? 0) > 0;

  if (!hasSystemIssues && !hasAnomalies) return null;

  const errors = data?.items.filter(i => i.severity === "error") ?? [];
  const warns = data?.items.filter(i => i.severity === "warn") ?? [];

  const hasCritical = errors.length > 0 || anomCrit > 0;
  const toneCls = hasCritical
    ? "bg-danger-muted border-danger/50 text-danger"
    : "bg-warning-muted border-warning/50 text-warning";

  return (
    <div className={cn("rounded-md border px-4 py-3 mb-6", toneCls)}>
      <div className="flex items-center gap-2 mb-1.5 text-label font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-current inline-block" />
        System Health: {hasCritical ? "DEGRADED" : "WARNINGS"}
        <span className="text-tiny font-mono font-normal opacity-70 ml-auto
                          tabular-nums">
          {errors.length}e · {warns.length}w · anomalies
          : {anomCrit}c/{anomWarn}w/{anomInfo}i
        </span>
      </div>
      {(errors.length > 0 || warns.length > 0) && (
        <ul className="text-tiny space-y-1 mt-2">
          {errors.concat(warns).slice(0, 5).map(i => (
            <li key={i.key} className="flex gap-2">
              <span className="font-mono opacity-50 w-14 shrink-0">
                [{i.severity}]
              </span>
              <span className="font-medium">{i.label}:</span>
              <span className="opacity-85">{i.detail}</span>
            </li>
          ))}
        </ul>
      )}
      {hasAnomalies && anomalies?.top3 && anomalies.top3.length > 0 && (
        <ul className="text-tiny space-y-1 mt-2 pt-2 border-t border-current/20
                        opacity-90">
          {anomalies.top3.map(a => (
            <li key={a.id} className="flex gap-2">
              <span className="font-mono opacity-50 w-14 shrink-0">
                [{a.severity}]
              </span>
              <span className="font-mono text-[10px] opacity-60 w-12 shrink-0">
                {a.category}
              </span>
              <span className="font-medium">{a.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
