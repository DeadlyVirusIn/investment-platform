// Phase ML-2.5 — compact admin card. Latest replay run only.

import { useReplayLatestRun } from "@/lib/replay/hooks";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function HistoricalReplayCard() {
  const { data } = useReplayLatestRun();

  if (!data?.present || !data.run) {
    return (
      <div className="u-card">
        <Label>Historical Replay</Label>
        <div className="u-caption-2 mt-2">
          No replay runs yet. POST{" "}
          <code className="u-mono-sm">/api/ml/replay/run</code> to start.
        </div>
      </div>
    );
  }

  const r = data.run;
  const n = r.summary?.n_decisions ?? 0;
  const syms = r.summary?.n_symbols ?? 0;
  const dates = r.summary?.n_dates ?? 0;
  const tone = statusTone(r.status);
  const warnings = (r.summary?.warnings ?? []).concat(r.warnings ?? []);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Historical Replay</Label>
          <div className="u-caption-2 mt-0.5">
            <code className="u-mono-sm">{r.replay_name}</code> ·{" "}
            {new Date(r.created_at).toLocaleString()}
          </div>
        </div>
        <span className={cn("u-chip", tone)}>{r.status}</span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <KV k="Range"       v={`${r.start_date} → ${r.end_date}`} />
        <KV k="Decisions"   v={`${n}`} />
        <KV k="Symbols"     v={`${syms}`} />
        <KV k="Trading days" v={`${dates}`} />
      </div>

      {warnings.length > 0 && (
        <div className="mt-2">
          <div className="u-label-sm mb-1.5">Warnings</div>
          <ul className="space-y-1">
            {warnings.slice(0, 3).map((w, i) => (
              <li key={i} className="u-caption-2 flex items-start gap-2">
                <span className="text-warning shrink-0">!</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex gap-4">
        <a className="u-caption text-accent hover:underline"
           href={`/api/ml/replay/runs/${r.id}/report`}
           target="_blank" rel="noreferrer">
          view report
        </a>
        <a className="u-caption text-accent hover:underline"
           href={`/api/ml/replay/runs/${r.id}/decisions`}
           target="_blank" rel="noreferrer">
          view decisions
        </a>
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{k}</span>
      <span className="u-mono-sm font-semibold text-fg">{v}</span>
    </div>
  );
}

function statusTone(s: string): string {
  switch (s) {
    case "completed":       return "u-chip-success";
    case "running":         return "u-chip-accent";
    case "failed_leakage":  return "u-chip-danger";
    case "pending":         return "u-chip-warning";
    default:                return "u-chip-neutral";
  }
}
