// Alpha Lab — research console for validating, comparing, debugging
// strategies. UI + visualization only. No backend changes, no trading
// logic, no scheduler/ML/risk side effects.

import { useMemo, useState } from "react";
import {
  usePaperTrades, usePaperEquity, usePerformance,
} from "@/lib/operator/hooks";
import { Label } from "@/components/ui/primitives";
import Sparkline from "@/components/ui/Sparkline";
import { cn } from "@/lib/cn";


type StrategyKey = "engine_a" | "engine_b" | "baseline" | "combined";
type RangeKey = "30D" | "90D" | "YTD" | "ALL";
type RegimeKey = "all" | "stress" | "directional" | "neutral";


// Static baselines — measurement_audit output
const BASELINES = [
  { key: "tsmom_60",  label: "TSMOM 60d",
     sharpe: 1.02, hit: 0.40, dd: -19.94, n: 1588, total: 104.46 },
  { key: "ma_50_200", label: "MA 50/200",
     sharpe: 0.81, hit: 0.38, dd: -18.64, n: 1588, total: 81.01 },
  { key: "tsmom_20",  label: "TSMOM 20d",
     sharpe: 0.94, hit: 0.36, dd: -12.82, n: 1588, total: 93.41 },
  { key: "bh_es",     label: "Buy & hold",
     sharpe: 0.72, hit: 0.54, dd: -34.45, n: 1588, total: 120.77 },
] as const;


