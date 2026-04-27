// Phase: integrated Alpha Core + ML Overlay UI.
// Shows Engine A / Engine B / baselines side-by-side so system truth
// (Engine B drag, Engine A edge, baseline benchmark) is visible <2s.

import { usePerformance } from "@/lib/operator/hooks";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";


// Static baselines — measurement_audit.py output (yfinance ES, 2020+).
// Hardcoded for now: no backend endpoint yet, no new schema.
// When backend baseline persistence ships (Phase 2), swap to query.
const BASELINES = [
  { key: "tsmom_60",  label: "TSMOM 60d",  sharpe: 1.02 },
  { key: "ma_50_200", label: "MA 50/200",  sharpe: 0.81 },
  { key: "bh_es",     label: "Buy & hold", sharpe: 0.72 },
] as const;


export default function AlphaCoreStatus() {
  const { data: perf } = usePerformance();

  const engineA = perf?.engine_a;
  const engineB = perf?.engine_b;

  const aSharpe = _num(engineA?.sharpe_proxy);
  const bSharpe = _num(engineB?.sharpe_proxy);
  const aHit = _num(engineA?.win_rate);
  const bHit = _num(engineB?.win_rate);
  const aN = _num(engineA?.n_trades);
  const bN = _num(engineB?.n_trades);

  const aBadge = _classifyEngine(aSharpe, aHit, aN);
  const bBadge = _classifyEngine(bSharpe, bHit, bN);

  // Best system Sharpe = max(engine sharpes); compute delta vs best baseline.
  const bestBaseline = Math.max(...BASELINES.map(b => b.sharpe));
  const systemSharpe = Math.max(
    Number.isFinite(aSharpe ?? NaN) ? (aSharpe ?? 0) : 0,
    Number.isFinite(bSharpe ?? NaN) ? (bSharpe ?? 0) : 0,
  );
  const deltaVsBaseline = systemSharpe - bestBaseline;

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Alpha Core Status</Label>
          <div className="u-caption-2 mt-0.5">
            engines · baselines · system delta
          </div>
        </div>
        <span className={cn("u-chip",
          deltaVsBaseline > 0 ? "u-chip-success"
          : deltaVsBaseline < -0.1 ? "u-chip-warning"
          : "u-chip-neutral")}
          title={`vs best baseline (${bestBaseline.toFixed(2)})`}>
          {deltaVsBaseline >= 0 ? "+" : ""}{deltaVsBaseline.toFixed(2)} vs best
        </span>
      </div>

      {/* Engine rows */}
      <ul className="space-y-2.5 mb-4">
        <EngineRow label="Engine A" sub="stress mean reversion"
                    sharpe={aSharpe} hit={aHit} n={aN}
                    badge={aBadge}
                    hint={
                      aBadge.tone === "pos"
                        ? "Strong edge — primary alpha"
                        : aN != null && aN < 30
                          ? "Small sample — monitor"
                          : "Underperforming"
                    } />
        <EngineRow label="Engine B" sub="directional"
                    sharpe={bSharpe} hit={bHit} n={bN}
                    badge={bBadge}
                    hint={
                      bBadge.tone === "neg"
                        ? "Dragging system — under review"
                        : "Active"
                    } />
      </ul>

      {/* Baselines (always visible benchmark) */}
      <div className="pt-3 border-t border-b1 mb-2">
        <div className="u-label-sm mb-1.5">Baselines (shadow only)</div>
        <ul className="space-y-1">
          {BASELINES.map(b => (
            <li key={b.key} className="flex items-center justify-between">
              <span className="u-caption text-fg-2">{b.label}</span>
              <span className={cn("u-mono-sm font-semibold",
                _toneFor(b.sharpe))}>
                {b.sharpe.toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="u-caption-2 text-fg-3 italic">
        Baselines never trade live. Used only for promotion-guard context.
      </div>
    </div>
  );
}


function EngineRow({
  label, sub, sharpe, hit, n, badge, hint,
}: {
  label: string;
  sub: string;
  sharpe: number | null;
  hit: number | null;
  n: number | null;
  badge: { text: string; tone: "pos" | "neg" | "warn" | "neutral" };
  hint: string;
}) {
  const sharpeStr = sharpe != null ? sharpe.toFixed(2) : "—";
  const hitStr    = hit != null ? `${(hit * 100).toFixed(0)}%` : "—";
  const nStr      = n != null ? `n=${n}` : "n=0";
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2">
        <span className="u-caption text-fg font-medium">{label}</span>
        <span className={cn("u-chip", _badgeChip(badge.tone))}>
          {badge.text}
        </span>
      </div>
      <div className="u-caption-2 text-fg-3 mb-1">{sub}</div>
      <div className="grid grid-cols-3 gap-2 mb-1">
        <Stat k="Sharpe" v={sharpeStr} tone={_toneFor(sharpe ?? 0)} />
        <Stat k="Hit"    v={hitStr} />
        <Stat k="N"      v={nStr.replace("n=", "")} />
      </div>
      <div className="u-caption-2 text-fg-3 italic">{hint}</div>
    </li>
  );
}


function Stat({ k, v, tone }: {
  k: string; v: string; tone?: string;
}) {
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{k}</div>
      <div className={cn("u-mono-sm font-semibold", tone ?? "text-fg")}>
        {v}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
function _num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}


function _toneFor(s: number): string {
  if (s >= 1.0) return "text-success";
  if (s <= -0.3) return "text-danger";
  if (s < 0.5) return "text-warning";
  return "text-fg";
}


function _classifyEngine(
  sharpe: number | null, hit: number | null, n: number | null,
): { text: string; tone: "pos" | "neg" | "warn" | "neutral" } {
  if (sharpe == null || n == null || n === 0) {
    return { text: "IDLE", tone: "neutral" };
  }
  if (sharpe >= 1.5 && (hit ?? 0) >= 0.55) {
    return { text: "STRONG", tone: "pos" };
  }
  if (sharpe <= -0.3) {
    return { text: "WEAK", tone: "neg" };
  }
  if (sharpe < 0.5) {
    return { text: "WATCH", tone: "warn" };
  }
  return { text: "ACTIVE", tone: "pos" };
}


function _badgeChip(tone: string): string {
  if (tone === "pos") return "u-chip-success";
  if (tone === "neg") return "u-chip-danger";
  if (tone === "warn") return "u-chip-warning";
  return "u-chip-neutral";
}
