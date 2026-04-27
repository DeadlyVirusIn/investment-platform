import { useDecision } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

export default function DecisionDrawer({
  asOfDate, onClose,
}: {
  asOfDate: string | null;
  onClose: () => void;
}) {
  const { data, isLoading } = useDecision(asOfDate);

  if (!asOfDate) return null;

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <aside className="w-[480px] max-w-full h-full bg-surface-card border-l
                          border-surface-border p-5 overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-text-primary">
            Decision Audit
          </h2>
          <button onClick={onClose}
            className="text-text-muted hover:text-text-primary text-lg">✕</button>
        </div>

        {isLoading || !data ? (
          <div className="h-64 bg-surface-hover animate-pulse rounded" />
        ) : (
          <>
            <div className="mb-4">
              <div className="text-xs text-text-muted uppercase">As-of Date</div>
              <div className="text-sm text-text-primary font-mono">
                {data.as_of_date}  ·  <span className="text-text-secondary">
                  {new Date(data.decision_ts).toLocaleString()}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-4">
              <Stat label="Engine"
                    value={data.engine === "none" ? "—" : data.engine} />
              <Stat label="Action" value={data.action} />
              <Stat label="Instrument" value={data.instrument} />
            </div>

            <SectionLabel text="Reason" />
            <pre className="bg-surface-hover rounded p-2 text-[11px] text-text-primary
                             whitespace-pre-wrap font-mono mb-4">
              {data.reason ?? "(none)"}
            </pre>

            <SectionLabel text="Inputs Used (production)" />
            <JSONBlock data={data.inputs_used} />

            <SectionLabel text="Context Values (production)" />
            <JSONBlock data={data.context_values} />

            {data.diagnostic_snapshot
             && Object.keys(data.diagnostic_snapshot).length > 0 && (
              <>
                <SectionLabel text="Diagnostic Snapshot (NOT USED IN PRODUCTION)"
                              tone="diag" />
                <JSONBlock data={data.diagnostic_snapshot} tone="diag" />
              </>
            )}

            {data.blocked_by && (
              <div className="mt-3 text-xs text-warning">
                Blocked by: {data.blocked_by}
              </div>
            )}

            <div className="mt-6 text-[10px] text-text-muted">
              decision_version: <span className="font-mono">
                {data.decision_version}
              </span>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-surface-hover rounded p-2">
      <div className="text-[10px] uppercase text-text-muted">{label}</div>
      <div className="text-sm font-semibold text-text-primary">{value}</div>
    </div>
  );
}

function SectionLabel({ text, tone = "normal" }: {
  text: string; tone?: "normal" | "diag";
}) {
  return (
    <div className={cn(
      "text-[10px] uppercase tracking-wider mb-1 mt-3",
      tone === "diag" ? "text-warning" : "text-text-muted",
    )}>
      {text}
    </div>
  );
}

function JSONBlock({ data, tone = "normal" }: {
  data: unknown; tone?: "normal" | "diag";
}) {
  return (
    <pre className={cn(
      "rounded p-2 text-[11px] font-mono whitespace-pre-wrap mb-4",
      tone === "diag"
        ? "bg-warning/10 border border-warning/30 text-warning"
        : "bg-surface-hover text-text-primary",
    )}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
