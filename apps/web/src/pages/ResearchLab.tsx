// ALPHA LAB — non-prod signal observatory + pattern mining.
// Every tab shows real computed content from trades + anomalies + shadow
// signals. No empty states.

import { useMemo, useState } from "react";
import {
  useShadowSignals, useAnomalies, usePaperTrades, usePerformance,
} from "@/lib/operator/hooks";
import {
  Card, Label, SectionHeader,
  fmtPct, toneForNumber,
} from "@/components/ui/primitives";
import type { TradeRow, ShadowSignal } from "@/lib/operator/types";
import { cn } from "@/lib/cn";
// Phase 13e — narrative-flow chapter rail
import PageChapter from "@/components/shell/PageChapter";

const TABS = [
  { id: "signals",   label: "Signals" },
  { id: "wins",      label: "Top Wins" },
  { id: "losses",    label: "Top Losses" },
  { id: "patterns",  label: "Patterns" },
] as const;
type TabId = typeof TABS[number]["id"];

export default function ResearchLab() {
  const [tab, setTab] = useState<TabId>("signals");

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6">
      <div className="picks-root picks-root-inline">
        <PageChapter pathname="/research" />
      </div>
      <div className="u-lab-mode">
        <header className="mb-6 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Label>Research</Label>
              <span className="u-chip u-lab-chip">experimental</span>
            </div>
            <h1 className="u-title-lg mt-1">Alpha Lab</h1>
            <p className="u-body mt-2 max-w-3xl">
              Observatory for candidate signals, winning/losing pattern
              mining, and ideas under evaluation. Status per signal shown
              inline (production / candidate / diagnostic).
            </p>
          </div>
        </header>

        <nav className="flex gap-0.5 -mb-[1px]">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cn(
                "px-4 py-2.5 text-[13px] border-b-2 transition-colors",
                tab === t.id
                  ? "u-lab-tab-active font-semibold"
                  : "border-transparent text-fg-3 hover:text-fg-2",
              )}>
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="mb-6" />

      {tab === "signals"  && <SignalsTab />}
      {tab === "wins"     && <WinsTab />}
      {tab === "losses"   && <LossesTab />}
      {tab === "patterns" && <PatternsTab />}
    </div>
  );
}

// =========================================================================
// SIGNALS — shadow feature registry + shadow-flagged anomalies
// =========================================================================

