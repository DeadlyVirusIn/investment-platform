import { useState } from "react";
import { useAnomalies } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";
import type {
  AnomalyCategory, AnomalySeverity, AnomalyEvent,
} from "@/lib/operator/types";

function SeverityChip({ s }: { s: AnomalySeverity }) {
  const cls = s === "critical"
    ? "bg-danger-muted text-danger border-danger/50"
    : s === "warning"
      ? "bg-warning-muted text-warning border-warning/50"
      : "bg-info-muted text-info border-info/40";
  return <span className={cn("chip", cls)}>{s}</span>;
}

function CategoryChip({ c }: { c: AnomalyCategory }) {
  const label = {
    decision: "DEC", trade: "TRD", regime: "REG",
    data: "DAT", shadow: "SHD",
  }[c];
  return (
    <span className="chip bg-surface-elev text-text-muted border-surface-border/70
                      font-mono">
      {label}
    </span>
  );
}

const SEVERITY_OPTIONS: (AnomalySeverity | "all")[] = [
  "all", "critical", "warning", "info",
];
const CATEGORY_OPTIONS: (AnomalyCategory | "all")[] = [
  "all", "decision", "trade", "regime", "data", "shadow",
];

function FilterButton({
  active, onClick, children,
}: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button onClick={onClick}
      className={cn(
        "text-tiny uppercase px-2 py-1 rounded-sm border transition-colors",
        active
          ? "bg-accent-subtle text-accent border-accent/50 font-semibold"
          : "bg-surface-elev/60 border-surface-border text-text-muted"
            + " hover:text-text-primary hover:border-surface-border",
      )}>
      {children}
    </button>
  );
}

export default function AnomalyPanel({
  onSelectTrade,
}: {
  onSelectTrade?: (tradeId: string) => void;
}) {
  const [severity, setSeverity] = useState<AnomalySeverity | "all">("all");
  const [category, setCategory] = useState<AnomalyCategory | "all">("all");
  const { data, isLoading } = useAnomalies(
    "open",
    severity === "all" ? undefined : severity,
  );

  const filtered = (data ?? []).filter(
    a => category === "all" || a.category === category,
  );

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-5">
        <h3 className="section-label">
          Anomalies
          <span className="ml-2 text-tiny text-text-muted font-normal normal-case
                            tracking-normal">
            {filtered.length} open
          </span>
        </h3>
      </div>

      <div className="mb-2 flex items-center gap-2 flex-wrap">
        <span className="text-tiny uppercase text-text-faint font-semibold
                          tracking-[0.15em] mr-1">severity</span>
        {SEVERITY_OPTIONS.map(s => (
          <FilterButton key={s} active={severity === s}
                        onClick={() => setSeverity(s)}>{s}</FilterButton>
        ))}
      </div>
      <div className="mb-5 flex items-center gap-2 flex-wrap">
        <span className="text-tiny uppercase text-text-faint font-semibold
                          tracking-[0.15em] mr-1">category</span>
        {CATEGORY_OPTIONS.map(c => (
          <FilterButton key={c} active={category === c}
                        onClick={() => setCategory(c)}>{c}</FilterButton>
        ))}
      </div>

      <div className="space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
        {isLoading && filtered.length === 0 ? (
          <div className="h-20 bg-surface-elev/40 animate-pulse rounded-md" />
        ) : filtered.length === 0 ? (
          <div className="text-center py-10 text-text-muted">
            <div className="text-2xl mb-1.5 text-success/70">✓</div>
            <p className="text-label">No open anomalies.</p>
          </div>
        ) : filtered.map(a => (
          <AnomalyRow key={a.id} a={a} onSelectTrade={onSelectTrade} />
        ))}
      </div>
    </div>
  );
}

function AnomalyRow({
  a, onSelectTrade,
}: {
  a: AnomalyEvent;
  onSelectTrade?: (tradeId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const isShadow = a.category === "shadow";
  return (
    <div className={cn(
      "rounded-md border p-3 cursor-pointer transition-all duration-150",
      isShadow
        ? "bg-warning-muted/30 border-warning/30 border-dashed hover:bg-warning-muted/50"
        : "bg-surface-elev/50 border-surface-border/60 hover:border-accent/40"
          + " hover:bg-surface-elev",
    )} onClick={() => setOpen(o => !o)}>
      <div className="flex items-start gap-2 flex-wrap">
        <SeverityChip s={a.severity} />
        <CategoryChip c={a.category} />
        {isShadow && (
          <span className="chip bg-warning-muted text-warning border-warning/50
                            text-[9px] tracking-[0.15em]">
            DIAGNOSTIC · NOT USED IN PRODUCTION
          </span>
        )}
        <span className="ml-auto text-tiny text-text-muted font-mono tabular-nums">
          {a.as_of_date}
        </span>
      </div>
      <div className="mt-2 text-label text-text-primary font-medium">
        {a.title}
      </div>
      {open && (
        <div className="mt-3 pt-3 border-t border-surface-border/50 text-tiny
                         text-text-secondary space-y-1.5">
          <p>{a.description}</p>
          {a.related_engine && (
            <div className="text-text-muted">
              engine:{" "}
              <span className="text-text-primary font-mono">
                {a.related_engine}
              </span>
            </div>
          )}
          {a.related_trade_id && onSelectTrade && (
            <button className="text-accent text-tiny hover:underline"
              onClick={e => { e.stopPropagation();
                              onSelectTrade(a.related_trade_id!); }}>
              → inspect trade
            </button>
          )}
          {Object.keys(a.metrics_snapshot || {}).length > 0 && (
            <pre className="mt-1.5 bg-surface-muted/60 rounded-sm p-2 text-tiny
                             font-mono text-text-primary">
              {JSON.stringify(a.metrics_snapshot, null, 2)}
            </pre>
          )}
          <div className="text-tiny text-text-faint mt-1.5">
            rule: <span className="font-mono">{a.rule_key}</span>
          </div>
        </div>
      )}
    </div>
  );
}
