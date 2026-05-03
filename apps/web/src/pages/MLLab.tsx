// ML Lab — production-grade ML validation console.
// UI + data aggregation only. ML stays advisory, no model/risk changes.

import { useMemo } from "react";
import {
  useShadowLatestReport, usePromotionStatus, useHybridStatus,
} from "@/lib/ml/shadow";
import { usePaperTrades, usePerformance } from "@/lib/operator/hooks";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";


export default function MLLab() {
  const { data: shadow } = useShadowLatestReport();
  const { data: promo } = usePromotionStatus();
  const { data: hyb } = useHybridStatus();
  const { data: trades } = usePaperTrades();
  const { data: perf } = usePerformance();

  const status = useMemo(() => _statusBar({ shadow, promo, hyb }),
                            [shadow, promo, hyb]);
  const decisionQual = useMemo(() => _decisionQuality(trades ?? []),
                                  [trades]);
  const regimeMl = useMemo(() => _byRegime(trades ?? []), [trades]);
  const buckets = useMemo(() => _confidenceBuckets(trades ?? []),
                              [trades]);

  return (
    <div className="max-w-[1520px] mx-auto px-6 py-6 space-y-4">
      <header>
        <Label>ML Lab</Label>
        <h1 className="u-title mt-1">ML Validation Console</h1>
        <p className="u-caption mt-0.5">
          Advisory-only. No execution. Promotion is gated, never automatic.
        </p>
      </header>

      {/* Status bar */}
      <StatusBar s={status} />

      {/* Comparison + Decision quality */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ComparisonTable perf={perf} promo={promo} />
        <DecisionQuality stats={decisionQual} />
      </section>

      {/* Calibration + Regime perf */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CalibrationPanel shadow={shadow} promo={promo} />
        <RegimePerformance ml={regimeMl} />
      </section>

      {/* Confidence vs outcome */}
      <ConfidenceVsOutcome buckets={buckets} />

      {/* ML impact + Shadow timeline */}
      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-4">
        <MLImpact promo={promo} />
        <ShadowTimeline trades={trades ?? []} />
      </section>

      {/* Promotion readiness checklist */}
      <PromotionChecklist promo={promo} hyb={hyb} shadow={shadow} />
    </div>
  );
}


// ---------------------------------------------------------------------------
// 1. Status bar
// ---------------------------------------------------------------------------

function StatusBar({
  s,
}: { s: ReturnType<typeof _statusBar> }) {
  return (
    <section className="u-card-tight">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Cell k="Mode" v={s.mode} tone={s.mode === "advisory" ? "" : "warn"} />
        <Cell k="Shadow runs" v={String(s.runs)} />
        <Cell k="Labeled" v={String(s.labeled)} />
        <Cell k="Healthy days"
              v={`${s.healthy_days}/${s.required_healthy_days}`} />
        <Cell k="Promotion" v={s.promo_state.toLowerCase().replace(/_/g," ")}
              tone={s.promo_state === "READY_FOR_PAPER_REDUCE" ? "pos"
                    : s.promo_state === "ADVISORY_HEALTHY" ? "" : "warn"} />
        <Cell k="Next milestone" v={s.next_milestone} />
      </div>
    </section>
  );
}


// ---------------------------------------------------------------------------
// 2. ML vs Deterministic vs Baseline
// ---------------------------------------------------------------------------

function ComparisonTable({
  perf, promo,
}: {
  perf: ReturnType<typeof usePerformance>["data"];
  promo: ReturnType<typeof usePromotionStatus>["data"];
}) {
  const w30 = promo?.windows?.["30"];
  const detSharpe = w30?.metrics
    ? Number((w30.metrics as Record<string, unknown>)["det_sharpe_proxy"] ?? NaN)
    : (Number(perf?.engine_a?.sharpe_proxy ?? 0)
       + Number(perf?.engine_b?.sharpe_proxy ?? 0)) / 2;
  const cfSharpe = w30?.metrics
    ? Number((w30.metrics as Record<string, unknown>)["cf_sharpe_proxy"] ?? NaN)
    : NaN;
  const dSharpe = (Number.isFinite(cfSharpe) && Number.isFinite(detSharpe))
    ? cfSharpe - detSharpe : null;
  const baselineMax = 1.02;   // TSMOM 60d, static for now

  const rows: Array<{label: string; sharpe: number; hit: number;
                       n: number; tag: string}> = [
    { label: "Deterministic (live)",
      sharpe: detSharpe || 0, hit: 0,
      n: w30?.deterministic_trades ?? 0, tag: "live" },
    { label: "ML counterfactual",
      sharpe: cfSharpe || 0,
      hit: 0,
      n: w30?.ml_advice_count ?? 0, tag: "advisory" },
    { label: "Baseline TSMOM 60d",
      sharpe: 1.02, hit: 0.40, n: 1588, tag: "shadow" },
    { label: "Baseline B&H",
      sharpe: 0.72, hit: 0.54, n: 1588, tag: "shadow" },
  ];
  const best = Math.max(...rows.map(r => r.sharpe));

  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>ML vs Deterministic vs Baseline</Label>
        <span className="u-caption-2 text-fg-3">
          ΔvsBase {(rows[1].sharpe - baselineMax).toFixed(2)} ·
          ΔvsDet {dSharpe != null ? dSharpe.toFixed(2) : "—"}
        </span>
      </div>
      <table className="w-full u-caption-2">
        <thead className="text-fg-3">
          <tr>
            <th className="text-left py-1">strategy</th>
            <th className="text-left py-1">tag</th>
            <th className="text-right py-1">Sharpe</th>
            <th className="text-right py-1">N</th>
          </tr>
        </thead>
        <tbody className="u-mono-sm">
          {rows.map(r => (
            <tr key={r.label}
                className={cn(r.sharpe === best && "bg-accent-subtle")}>
              <td className="py-1 text-fg">{r.label}</td>
              <td className="text-fg-3">{r.tag}</td>
              <td className={cn("text-right", _sharpeTone(r.sharpe))}>
                {r.sharpe.toFixed(2)}
              </td>
              <td className="text-right">{r.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ---------------------------------------------------------------------------
// 3. Decision quality (TP/FP/TN/FN)
// ---------------------------------------------------------------------------

function DecisionQuality({
  stats,
}: { stats: ReturnType<typeof _decisionQuality> }) {
  const { tp, fp, tn, fn, n } = stats;
  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-3">
        <Label>Decision Quality</Label>
        <span className="u-caption-2 text-fg-3">
          n={n}{n === 0 ? " · awaiting outcomes" : ""}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <ConfusionCell label="TP" value={tp} tone="pos" />
        <ConfusionCell label="FP" value={fp} tone="neg" />
        <ConfusionCell label="TN" value={tn} tone="pos" />
        <ConfusionCell label="FN" value={fn} tone="neg" />
      </div>
      <div className="grid grid-cols-2 gap-3 mt-3">
        <Cell k="False allow rate"
              v={n ? `${(fp / Math.max(1, fp + tp) * 100).toFixed(1)}%` : "—"}
              tone={n && fp / Math.max(1, fp + tp) > 0.35 ? "neg" : ""} />
        <Cell k="False avoid rate"
              v={n ? `${(fn / Math.max(1, fn + tn) * 100).toFixed(1)}%` : "—"}
              tone={n && fn / Math.max(1, fn + tn) > 0.35 ? "neg" : ""} />
        <Cell k="Missed winner %"
              v={n ? `${(fn / Math.max(1, fn + tp) * 100).toFixed(1)}%` : "—"} />
        <Cell k="Bad trade capture"
              v={n ? `${(tn / Math.max(1, tn + fp) * 100).toFixed(1)}%` : "—"}
              tone="pos" />
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// 4. Calibration panel
// ---------------------------------------------------------------------------

function CalibrationPanel({
  shadow, promo,
}: {
  shadow: ReturnType<typeof useShadowLatestReport>["data"];
  promo: ReturnType<typeof usePromotionStatus>["data"];
}) {
  const cal = shadow?.latest_model_run?.calibration;
  const ece = cal?.ece;
  const w30 = promo?.windows?.["30"];
  const ece30 = w30?.calibration_ece;

  // Simple synthetic reliability curve from buckets (placeholder until
  // backend exposes bucketed predictions).
  const ideal = Array.from({ length: 10 }, (_, i) => i / 10);

  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>Calibration</Label>
        <span className={cn("u-chip",
          (ece ?? 999) < 0.10 ? "u-chip-success" : "u-chip-warning")}>
          ECE {ece != null ? ece.toFixed(3) : "—"}
        </span>
      </div>
      <svg viewBox="0 0 200 100" width="100%" height="120"
           role="img" aria-label="reliability curve placeholder">
        {/* Diagonal ideal line */}
        <line x1="10" y1="90" x2="190" y2="10"
              stroke="var(--chart-muted)" strokeDasharray="3 3" />
        {/* Bands */}
        {ideal.map((p, i) => (
          <circle key={i}
                  cx={10 + p * 180}
                  cy={90 - p * 80}
                  r={2.5}
                  fill="var(--accent)" />
        ))}
      </svg>
      <div className="grid grid-cols-3 gap-3 mt-2">
        <Cell k="ECE (latest run)"
              v={ece != null ? ece.toFixed(3) : "—"}
              tone={(ece ?? 0) > 0.10 ? "neg" : "pos"} />
        <Cell k="ECE (30d window)"
              v={ece30 != null ? Number(ece30).toFixed(3) : "—"}
              tone={(Number(ece30 ?? 0)) > 0.10 ? "neg" : "pos"} />
        <Cell k="Brier"
              v={cal?.brier != null ? cal.brier.toFixed(3) : "—"} />
      </div>
      <div className="u-caption-2 text-fg-3 mt-2 italic">
        Diagonal = perfect calibration. Live reliability curve renders
        once bucketed predictions accumulate.
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// 5. Regime performance
// ---------------------------------------------------------------------------

function RegimePerformance({
  ml,
}: { ml: ReturnType<typeof _byRegime> }) {
  const rows = Object.entries(ml);
  return (
    <div className="u-card-tight">
      <Label>Regime Performance (deterministic now, ML once available)</Label>
      <table className="w-full u-caption-2 mt-2">
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
    </div>
  );
}


// ---------------------------------------------------------------------------
// 6. Confidence vs outcome
// ---------------------------------------------------------------------------

function ConfidenceVsOutcome({
  buckets,
}: { buckets: { lo: number; hi: number; n: number; hit: number }[] }) {
  const max = Math.max(1, ...buckets.map(b => b.n));
  return (
    <section className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>Confidence vs Outcome</Label>
        <span className="u-caption-2 text-fg-3">
          predicted band × actual win rate
        </span>
      </div>
      {buckets.every(b => b.n === 0) ? (
        <div className="u-caption-2 italic text-fg-3">
          Awaiting bucketed ML predictions. Currently using
          deterministic confidence proxy.
        </div>
      ) : (
        <div className="grid grid-cols-5 gap-2">
          {buckets.map((b, i) => (
            <div key={i}
                 className="u-card-tight"
                 style={{ padding: "8px" }}>
              <div className="u-caption-2 text-fg-3">
                {b.lo.toFixed(1)}–{b.hi.toFixed(1)}
              </div>
              <div className="u-mono-sm font-semibold mt-1">
                hit {(b.hit * 100).toFixed(0)}%
              </div>
              <div className="u-caption-2 text-fg-3 mt-0.5">
                n={b.n}
              </div>
              <div className="h-[4px] mt-1 rounded-full overflow-hidden"
                   style={{ background: "var(--border-2)" }}>
                <div className="h-full"
                     style={{
                       width: `${(b.n / max) * 100}%`,
                       background: "var(--accent)",
                     }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


// ---------------------------------------------------------------------------
// 7. ML impact
// ---------------------------------------------------------------------------

function MLImpact({
  promo,
}: { promo: ReturnType<typeof usePromotionStatus>["data"] }) {
  const w30 = promo?.windows?.["30"];
  const reduce = w30?.ml_reduce_count ?? 0;
  const avoid = w30?.ml_avoid_count ?? 0;
  const dSharpe = w30?.delta_sharpe_vs_deterministic;
  return (
    <div className="u-card-tight">
      <Label>ML Impact (30d)</Label>
      <div className="grid grid-cols-3 gap-3 mt-3">
        <Cell k="Reduces" v={String(reduce)} />
        <Cell k="Avoids" v={String(avoid)} />
        <Cell k="ΔSharpe (cf)"
              v={dSharpe != null ? Number(dSharpe).toFixed(2) : "—"}
              tone={dSharpe != null && Number(dSharpe) > 0 ? "pos"
                    : dSharpe != null && Number(dSharpe) < 0 ? "neg" : ""} />
        <Cell k="Avoided loss est"
              v={w30?.avoided_loss_estimate != null
                  ? `${Number(w30.avoided_loss_estimate).toFixed(2)}%` : "—"} />
        <Cell k="Missed winner est"
              v={w30?.missed_winner_estimate != null
                  ? `${Number(w30.missed_winner_estimate).toFixed(2)}%` : "—"} />
        <Cell k="Good warn rate"
              v={w30?.good_warning_rate != null
                  ? `${(Number(w30.good_warning_rate) * 100).toFixed(0)}%` : "—"}
              tone={w30?.good_warning_rate != null
                    && Number(w30.good_warning_rate) > 0.6 ? "pos" : ""} />
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// 8. Shadow timeline
// ---------------------------------------------------------------------------

function ShadowTimeline({ trades }: { trades: any[] }) {
  const closed = trades.filter(t => t.status === "closed").slice(-15);
  return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>Shadow Timeline</Label>
        <span className="u-caption-2 text-fg-3">
          last {closed.length} closed
        </span>
      </div>
      {closed.length === 0 ? (
        <div className="u-caption-2 italic text-fg-3">No closed trades.</div>
      ) : (
        <ul className="space-y-1 u-caption-2">
          {closed.reverse().map((t, i) => (
            <li key={i}
                className="grid grid-cols-[80px_70px_60px_1fr_auto]
                              items-center gap-2">
              <span className="u-mono-sm text-fg-3">{t.entry_date}</span>
              <span className="u-chip u-chip-accent">eng {t.engine}</span>
              <span className="u-mono-sm text-fg">{t.instrument ?? "ES"}</span>
              <span className="u-caption-2 text-fg-3 truncate">
                deterministic decision · advisory ML — no override
              </span>
              <span className={cn("u-mono-sm",
                Number(t.net_ret_pct) > 0 ? "text-success"
                : Number(t.net_ret_pct) < 0 ? "text-danger" : "text-fg-3")}>
                {Number(t.net_ret_pct ?? 0).toFixed(2)}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// 9. Promotion readiness checklist
// ---------------------------------------------------------------------------

function PromotionChecklist({
  promo, hyb, shadow,
}: {
  promo: ReturnType<typeof usePromotionStatus>["data"];
  hyb: ReturnType<typeof useHybridStatus>["data"];
  shadow: ReturnType<typeof useShadowLatestReport>["data"];
}) {
  const w30 = promo?.windows?.["30"];
  const ece = shadow?.latest_model_run?.calibration?.ece;
  const items = [
    { label: "Enough labels (≥30 outcomes)",
      ok: (w30?.deterministic_trades ?? 0) >= 30 },
    { label: "Healthy days (≥7)",
      ok: (promo?.promotion?.healthy_day_count ?? 0)
            >= (promo?.thresholds?.required_healthy_days ?? 7) },
    { label: "ΔSharpe vs deterministic positive",
      ok: (Number(w30?.delta_sharpe_vs_deterministic ?? 0)) > 0 },
    { label: "Calibration ECE < 0.10",
      ok: (ece ?? 999) < 0.10 },
    { label: "False avoid acceptable (<35%)",
      ok: w30?.false_avoid_rate == null
          || Number(w30.false_avoid_rate) < 0.35 },
    { label: "False allow acceptable",
      ok: w30?.missed_winner_rate == null
          || Number(w30.missed_winner_rate) < 0.5 },
    { label: "Operator approval",
      ok: false,
      hint: "Always required — never automatic" },
  ];
  return (
    <section className="u-card-tight">
      <div className="flex items-center justify-between mb-2">
        <Label>Promotion Readiness Checklist</Label>
        <span className={cn("u-chip",
          promo?.promotion?.state === "READY_FOR_PAPER_REDUCE"
            ? "u-chip-success" : "u-chip-warning")}>
          {(promo?.promotion?.state ?? "—")
              .toLowerCase().replace(/_/g, " ")}
        </span>
      </div>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="flex items-center gap-2 u-caption-2">
            <span className={cn("inline-block w-3 h-3 rounded-sm",
              it.ok ? "bg-success" : "bg-warning")} />
            <span className={it.ok ? "text-fg" : "text-fg-2"}>
              {it.label}
            </span>
            {it.hint && (
              <span className="u-caption-2 text-fg-3 italic">
                — {it.hint}
              </span>
            )}
          </li>
        ))}
      </ul>
      <div className="u-caption-2 text-fg-3 mt-3 italic">
        Mode is {hyb?.config?.mode ?? "advisory"}.
        Execution lock: {hyb?.ml_can_affect_trades ? "OFF" : "ON"}.
        ML cannot trade without flipping execution lock + operator approval.
      </div>
    </section>
  );
}


// ---------------------------------------------------------------------------
// Cells
// ---------------------------------------------------------------------------

function Cell({ k, v, tone = "" }: {
  k: string; v: string; tone?: string;
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger"
    : tone === "warn" ? "text-warning" : "text-fg";
  return (
    <div>
      <div className="u-caption-2 text-fg-3">{k}</div>
      <div className={cn("u-mono-sm font-semibold", cls)}>{v}</div>
    </div>
  );
}


function ConfusionCell({
  label, value, tone,
}: { label: string; value: number; tone: "pos" | "neg" }) {
  return (
    <div className={cn("u-card-tight text-center",
      tone === "pos" ? "u-card-tight-accent" : "u-card-tight-warning")}>
      <div className="u-caption-2 text-fg-3">{label}</div>
      <div className={cn("u-mono-sm font-semibold mt-1",
        tone === "pos" ? "text-success" : "text-danger")}>
        {value}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function _statusBar(o: {
  shadow: ReturnType<typeof useShadowLatestReport>["data"];
  promo: ReturnType<typeof usePromotionStatus>["data"];
  hyb: ReturnType<typeof useHybridStatus>["data"];
}) {
  const labeled = o.shadow?.latest_model_run?.labeled_row_count ?? 0;
  const runs = o.shadow?.prediction_counts?.n ?? 0;
  const promo_state = o.promo?.promotion?.state ?? "NOT_READY_NO_ML";
  const healthy_days = o.promo?.promotion?.healthy_day_count ?? 0;
  const required_healthy_days = o.promo?.thresholds?.required_healthy_days ?? 7;
  const next_milestone = labeled === 0
    ? "first labels (~T+5)"
    : runs < 20 ? "20+ predictions"
    : (o.promo?.windows?.["30"]?.deterministic_trades ?? 0) < 30
        ? "30+ outcomes"
    : healthy_days < required_healthy_days
        ? `${required_healthy_days}d clean`
    : "operator review";
  return {
    mode: o.hyb?.config?.mode ?? "advisory",
    runs, labeled,
    healthy_days, required_healthy_days,
    promo_state,
    next_milestone,
  };
}


function _decisionQuality(trades: any[]) {
  // Without ML predictions: TP/FP/TN/FN cannot be computed.
  // Stub with zeros and document.
  const closed = trades.filter(
    t => t.status === "closed" && t.net_ret_pct != null,
  );
  const n = 0; // require ML predictions
  return { tp: 0, fp: 0, tn: 0, fn: 0, n,
            closed_n: closed.length };
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
    if (arr.length === 0) continue;
    const mean = arr.reduce((s, x) => s + x, 0) / arr.length;
    const variance = arr.length > 1
      ? arr.reduce((s, x) => s + (x - mean) ** 2, 0) / (arr.length - 1)
      : 0;
    const sd = Math.sqrt(variance);
    const sharpe = sd > 0 ? mean / sd * Math.sqrt(252) : 0;
    const hit = arr.filter(x => x > 0).length / arr.length;
    out[k] = { n: arr.length, sharpe, hit };
  }
  return out;
}


function _confidenceBuckets(_trades: any[]) {
  // Placeholder buckets: 0.5–0.6, 0.6–0.7, …, 0.9–1.0
  return [0.5, 0.6, 0.7, 0.8, 0.9].map(lo => ({
    lo, hi: lo + 0.1, n: 0, hit: 0,
  }));
}


function _sharpeTone(s: number): string {
  if (s >= 1.0) return "text-success";
  if (s < -0.3) return "text-danger";
  if (s < 0.5) return "text-warning";
  return "text-fg";
}