function SignalsTab() {
  const { data: shadow } = useShadowSignals();
  const { data: anomalies } = useAnomalies("open");
  const shadowAnomalies = (anomalies ?? [])
    .filter(a => a.category === "shadow");

  // Fallback registry — phase X1/X2/X3 results even if registry empty
  const knownSignals: ShadowSignal[] = [
    {
      name: "flow_persistence",
      status: "diagnostic",
      value: null,
      value_display: "Phase X FAIL",
      context_flag: null,
      source: "Phase X experiment",
      last_updated: "2026-01-15",
      notes: "Flow persistence overlay — tested; did not contain 2026 regime shift",
    },
    {
      name: "vix_term_structure",
      status: "diagnostic",
      value: null,
      value_display: "Phase X2 FAIL",
      context_flag: null,
      source: "Phase X2 experiment",
      last_updated: "2026-02-03",
      notes: "VIX term structure overlay — no OOS separation",
    },
    {
      name: "gex_sign",
      status: "diagnostic",
      value: null,
      value_display: "Phase X3 FAIL",
      context_flag: null,
      source: "Phase X3 SqueezeMetrics",
      last_updated: "2026-02-28",
      notes: "Dealer gamma overlay — failed OOS validation",
    },
    {
      name: "d10y_5d",
      status: "candidate",
      value: null,
      value_display: "Phase 19 cleanest",
      context_flag: null,
      source: "FRED DGS10",
      last_updated: "2026-04-01",
      notes: "10Y yield 5d direction — Phase 19 top cross-asset separator",
    },
  ];

  // Phase 15a — Truth fix. Earlier this page silently substituted the
  // knownSignals fallback rows for live data when /api/shadow returned
  // empty, with no visual distinction. usingFallback gates a visible
  // banner so the user can tell static registry baseline from live.
  const usingFallback = !(shadow && shadow.length > 0);
  const signals: ShadowSignal[] = usingFallback ? knownSignals : (shadow ?? []);

  return (
    <div className="space-y-5">
      <Card size="md">
        <SectionHeader title="Shadow Signal Registry"
          hint={usingFallback
            ? "Static registry baseline — no live shadow signals this cycle."
            : "Observed in parallel — status per signal shown inline."} />
        {usingFallback && (
          <div className="mb-3 inline-flex items-center gap-2 rounded-md
                          border border-b1 px-2.5 py-1 text-[10px] font-semibold
                          tracking-[0.16em] uppercase text-fg-3"
               role="note">
            Static baseline · not live data
          </div>
        )}
        <div className="divide-y divide-b1">
          {signals.map(s => (
            <SignalRow key={s.name} s={s} />
          ))}
        </div>
      </Card>

      <Card size="md">
        <SectionHeader title="Shadow-flagged Patterns"
          hint="Clustering of losers / divergence — diagnostic scanner." />
        {shadowAnomalies.length === 0 ? (
          <div className="u-caption text-fg-2 py-2">
            No shadow-flagged divergences this cycle. The scanner evaluates
            every bar for loser-clustering, factor drift, and regime
            inconsistency.
          </div>
        ) : (
          <ul className="divide-y divide-b1">
            {shadowAnomalies.map(a => (
              <li key={a.id} className="py-3">
                <div className="u-caption text-fg font-medium">{a.title}</div>
                <div className="u-caption-2 mt-1">{a.description}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function SignalRow({ s }: { s: ShadowSignal }) {
  const toneChip = s.status === "production" ? "success"
    : s.status === "candidate" ? "warning" : "danger";
  const plain = plainEnglishForSignal(s.name, s.status);
  return (
    <div className="py-3 flex items-start gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="u-mono font-semibold">{s.name}</span>
          <span className={`u-chip u-chip-${toneChip}`}>{s.status}</span>
          <span className="u-caption-2 text-fg-3 italic">
            {statusSuffix(s.status)}
          </span>
        </div>
        <div className="u-caption text-fg-2 leading-snug mb-1">
          {plain}
        </div>
        {s.notes && (
          <div className="u-caption-2">{s.notes}</div>
        )}
      </div>
      <div className="text-right shrink-0">
        <div className="u-label-sm">Value</div>
        <div className="u-mono mt-1">{s.value_display}</div>
      </div>
    </div>
  );
}


const PLAIN_SIGNAL: Record<string, string> = {
  gex_sign:
    "Options market pressure signal. Currently diagnostic — not used for trading.",
  ts_ratio:
    "Trend-strength ratio. Under evaluation — not affecting live trades.",
  cot_extreme_flag:
    "Positioning extreme signal. Not yet wired into production.",
  flow_persistence:
    "Flow-persistence overlay. Tested and retired — kept for audit only.",
  vix_term_structure:
    "VIX term-structure overlay. Failed out-of-sample validation.",
  d10y_5d:
    "10Y yield 5-day direction. Cleanest cross-asset separator in Phase 19 probe.",
};


function plainEnglishForSignal(name: string, status: string): string {
  const mapped = PLAIN_SIGNAL[name];
  if (mapped) return mapped;
  const s = status === "production"
    ? "Active production signal — influences trading decisions."
    : status === "candidate"
      ? "Candidate signal under evaluation — not yet live."
      : "Diagnostic signal — observed, not used for trading.";
  return s;
}


function statusSuffix(status: string): string {
  if (status === "production") return "live";
  if (status === "candidate")  return "evaluating";
  return "observe only";
}

// =========================================================================
// TOP WINS — closed winners sorted by net return
// =========================================================================

function WinsTab() {
  const { data: trades } = usePaperTrades();
  const winners = useMemo(() =>
    (trades ?? [])
      .filter(t => t.status === "closed" && (t.net_ret_pct ?? 0) > 0)
      .sort((a, b) => (b.net_ret_pct ?? 0) - (a.net_ret_pct ?? 0))
      .slice(0, 15),
  [trades]);

  return (
    <Card size="md">
      <SectionHeader title="Top Winning Trades"
        hint="Closed positive returns, ranked. Diagnostic — already reflected in Engine A/B attribution." />
      {winners.length === 0 ? (
        <FallbackStrip reason="No closed winners yet."
                        subline="Shows the moment the first positive trade closes." />
      ) : (
        <TradeList trades={winners} />
      )}
    </Card>
  );
}

// =========================================================================
// TOP LOSSES
// =========================================================================

function LossesTab() {
  const { data: trades } = usePaperTrades();
  const losers = useMemo(() =>
    (trades ?? [])
      .filter(t => t.status === "closed" && (t.net_ret_pct ?? 0) < 0)
      .sort((a, b) => (a.net_ret_pct ?? 0) - (b.net_ret_pct ?? 0))
      .slice(0, 15),
  [trades]);

  return (
    <Card size="md">
      <SectionHeader title="Top Losing Trades"
        hint="Worst closed trades, ranked. Mine these for repeated failure patterns." />
      {losers.length === 0 ? (
        <FallbackStrip reason="No closed losers yet — system has been clean."
                        subline="Losses accrue into this list as they close." />
      ) : (
        <TradeList trades={losers} />
      )}
    </Card>
  );
}

function TradeList({ trades }: { trades: TradeRow[] }) {
  if (trades.length === 0) return null;
  const maxAbs = Math.max(...trades.map(t => Math.abs(t.net_ret_pct ?? 0)), 0.01);
  return (
    <div className="space-y-2">
      {trades.map((t, idx) => {
        const tone = toneForNumber(t.net_ret_pct ?? 0);
        const cls = tone === "pos" ? "text-success" : "text-danger";
        const rankCls = idx === 0 ? "is-gold"
          : idx === 1 ? "is-silver"
          : idx === 2 ? "is-bronze" : "";
        const podium = idx < 3;
        const barPct = Math.abs(t.net_ret_pct ?? 0) / maxAbs * 100;
        return (
          <div key={t.trade_id}
               className={cn("u-card-tight flex items-center gap-4",
                              podium && "border-b2")}
               style={podium
                 ? { padding: "14px 16px",
                     background: idx === 0
                       ? "linear-gradient(90deg, rgba(248,166,56,0.06), transparent 50%)"
                       : idx === 1
                         ? "linear-gradient(90deg, rgba(180,195,220,0.04), transparent 50%)"
                         : "linear-gradient(90deg, rgba(205,127,50,0.05), transparent 50%)" }
                 : { padding: "10px 14px" }}>
            <span className={cn("u-rank", rankCls)}>{idx + 1}</span>
            <div className="w-24 shrink-0">
              <div className="u-mono-sm text-fg">{t.entry_date}</div>
              <div className="u-caption-2 mt-0.5">
                {t.days_held !== null ? `${t.days_held}d` : "—"}
              </div>
            </div>
            <span className="u-chip u-chip-accent shrink-0">{t.engine}</span>
            <span className="u-caption text-fg-2 uppercase tracking-wide
                              w-24 shrink-0">
              {t.regime_at_entry}
            </span>
            <div className="flex-1 min-w-0">
              <div className="u-bar-track">
                <div className={cn("u-bar-fill",
                  tone === "pos" ? "is-pos" : "is-neg")}
                  style={{ left: 0, width: `${barPct}%` }} />
              </div>
              <div className="u-caption-2 mt-1 truncate">
                ${t.entry_price.toFixed(2)} → ${t.exit_price?.toFixed(2) ?? "—"}
              </div>
            </div>
            <span className={cn(
              podium ? "u-num-lg font-bold" : "u-num-md font-semibold",
              cls, "shrink-0")}>
              {fmtPct(t.net_ret_pct)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// =========================================================================
// PATTERNS — computed analysis across trade history
// =========================================================================

function PatternsTab() {
  const { data: trades } = usePaperTrades();
  const { data: perf } = usePerformance();
  const closed = (trades ?? []).filter(t =>
    t.status === "closed" && t.net_ret_pct !== null);

  const byRegime = useMemo(
    () => groupBy(closed, t => t.regime_at_entry ?? "unknown"),
    [closed],
  );
  const byEngine = useMemo(() => groupBy(closed, t => t.engine), [closed]);

  const bestRegime = pickTopByAvg(byRegime);
  const worstRegime = pickBottomByAvg(byRegime);
  const bestEngine = pickTopByAvg(byEngine);

  const durations = closed.filter(t => t.days_held !== null);
  const avgHold = durations.length > 0
    ? durations.reduce((s, t) => s + (t.days_held ?? 0), 0) / durations.length
    : 0;

  const winRateByRegime = Object.entries(byRegime).map(([k, arr]) => ({
    key: k,
    wr: arr.length > 0
      ? arr.filter(t => (t.net_ret_pct ?? 0) > 0).length / arr.length : 0,
    n: arr.length,
  }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Card size="md">
          <Label>Best regime</Label>
          <div className="u-num-md mt-2 uppercase">
            {bestRegime ? bestRegime.key : "—"}
          </div>
          <div className="u-caption-2 mt-2">
            {bestRegime
              ? `avg ${fmtPct(bestRegime.avg)} · n=${bestRegime.n}`
              : "insufficient data"}
          </div>
        </Card>
        <Card size="md">
          <Label>Worst regime</Label>
          <div className="u-num-md mt-2 uppercase">
            {worstRegime ? worstRegime.key : "—"}
          </div>
          <div className="u-caption-2 mt-2">
            {worstRegime
              ? `avg ${fmtPct(worstRegime.avg)} · n=${worstRegime.n}`
              : "insufficient data"}
          </div>
        </Card>
        <Card size="md">
          <Label>Dominant engine</Label>
          <div className="u-num-md mt-2">
            Engine {bestEngine ? bestEngine.key : "—"}
          </div>
          <div className="u-caption-2 mt-2">
            {bestEngine
              ? `avg ${fmtPct(bestEngine.avg)} · n=${bestEngine.n}`
              : "insufficient data"}
          </div>
        </Card>
      </div>

      <Card size="md">
        <SectionHeader title="Win Rate × Regime"
          hint="Hit-rate of closed trades broken down by entry regime." />
        <div className="space-y-4">
          {winRateByRegime.length === 0 ? (
            <FallbackStrip reason="No closed trades yet to analyse."
                            subline="Table populates once the first trade closes." />
          ) : winRateByRegime.map(r => {
            const toneCls = r.wr >= 0.55 ? "is-pos"
              : r.wr < 0.4 ? "is-neg" : "is-warning";
            const textCls = r.wr >= 0.55 ? "text-success"
              : r.wr < 0.4 ? "text-danger" : "text-warning";
            return (
              <div key={r.key}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="u-caption uppercase tracking-wider
                                     text-fg font-semibold">
                    {r.key}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className={cn("u-num-md font-bold", textCls)}>
                      {(r.wr * 100).toFixed(0)}%
                    </span>
                    <span className="u-caption-2">n={r.n}</span>
                  </div>
                </div>
                <div className="u-bar-track is-thick">
                  <div className={cn("u-bar-fill", toneCls)}
                       style={{ left: 0,
                                width: `${Math.max(r.wr * 100, 2)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card size="md">
        <SectionHeader title="Execution Summary" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <PatternStat label="Total closed" value={String(closed.length)} />
          <PatternStat label="Avg hold"
                       value={`${avgHold.toFixed(1)}d`} />
          <PatternStat label="Engine A trades"
                       value={String(perf?.engine_a.n_trades ?? 0)} />
          <PatternStat label="Engine B trades"
                       value={String(perf?.engine_b.n_trades ?? 0)} />
        </div>
      </Card>
    </div>
  );
}

function PatternStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="u-label-sm mb-2">{label}</div>
      <div className="u-num-md text-fg">{value}</div>
    </div>
  );
}

function FallbackStrip({ reason, subline }: {
  reason: string; subline: string;
}) {
  return (
    <div className="u-card-tight"
         style={{ background: "var(--accent-subtle)",
                  borderColor: "rgba(75,139,255,0.25)" }}>
      <div className="flex items-start gap-3">
        <span className="u-dot u-dot-accent mt-1.5" />
        <div>
          <div className="u-caption text-fg font-medium">{reason}</div>
          <div className="u-caption-2 mt-1">{subline}</div>
        </div>
      </div>
    </div>
  );
}

function groupBy<T, K extends string>(
  arr: T[], fn: (t: T) => K,
): Record<K, T[]> {
  const out = {} as Record<K, T[]>;
  for (const x of arr) {
    const k = fn(x);
    (out[k] ??= []).push(x);
  }
  return out;
}

function pickTopByAvg<K extends string>(groups: Record<K, TradeRow[]>):
  { key: K; avg: number; n: number } | null {
  const entries = (Object.entries(groups) as [K, TradeRow[]][])
    .filter(([, v]) => v.length > 0)
    .map(([k, v]) => ({
      key: k,
      avg: v.reduce((s, t) => s + (t.net_ret_pct ?? 0), 0) / v.length,
      n: v.length,
    }));
  if (entries.length === 0) return null;
  return entries.sort((a, b) => b.avg - a.avg)[0];
}

function pickBottomByAvg<K extends string>(groups: Record<K, TradeRow[]>):
  { key: K; avg: number; n: number } | null {
  const entries = (Object.entries(groups) as [K, TradeRow[]][])
    .filter(([, v]) => v.length > 0)
    .map(([k, v]) => ({
      key: k,
      avg: v.reduce((s, t) => s + (t.net_ret_pct ?? 0), 0) / v.length,
      n: v.length,
    }));
  if (entries.length === 0) return null;
  return entries.sort((a, b) => a.avg - b.avg)[0];
}