export default function AlphaLab() {
  const [strategy, setStrategy] = useState<StrategyKey>("combined");
  const [range, setRange] = useState<RangeKey>("ALL");
  const [regime, setRegime] = useState<RegimeKey>("all");
  const [whatif, setWhatif] = useState<"none" | "remove_b" | "gate_b">("none");

  const { data: trades } = usePaperTrades();
  const { data: equity } = usePaperEquity();
  const { data: perf } = usePerformance();

  const filtered = useMemo(() =>
    _filter(trades ?? [], strategy, range, regime, whatif),
  [trades, strategy, range, regime, whatif]);

  const score = useMemo(() => _score(filtered), [filtered]);
  const dist  = useMemo(() => _histogram(filtered), [filtered]);
  const decisionStats = useMemo(() =>
    _decisionStats(filtered), [filtered]);
  const byRegime = useMemo(() => _byRegime(trades ?? []), [trades]);

  const equitySeries = (equity ?? []).map(p => p.equity);

  return (
    <div className="max-w-[1520px] mx-auto px-6 py-6 space-y-4">
      {/* === HEADER + CONTROLS === */}
      <header className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <Label>Research</Label>
          <h1 className="u-title mt-1">Alpha Lab</h1>
          <p className="u-caption mt-0.5">
            Validate · compare · debug strategies. Read-only.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ControlGroup label="Strategy">
            <Pill active={strategy === "engine_a"}
                  onClick={() => setStrategy("engine_a")}>Engine A</Pill>
            <Pill active={strategy === "engine_b"}
                  onClick={() => setStrategy("engine_b")}>Engine B</Pill>
            <Pill active={strategy === "baseline"}
                  onClick={() => setStrategy("baseline")}>Baseline</Pill>
            <Pill active={strategy === "combined"}
                  onClick={() => setStrategy("combined")}>Combined</Pill>
          </ControlGroup>
          <ControlGroup label="Range">
            {(["30D","90D","YTD","ALL"] as RangeKey[]).map(r => (
              <Pill key={r} active={range === r}
                    onClick={() => setRange(r)}>{r}</Pill>
            ))}
          </ControlGroup>
          <ControlGroup label="Regime">
            {(["all","stress","directional","neutral"] as RegimeKey[]).map(r => (
              <Pill key={r} active={regime === r}
                    onClick={() => setRegime(r)}>{r}</Pill>
            ))}
          </ControlGroup>
        </div>
      </header>

      {/* === EDGE SCOREBOARD + DISTRIBUTION (split row) === */}
      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-4">
        <ScoreBoard score={score} strategy={strategy}
                       baselineMaxSharpe={Math.max(...BASELINES.map(b => b.sharpe))} />
        <DistributionPanel dist={dist} />
      </section>

      {/* === TRADE TIMELINE (full width) === */}
      <section className="u-card-tight">
        <div className="flex items-center justify-between mb-2">
          <Label>Trade Timeline</Label>
          <span className="u-caption-2 text-fg-3">
            {filtered.length} trades · equity sparkline
          </span>
        </div>
        <Sparkline values={equitySeries} width={1400} height={56}
                    ariaLabel="Equity timeline" />
        <TradeMarkers trades={filtered} />
      </section>

      {/* === DECISION BREAKDOWN + REGIME ANALYSIS (split row) === */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DecisionBreakdown stats={decisionStats} />
        <RegimeAnalysis perf={perf} byRegime={byRegime} />
      </section>

      {/* === BASELINE COMPARISON TABLE === */}
      <section className="u-card-tight">
        <div className="flex items-center justify-between mb-2">
          <Label>Baseline Comparison</Label>
          <span className="u-caption-2 text-fg-3">
            best highlighted
          </span>
        </div>
        <BaselineTable perf={perf} />
      </section>

      {/* === WHAT-IF SIMULATOR === */}
      <section className="u-card-tight">
        <div className="flex items-center justify-between mb-2">
          <Label>What-if Simulator</Label>
          <div className="flex gap-2">
            <Pill active={whatif === "none"}
                  onClick={() => setWhatif("none")}>none</Pill>
            <Pill active={whatif === "remove_b"}
                  onClick={() => setWhatif("remove_b")}>remove Engine B</Pill>
            <Pill active={whatif === "gate_b"}
                  onClick={() => setWhatif("gate_b")}>gate Engine B</Pill>
          </div>
        </div>
        <WhatIfImpact baseScore={_score(_filter(
          trades ?? [], strategy, range, regime, "none"))}
                       altScore={score} mode={whatif} />
      </section>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Header controls
// ---------------------------------------------------------------------------

function ControlGroup({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="u-caption-2 text-fg-3 uppercase tracking-wider">
        {label}
      </span>
      <div className="flex gap-1">{children}</div>
    </div>
  );
}


function Pill({
  active, onClick, children,
}: { active: boolean; onClick: () => void;
     children: React.ReactNode }) {
  return (
    <button type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={cn("u-chip cursor-pointer u-btn-toggle",
        active ? "u-chip-accent" : "u-chip-neutral")}>
      {children}
    </button>
  );
}


// ---------------------------------------------------------------------------
// Edge scoreboard
// ---------------------------------------------------------------------------

function ScoreBoard({
  score, strategy, baselineMaxSharpe,
}: {
  score: ReturnType<typeof _score>;
  strategy: StrategyKey;
  baselineMaxSharpe: number;
}) {
  const verdict = _verdict(score.sharpe);
  const dvb = score.sharpe - baselineMaxSharpe;
  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-3">
        <Label>Edge Scoreboard ({_strategyName(strategy)})</Label>
        <span className={cn("u-chip", _verdictChip(verdict))}>
          {verdict}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Cell k="Sharpe" v={score.sharpe.toFixed(2)}
              tone={_sharpeTone(score.sharpe)} />
        <Cell k="Hit %" v={`${(score.hit * 100).toFixed(0)}%`}
              tone={score.hit >= 0.55 ? "pos" : score.hit < 0.4 ? "neg" : ""} />
        <Cell k="Avg ret" v={`${(score.avg * 100).toFixed(2)}%`}
              tone={score.avg > 0 ? "pos" : "neg"} />
        <Cell k="Max DD" v={`${score.dd.toFixed(2)}%`} tone="neg" />
        <Cell k="Trades" v={String(score.n)} />
        <Cell k="vs baseline"
              v={`${dvb >= 0 ? "+" : ""}${dvb.toFixed(2)}`}
              tone={dvb > 0 ? "pos" : dvb < 0 ? "neg" : ""} />
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Distribution panel
// ---------------------------------------------------------------------------

function DistributionPanel({
  dist,
}: { dist: ReturnType<typeof _histogram> }) {
  const max = Math.max(1, ...dist.bins.map(b => b.count));
  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>Return Distribution</Label>
        <span className="u-caption-2 text-fg-3">
          skew {dist.skew.toFixed(2)} · tail-3σ {dist.tail3.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-end gap-[2px] h-[80px]">
        {dist.bins.map((b, i) => (
          <div key={i}
               title={`${b.lo.toFixed(2)}% to ${b.hi.toFixed(2)}% · ${b.count}`}
               className="flex-1 rounded-t-sm"
               style={{
                 height: `${(b.count / max) * 100}%`,
                 minHeight: b.count > 0 ? "2px" : "0",
                 background: b.lo < 0
                   ? "var(--chart-negative)"
                   : "var(--chart-positive)",
                 opacity: 0.85,
               }} />
        ))}
      </div>
      <div className="flex justify-between u-caption-2 text-fg-3 mt-1">
        <span>{dist.bins[0]?.lo.toFixed(1)}%</span>
        <span>0</span>
        <span>{dist.bins[dist.bins.length - 1]?.hi.toFixed(1)}%</span>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Trade markers strip — chronological dots
// ---------------------------------------------------------------------------

function TradeMarkers({ trades }: { trades: ReturnType<typeof _filter> }) {
  if (!trades.length) return (
    <div className="u-caption-2 italic text-fg-3 mt-2">No trades.</div>
  );
  return (
    <div className="mt-2 flex flex-wrap gap-[3px]">
      {trades.map((t, i) => {
        const ret = Number(t.net_ret_pct ?? 0);
        const tone = ret > 0 ? "pos" : ret < 0 ? "neg" : "neu";
        return (
          <span key={i}
                title={`${t.entry_date} ${t.engine} ${ret.toFixed(2)}%`}
                style={{
                  display: "inline-block",
                  width: 10, height: 14, borderRadius: 2,
                  background: tone === "pos" ? "var(--chart-positive)"
                    : tone === "neg" ? "var(--chart-negative)"
                    : "var(--chart-muted)",
                  opacity: 0.85,
                }} />
        );
      })}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Decision breakdown
// ---------------------------------------------------------------------------

function DecisionBreakdown({
  stats,
}: { stats: ReturnType<typeof _decisionStats> }) {
  return (
    <div className="u-card-tight">
      <Label>Decision Breakdown</Label>
      <div className="grid grid-cols-2 gap-3 mt-3">
        <Cell k="Wins" v={String(stats.wins)} tone="pos" />
        <Cell k="Losses" v={String(stats.losses)} tone="neg" />
        <Cell k="Avg win"  v={`${(stats.avg_win * 100).toFixed(2)}%`}
              tone="pos" />
        <Cell k="Avg loss" v={`${(stats.avg_loss * 100).toFixed(2)}%`}
              tone="neg" />
        <Cell k="Best"  v={`${(stats.best * 100).toFixed(2)}%`} tone="pos" />
        <Cell k="Worst" v={`${(stats.worst * 100).toFixed(2)}%`} tone="neg" />
      </div>
      <div className="u-caption-2 text-fg-3 mt-3 italic">
        False positives = trades with positive size that lost money.
        Missed winners surfaceable once ML predictions accumulate.
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Regime analysis
// ---------------------------------------------------------------------------

function RegimeAnalysis({
  perf, byRegime,
}: {
  perf: ReturnType<typeof usePerformance>["data"];
  byRegime: Record<string, { n: number; sharpe: number; hit: number }>;
}) {
  const rows = Object.entries(byRegime);
  return (
    <div className="u-card-tight">
      <Label>Regime Analysis</Label>
      <table className="w-full u-caption-2 mt-3">
        <thead className="text-fg-3">
          <tr>
            <th className="text-left py-1">regime</th>
            <th className="text-right py-1">N</th>
            <th className="text-right py-1">Sharpe</th>
            <th className="text-right py-1">Hit %</th>
          </tr>
        </thead>
        <tbody className="u-mono-sm">
          {rows.length === 0 ? (
            <tr><td colSpan={4} className="italic text-fg-3 py-2">
              No regime data.
            </td></tr>
          ) : rows.map(([r, s]) => (
            <tr key={r}>
              <td className="py-1 text-fg">{r}</td>
              <td className="text-right">{s.n}</td>
              <td className={cn("text-right", _sharpeTone(s.sharpe))}>
                {s.sharpe.toFixed(2)}
              </td>
              <td className="text-right">
                {(s.hit * 100).toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {perf && (
        <div className="u-caption-2 text-fg-3 mt-2">
          Engine A: stress · Engine B: directional. Live perf maps to
          engine attribution.
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Baseline comparison table
// ---------------------------------------------------------------------------

function BaselineTable({
  perf,
}: { perf: ReturnType<typeof usePerformance>["data"] }) {
  const rows: Array<{label: string; sharpe: number; hit: number;
                       dd: number; n: number; tag?: string }> = [];
  if (perf?.engine_a) {
    rows.push({
      label: "Engine A",
      sharpe: Number(perf.engine_a.sharpe_proxy ?? 0),
      hit: Number(perf.engine_a.win_rate ?? 0),
      dd: 0, // engine-level drawdown not exposed by current API
      n: Number(perf.engine_a.n_trades ?? 0),
      tag: "primary",
    });
  }
  if (perf?.engine_b) {
    rows.push({
      label: "Engine B",
      sharpe: Number(perf.engine_b.sharpe_proxy ?? 0),
      hit: Number(perf.engine_b.win_rate ?? 0),
      dd: 0,
      n: Number(perf.engine_b.n_trades ?? 0),
      tag: "review",
    });
  }
  for (const b of BASELINES) {
    rows.push({
      label: b.label, sharpe: b.sharpe, hit: b.hit,
      dd: b.dd, n: b.n, tag: "baseline",
    });
  }
  const bestSharpe = Math.max(...rows.map(r => r.sharpe));
  return (
    <table className="w-full u-caption-2">
      <thead className="text-fg-3">
        <tr>
          <th className="text-left py-1">strategy</th>
          <th className="text-left py-1">tag</th>
          <th className="text-right py-1">Sharpe</th>
          <th className="text-right py-1">Hit %</th>
          <th className="text-right py-1">MaxDD %</th>
          <th className="text-right py-1">N</th>
        </tr>
      </thead>
      <tbody className="u-mono-sm">
        {rows.map(r => {
          const isBest = r.sharpe === bestSharpe;
          return (
            <tr key={r.label}
                className={cn(isBest && "bg-accent-subtle")}>
              <td className="py-1 text-fg font-medium">
                {r.label} {isBest ? "★" : ""}
              </td>
              <td className="text-fg-3">{r.tag ?? ""}</td>
              <td className={cn("text-right",
                _sharpeTone(r.sharpe))}>
                {r.sharpe.toFixed(2)}
              </td>
              <td className="text-right">{(r.hit * 100).toFixed(0)}%</td>
              <td className="text-right text-danger">
                {r.dd.toFixed(2)}
              </td>
              <td className="text-right">{r.n}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}


// ---------------------------------------------------------------------------
// What-if simulator
// ---------------------------------------------------------------------------

function WhatIfImpact({
  baseScore, altScore, mode,
}: {
  baseScore: ReturnType<typeof _score>;
  altScore: ReturnType<typeof _score>;
  mode: "none" | "remove_b" | "gate_b";
}) {
  const dSharpe = altScore.sharpe - baseScore.sharpe;
  const dHit    = altScore.hit - baseScore.hit;
  const dN      = altScore.n - baseScore.n;
  return (
    <div>
      <div className="grid grid-cols-3 gap-3">
        <Cell k="ΔSharpe"
              v={`${dSharpe >= 0 ? "+" : ""}${dSharpe.toFixed(2)}`}
              tone={dSharpe > 0 ? "pos" : dSharpe < 0 ? "neg" : ""} />
        <Cell k="ΔHit"
              v={`${dHit >= 0 ? "+" : ""}${(dHit * 100).toFixed(1)}%`}
              tone={dHit > 0 ? "pos" : dHit < 0 ? "neg" : ""} />
        <Cell k="Trades"
              v={`${dN >= 0 ? "+" : ""}${dN}`}
              tone="" />
      </div>
      <div className="u-caption-2 text-fg-3 mt-2 italic">
        {mode === "none" && "Apply a what-if scenario above."}
        {mode === "remove_b"
          && "Engine B removed. ΔSharpe shows aggregate change."}
        {mode === "gate_b"
          && "Engine B gated to 0.5× size. Conservative impact."}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Generic cells
// ---------------------------------------------------------------------------

function Cell({ k, v, tone = "" }: {
  k: string; v: string; tone?: string;
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{k}</div>
      <div className={cn("u-mono-sm font-semibold", cls)}>{v}</div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function _filter(
  trades: any[],
  strategy: StrategyKey,
  range: RangeKey,
  regime: RegimeKey,
  whatif: "none" | "remove_b" | "gate_b",
): any[] {
  let out = trades.filter(
    t => t.status === "closed" && t.net_ret_pct != null,
  );
  // Strategy filter
  if (strategy === "engine_a") out = out.filter(t => t.engine === "A");
  else if (strategy === "engine_b") out = out.filter(t => t.engine === "B");
  else if (strategy === "baseline") out = [];   // baseline data static

  // Regime filter
  if (regime !== "all") {
    out = out.filter(t =>
      (t.regime_at_entry ?? "").toLowerCase() === regime,
    );
  }
  // Range filter
  if (range !== "ALL" && out.length) {
    const cutoff = (() => {
      const today = new Date();
      switch (range) {
        case "30D": today.setDate(today.getDate() - 30); return today;
        case "90D": today.setDate(today.getDate() - 90); return today;
        case "YTD": return new Date(today.getFullYear(), 0, 1);
      }
    })()!;
    out = out.filter(t => new Date(t.entry_date) >= cutoff);
  }

  // What-if
  if (whatif === "remove_b") {
    out = out.filter(t => t.engine !== "B");
  }
  if (whatif === "gate_b") {
    // Halve B contribution by halving net_ret_pct (approximation)
    out = out.map(t => t.engine === "B"
      ? { ...t, net_ret_pct: Number(t.net_ret_pct) * 0.5 }
      : t);
  }
  return out;
}


function _score(trades: any[]) {
  const rets = trades.map(t => Number(t.net_ret_pct) / 100)
                       .filter(r => Number.isFinite(r));
  const n = rets.length;
  if (n === 0) return {
    n: 0, sharpe: 0, hit: 0, avg: 0, dd: 0, total: 0,
  };
  const mean = rets.reduce((s, r) => s + r, 0) / n;
  const variance = n > 1
    ? rets.reduce((s, r) => s + (r - mean) ** 2, 0) / (n - 1) : 0;
  const sd = Math.sqrt(variance);
  const sharpe = sd > 0 ? mean / sd * Math.sqrt(252) : 0;
  const hit = rets.filter(r => r > 0).length / n;
  // Equity-style max DD
  let peak = 1.0, maxDD = 0;
  let eq = 1.0;
  for (const r of rets) {
    eq *= (1 + r);
    peak = Math.max(peak, eq);
    maxDD = Math.min(maxDD, (eq - peak) / peak * 100);
  }
  const total = (eq - 1) * 100;
  return { n, sharpe, hit, avg: mean, dd: maxDD, total };
}


function _histogram(trades: any[], bins = 24) {
  const rets = trades.map(t => Number(t.net_ret_pct))
                       .filter(r => Number.isFinite(r));
  if (rets.length === 0) {
    return { bins: [], skew: 0, tail3: 0 };
  }
  const min = Math.min(...rets), max = Math.max(...rets);
  const range = (max - min) || 1;
  const step = range / bins;
  const counts = Array(bins).fill(0).map((_, i) => ({
    lo: min + step * i, hi: min + step * (i + 1), count: 0,
  }));
  for (const r of rets) {
    let idx = Math.floor((r - min) / step);
    if (idx >= bins) idx = bins - 1;
    counts[idx].count++;
  }
  const mean = rets.reduce((s, r) => s + r, 0) / rets.length;
  const variance = rets.reduce((s, r) => s + (r - mean) ** 2, 0)
    / Math.max(1, rets.length - 1);
  const sd = Math.sqrt(variance);
  const skew = sd > 0
    ? rets.reduce((s, r) => s + ((r - mean) / sd) ** 3, 0) / rets.length
    : 0;
  const tail3 = mean - 3 * sd;
  return { bins: counts, skew, tail3 };
}


function _decisionStats(trades: any[]) {
  const rets = trades.map(t => Number(t.net_ret_pct) / 100);
  const wins = rets.filter(r => r > 0);
  const losses = rets.filter(r => r < 0);
  return {
    wins: wins.length,
    losses: losses.length,
    avg_win: wins.length ? wins.reduce((s, r) => s + r, 0) / wins.length : 0,
    avg_loss: losses.length
      ? losses.reduce((s, r) => s + r, 0) / losses.length : 0,
    best: rets.length ? Math.max(...rets) : 0,
    worst: rets.length ? Math.min(...rets) : 0,
  };
}


function _byRegime(trades: any[]) {
  const out: Record<string, { n: number; sharpe: number; hit: number }> = {};
  const groups: Record<string, number[]> = {};
  for (const t of trades) {
    if (t.status !== "closed" || t.net_ret_pct == null) continue;
    const r = (t.regime_at_entry ?? "unknown").toLowerCase();
    (groups[r] ??= []).push(Number(t.net_ret_pct) / 100);
  }
  for (const [k, arr] of Object.entries(groups)) {
    const score = _score(arr.map(r => ({ net_ret_pct: r * 100,
                                           status: "closed" })));
    out[k] = { n: score.n, sharpe: score.sharpe, hit: score.hit };
  }
  return out;
}


function _strategyName(s: StrategyKey): string {
  return s === "engine_a" ? "Engine A"
    : s === "engine_b" ? "Engine B"
    : s === "baseline" ? "Baseline"
    : "Combined";
}


function _verdict(sharpe: number): "STRONG" | "WEAK" | "NEGATIVE" {
  if (sharpe >= 1.0) return "STRONG";
  if (sharpe < 0) return "NEGATIVE";
  return "WEAK";
}

function _verdictChip(v: string): string {
  if (v === "STRONG") return "u-chip-success";
  if (v === "NEGATIVE") return "u-chip-danger";
  return "u-chip-warning";
}

function _sharpeTone(s: number): string {
  if (s >= 1.0) return "text-success";
  if (s < -0.3) return "text-danger";
  if (s < 0.5) return "text-warning";
  return "text-fg";
}
