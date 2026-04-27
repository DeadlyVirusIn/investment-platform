// Phase: compact under-chart events feed.
// Shows last 5-8 trade/decision events from latest paper run.
// Single line per event. No expand. Distinct from DailyActivityCard.

import { useLatestPaperRunEvents } from "@/lib/paper/runs";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";


const MAX = 8;


export default function RecentEventsFeed() {
  const { data: events } = useLatestPaperRunEvents();
  const rows = _flatten(events);

  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>Recent Activity</Label>
        <span className="u-caption-2 text-fg-3">
          last {Math.min(MAX, rows.length)} of {rows.length}
        </span>
      </div>
      {rows.length === 0 ? (
        <div className="u-caption-2 italic text-fg-3">
          No events on latest run.
        </div>
      ) : (
        <ul className="space-y-1">
          {rows.slice(0, MAX).map((r, i) => (
            <li key={i}
                className="grid grid-cols-[58px_64px_1fr_auto]
                              items-center gap-2 u-caption-2">
              <span className="u-mono-sm text-fg-3">{r.time}</span>
              <span className={cn("u-chip", _toneChip(r.kind))}>
                {r.kind}
              </span>
              <span className="truncate">
                <span className="u-mono-sm text-fg">{r.symbol ?? "—"}</span>
                {r.engine && (
                  <span className="text-fg-3"> · {r.engine}</span>
                )}
                {r.detail && (
                  <span className="text-fg-3 ml-1 truncate">
                    {r.detail}
                  </span>
                )}
              </span>
              <span className={cn("u-mono-sm shrink-0",
                r.ret != null && r.ret > 0 ? "text-success"
                : r.ret != null && r.ret < 0 ? "text-danger"
                : "text-fg-3")}>
                {r.ret != null
                  ? `${r.ret > 0 ? "+" : ""}${r.ret.toFixed(2)}%`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------

interface FlatRow {
  time: string;
  kind: "open" | "close" | "skip" | "decision";
  symbol: string | null;
  engine: string | null;
  detail: string | null;
  ret: number | null;
}


function _flatten(
  events: ReturnType<typeof useLatestPaperRunEvents>["data"],
): FlatRow[] {
  if (!events) return [];
  const out: FlatRow[] = [];
  for (const t of events.trades ?? []) {
    const kind: FlatRow["kind"] =
      (t as Record<string, unknown>)["event_type"] === "closed"
        ? "close" : "open";
    out.push({
      time: _fmt(t.ts),
      kind,
      symbol: t.symbol ?? null,
      engine: t.engine ?? null,
      detail: null,
      ret: _num(t.net_ret_pct ?? t.gross_ret_pct),
    });
  }
  for (const d of events.decisions ?? []) {
    const acc = (d.action ?? "").toLowerCase();
    if (acc === "enter_long") continue;     // already represented by trade
    const kind: FlatRow["kind"] =
      acc === "skip" || acc === "no_fire" ? "skip" : "decision";
    out.push({
      time: _fmt(d.ts),
      kind,
      symbol: d.symbol ?? null,
      engine: d.engine ?? null,
      detail: d.reason ?? null,
      ret: null,
    });
  }
  out.sort((a, b) => a.time.localeCompare(b.time));
  return out;
}


function _toneChip(k: string): string {
  if (k === "open") return "u-chip-accent";
  if (k === "close") return "u-chip-success";
  if (k === "skip") return "u-chip-neutral";
  return "u-chip-neutral";
}


function _fmt(s: string | undefined | null): string {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return s;
  }
}


function _num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}
