import { cn } from "@/lib/cn";
import { useCurrentState, usePaperSummary } from "@/lib/operator/hooks";

export default function CurrentActionCard() {
  const { data: state } = useCurrentState();
  const { data: summary } = usePaperSummary();

  if (!state) {
    return (
      <div className="card">
        <div className="h-40 bg-surface-elev/40 animate-pulse rounded-md" />
      </div>
    );
  }

  const regime = state.stress_regime ? "STRESS"
    : state.directional_regime ? "DIRECTIONAL" : "NEUTRAL";
  const regimeCls = state.stress_regime
    ? "text-info bg-info-muted border-info/50"
    : state.directional_regime
      ? "text-accent bg-accent-subtle border-accent/50"
      : "text-text-muted bg-surface-elev border-surface-border";

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-5">
        <h2 className="section-label">Today's Action</h2>
        <span className="text-tiny text-text-muted font-mono tabular-nums">
          {state.as_of_date}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div>
          <div className="stat-label mb-2">Regime</div>
          <span className={cn(
            "chip text-tiny uppercase tracking-wide", regimeCls,
          )}>
            {regime}
          </span>
          <div className="text-tiny text-text-muted mt-1.5 tabular-nums">
            gates {state.gates_favorable}/4
          </div>
        </div>
        <div>
          <div className="stat-label mb-2">Engine</div>
          <div className="text-num-md font-semibold text-text-primary">
            {state.engine === "none" ? "—" : state.engine}
          </div>
        </div>
        <div>
          <div className="stat-label mb-2">Open</div>
          <div className="text-num-md font-semibold text-text-primary
                           tabular-nums">
            {summary?.open_positions_count ?? "—"}
          </div>
        </div>
      </div>

      <div className="pt-5 divider">
        <div className="flex items-center gap-2 mb-2">
          <span className={cn(
            "text-micro uppercase font-bold tracking-[0.22em]",
            state.fire ? "text-success" : "text-text-muted",
          )}>
            {state.fire ? "● FIRED" : "○ STANDING BY"}
          </span>
          <span className="text-tiny text-text-faint font-mono ml-auto">
            {state.decision_version}
          </span>
        </div>
        <p className="mono leading-relaxed bg-surface-muted/60 rounded-md
                       p-3 text-text-primary">
          {state.reason}
        </p>
        {state.blocked_by && (
          <p className="mt-3 text-label text-warning">
            Blocked by: {state.blocked_by}
          </p>
        )}
      </div>
    </div>
  );
}
