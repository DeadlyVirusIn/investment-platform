import { useDecision } from "@/lib/operator/hooks";
import { cn } from "@/lib/cn";

function EmptyState() {
  return (
    <div className="card-lg border-surface-border border-dashed p-12 text-center">
      <div className="text-3xl text-text-faint mb-3">◁</div>
      <p className="text-body text-text-primary font-medium">
        Select a trade to inspect
      </p>
      <p className="text-tiny text-text-muted mt-1.5">
        See the reasoning, inputs, and diagnostic snapshot.
      </p>
    </div>
  );
}

function Section({
  title, children, tone = "normal",
}: {
  title: string; children: React.ReactNode;
  tone?: "normal" | "diagnostic";
}) {
  return (
    <div className="mb-6 last:mb-0">
      <div className={cn(
        "text-micro uppercase tracking-[0.22em] font-semibold mb-2.5",
        tone === "diagnostic" ? "text-warning" : "text-text-muted",
      )}>
        {title}
      </div>
      {children}
    </div>
  );
}

function KVTable({ data, tone = "normal" }: {
  data: Record<string, unknown>; tone?: "normal" | "diagnostic";
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <p className="text-tiny text-text-muted italic">(empty)</p>;
  }
  return (
    <dl className={cn(
      "rounded-md border divide-y overflow-hidden",
      tone === "diagnostic"
        ? "border-warning/30 divide-warning/15 bg-warning-muted"
        : "border-surface-border/60 divide-surface-border/50 bg-surface-muted/60",
    )}>
      {entries.map(([k, v]) => (
        <div key={k} className="px-3.5 py-2 grid grid-cols-[1fr_auto]
                                  gap-3 items-baseline">
          <dt className="text-tiny text-text-secondary font-mono">{k}</dt>
          <dd className={cn(
            "text-tiny font-mono tabular-nums",
            tone === "diagnostic" ? "text-warning" : "text-text-primary",
          )}>
            {String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function DecisionDetail({
  asOfDate,
}: {
  asOfDate: string | null;
}) {
  const { data, isLoading } = useDecision(asOfDate);

  if (!asOfDate) return <EmptyState />;
  if (isLoading || !data) {
    return (
      <div className="card">
        <div className="h-72 bg-surface-elev/40 animate-pulse rounded-md" />
      </div>
    );
  }

  const titleTone = data.engine === "A" ? "text-info"
    : data.engine === "B" ? "text-accent" : "text-text-muted";

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="section-label mb-1.5">
            Decision · {data.as_of_date}
          </div>
          <h2 className={cn(
            "text-num-md font-semibold tracking-tight", titleTone,
          )}>
            {data.engine === "none"
              ? "Stood by"
              : `Engine ${data.engine} → ${data.action}`}
          </h2>
        </div>
        <span className="text-tiny text-text-faint font-mono">
          {data.decision_version}
        </span>
      </div>

      <Section title="Why">
        <p className="mono leading-relaxed bg-surface-muted/60 rounded-md p-3">
          {data.reason ?? "(no reason recorded)"}
        </p>
      </Section>

      <Section title="Production Inputs">
        <KVTable data={data.inputs_used} />
      </Section>

      <Section title="Production Context">
        <KVTable data={data.context_values} />
      </Section>

      {data.diagnostic_snapshot
       && Object.keys(data.diagnostic_snapshot).length > 0 && (
        <Section title="Diagnostic Snapshot · NOT USED IN PRODUCTION"
                 tone="diagnostic">
          <KVTable data={data.diagnostic_snapshot} tone="diagnostic" />
        </Section>
      )}

      {data.blocked_by && (
        <div className="mt-5 p-3 rounded-md bg-warning-muted border border-warning/40
                          text-tiny text-warning">
          <span className="font-semibold">Blocked by:</span> {data.blocked_by}
        </div>
      )}
    </div>
  );
}
