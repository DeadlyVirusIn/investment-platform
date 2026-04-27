import { useCurrentState } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

function RegimeBadge({ name, active }: { name: string; active: boolean }) {
  return (
    <span className={cn(
      "text-xs px-2 py-0.5 rounded font-medium tracking-wide",
      active
        ? "bg-accent/20 text-accent border border-accent/40"
        : "bg-surface-hover text-text-muted border border-surface-border",
    )}>
      {name}
    </span>
  );
}

export default function CurrentStateCard() {
  const { data, isLoading } = useCurrentState();

  if (isLoading || !data) {
    return (
      <div className="rounded-lg bg-surface-card border border-surface-border p-4">
        <div className="h-24 animate-pulse bg-surface-hover rounded" />
      </div>
    );
  }

  const fireColor = data.fire ? "text-success" : "text-text-secondary";
  return (
    <div className="rounded-lg bg-surface-card border border-surface-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Current State
        </h3>
        <span className="text-xs text-text-muted">{data.as_of_date}</span>
      </div>

      <div className="flex gap-2 mb-4">
        <RegimeBadge name="STRESS" active={data.stress_regime} />
        <RegimeBadge name="DIRECTIONAL" active={data.directional_regime} />
        <span className="ml-auto text-xs text-text-secondary">
          gates: <span className="font-semibold text-text-primary">
            {data.gates_favorable}/4
          </span>
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-text-muted text-xs uppercase">Engine</div>
          <div className="font-semibold text-text-primary">
            {data.engine === "none" ? "—" : data.engine}
          </div>
        </div>
        <div>
          <div className="text-text-muted text-xs uppercase">Action</div>
          <div className={cn("font-semibold", fireColor)}>
            {data.fire ? "ENTER_LONG" : "NO_FIRE"}
          </div>
        </div>
        <div className="col-span-2">
          <div className="text-text-muted text-xs uppercase mb-1">Reason</div>
          <div className="text-text-primary text-sm font-mono leading-snug
                          bg-surface-hover px-2 py-1 rounded">
            {data.reason}
          </div>
        </div>
        <div className="col-span-2 text-xs text-text-muted">
          <span className="mr-4">version: {data.decision_version}</span>
          {data.blocked_by && (
            <span className="text-warning">blocked_by: {data.blocked_by}</span>
          )}
        </div>
      </div>
    </div>
  );
}
