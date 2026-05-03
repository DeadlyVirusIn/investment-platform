// Phase OPS-ML-PROGRESS — ML Readiness Progress panel.
// Pure observability. Consumes existing endpoints only.

import { useShadowLatestReport, usePromotionStatus } from "@/lib/ml/shadow";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";


export default function MLReadinessProgressCard() {
  const shadow = useShadowLatestReport();
  const promo = usePromotionStatus();

  const loading = shadow.isLoading || promo.isLoading;
  if (loading || !shadow.data || !promo.data) {
    return (
      <div className="u-card">
        <Label>ML Readiness Progress</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  const run = shadow.data.latest_model_run;
  const totalEligible = _num(run?.row_count) ?? 0;
  const labeled = _num(run?.labeled_row_count) ?? 0;
  const labelPct = totalEligible > 0
    ? Math.round((labeled / totalEligible) * 100)
    : 0;
  const daysRemaining = _estimateDaysToFirstLabel(
    run?.created_at, labeled,
  );

  const mlState = run?.status ?? "no_runs";
  const lastRun = run?.created_at ? _fmtTs(run.created_at) : "—";

  const th = promo.data.thresholds;
  // Use the 30d window as the primary readiness gate
  const w30 = promo.data.windows["30"];
  const adviceCount = w30?.ml_advice_count ?? 0;
  const outcomesCount = w30?.deterministic_trades ?? 0;
  const advicePct = Math.min(100,
    Math.round((adviceCount / th.min_advice) * 100));
  const outcomesPct = Math.min(100,
    Math.round((outcomesCount / th.min_outcomes) * 100));
  const promoState = promo.data.promotion.state;
  const promoTone = _promoTone(promoState);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>ML Readiness Progress</Label>
          <div className="u-caption-2 mt-0.5">
            advisory only · data accumulation phase
          </div>
        </div>
        <span className={cn("u-chip", promoTone)}>
          {promoState.replace(/_/g, " ").toLowerCase()}
        </span>
      </div>

      {/* Phase 3 HI-3 — Composite radial + numeric rows side by side */}
      <div className="grid grid-cols-1 md:grid-cols-[160px_1fr]
                       gap-5 items-start mb-4">
        <ReadinessRadial
          labelPct={labelPct}
          advicePct={advicePct}
          outcomesPct={outcomesPct}
          accumulating={labeled === 0 && adviceCount === 0
                          && outcomesCount === 0}
        />
        <div className="space-y-3 min-w-0">
          <RingRow color="var(--accent)"
                   label="Labels"
                   value={`${labeled} / ${totalEligible}`}
                   pct={labelPct} />
          <RingRow color="var(--success)"
                   label="ML advice (30d)"
                   value={`${adviceCount} / ${th.min_advice}`}
                   pct={advicePct} />
          <RingRow color="var(--warning)"
                   label="Closed outcomes (30d)"
                   value={`${outcomesCount} / ${th.min_outcomes}`}
                   pct={outcomesPct} />
        </div>
      </div>

      {/* Section — ML Status */}
      <div className="mb-4">
        <div className="u-label-sm mb-1.5">ML Status</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          <KV k="Current state" v={mlState.replace(/_/g, " ").toLowerCase()}
              tone={_stateTone(mlState)} />
          <KV k="Last run"       v={lastRun} />
          <KV k="Rows scanned"   v={`${totalEligible}`} />
          <KV k="Labeled rows"   v={`${labeled}`}
              tone={labeled > 0 ? "pos" : "neutral"} />
        </div>
        <div className="u-caption-2 text-fg-3 mt-2">
          {labeled === 0 && totalEligible === 0
            ? "No eligible decisions yet — accumulating."
            : labeled === 0
              ? `~${daysRemaining ?? 5} trading day(s) until first label ` +
                `(5-day forward horizon).`
              : `Labels flowing. Continue accumulating.`}
        </div>
      </div>

      {/* Section — Hybrid Readiness numeric details */}
      <div className="mb-3">
        <div className="u-label-sm mb-1.5">Hybrid Readiness</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          <KV k="Promotion guard"
              v={promoState.replace(/_/g, " ").toLowerCase()}
              tone={promoTone === "u-chip-success" ? "pos"
                     : promoTone === "u-chip-warning" ? "warn" : "neutral"} />
          <KV k="Healthy days"
              v={`${promo.data.promotion.healthy_day_count ?? 0} / `
                  + `${th.required_healthy_days}`} />
          <KV k="Δ Sharpe"
              v={_fmtSigned(w30?.delta_sharpe_vs_deterministic)} />
          <KV k="ECE (calibration)"
              v={w30?.calibration_ece != null
                  ? w30.calibration_ece.toFixed(3) : "—"}
              tone={w30?.calibration_ece != null
                     && w30.calibration_ece > th.max_ece ? "warn" : "neutral"} />
        </div>
      </div>

      <div className="u-caption-2 text-fg-3 italic">
        ML stays advisory. Execution locked. Promotion requires operator
        approval even if all bars turn green.
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Visual primitives
// ---------------------------------------------------------------------------

// Phase 3 HI-3 — composite 3-ring readiness radial. Pure SVG, no chart lib.
function ReadinessRadial({
  labelPct, advicePct, outcomesPct, accumulating,
}: {
  labelPct: number;
  advicePct: number;
  outcomesPct: number;
  accumulating: boolean;
}) {
  const W = 140;
  const cx = W / 2;
  const cy = W / 2;
  const STROKE = 8;
  const GAP = 4;
  // Three concentric rings (outer → inner): labels, advice, outcomes
  const radii = [
    cy - STROKE / 2 - 2,
    cy - STROKE / 2 - 2 - (STROKE + GAP),
    cy - STROKE / 2 - 2 - 2 * (STROKE + GAP),
  ];
  const rings = [
    { r: radii[0], pct: labelPct,    color: "var(--accent)" },
    { r: radii[1], pct: advicePct,   color: "var(--success)" },
    { r: radii[2], pct: outcomesPct, color: "var(--warning)" },
  ];
  return (
    <div className="flex items-center justify-center"
         role="img"
         aria-label="ML readiness composite">
      <svg width={W} height={W} viewBox={`0 0 ${W} ${W}`}>
        {rings.map((ring, i) => {
          const C = 2 * Math.PI * ring.r;
          const offset = C * (1 - Math.max(0, Math.min(100, ring.pct)) / 100);
          return (
            <g key={i} transform={`rotate(-90 ${cx} ${cy})`}>
              {/* Track */}
              <circle cx={cx} cy={cy} r={ring.r}
                      stroke="var(--border-2)" strokeWidth={STROKE}
                      fill="none" />
              {/* Progress */}
              <circle cx={cx} cy={cy} r={ring.r}
                      stroke={ring.color}
                      strokeWidth={STROKE}
                      strokeLinecap="butt"
                      strokeDasharray={C}
                      strokeDashoffset={offset}
                      fill="none"
                      style={{ transition: "stroke-dashoffset 300ms ease" }}
              />
            </g>
          );
        })}
        {/* Center text */}
        <text x={cx} y={cy - 4}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize={14}
              fill="var(--text-primary)"
              fontWeight={600}>
          {accumulating ? "—" : `${Math.round((labelPct + advicePct + outcomesPct) / 3)}%`}
        </text>
        <text x={cx} y={cy + 12}
              textAnchor="middle"
              fontFamily="var(--font-ui)"
              fontSize={9}
              fill="var(--text-muted)"
              letterSpacing="0.08em">
          {accumulating ? "ACCUMULATING" : "READINESS"}
        </text>
      </svg>
    </div>
  );
}


function RingRow({
  color, label, value, pct,
}: {
  color: string; label: string; value: string; pct: number;
}) {
  return (
    <div className="grid grid-cols-[12px_1fr_auto] items-center gap-3">
      <span className="inline-block w-3 h-3 rounded-full"
            style={{ background: color }} />
      <span className="u-caption text-fg-2 truncate">{label}</span>
      <span className="u-mono-sm text-fg-3">
        {value} <span className="ml-1 text-fg">{Math.round(pct)}%</span>
      </span>
    </div>
  );
}


function KV({ k, v, tone = "neutral" }: {
  k: string; v: string;
  tone?: "pos" | "neg" | "warn" | "neutral";
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger"
    : tone === "warn" ? "text-warning" : "text-fg";
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{k}</span>
      <span className={cn("u-mono-sm font-semibold", cls)}>{v}</span>
    </div>
  );
}


// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function _num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}


function _fmtTs(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return s; }
}


function _fmtSigned(v: number | null | undefined): string {
  const n = _num(v);
  if (n == null) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(3)}`;
}


function _estimateDaysToFirstLabel(
  lastRunIso: string | null | undefined,
  labeled: number,
): number | null {
  if (labeled > 0) return 0;
  // 5-day forward horizon starting from most recent eligible decision.
  // Without a direct "oldest unlabeled decision" field, use last_run
  // as a proxy anchor.
  if (!lastRunIso) return 5;
  try {
    const last = new Date(lastRunIso);
    const ms = Date.now() - last.getTime();
    const daysElapsed = Math.floor(ms / 86_400_000);
    // Approximate trading-day horizon: 5 cal-days minus weekends
    const remaining = Math.max(0, 5 - daysElapsed);
    return remaining;
  } catch { return 5; }
}


function _stateTone(s: string): "pos" | "neg" | "warn" | "neutral" {
  if (s === "SHADOW_OUTPERFORMING") return "pos";
  if (s === "TRAINED_SHADOW") return "neutral";
  if (s.startsWith("TRAINED_BUT")) return "warn";
  if (s === "SKIPPED_LEAKAGE_RISK") return "neg";
  if (s.startsWith("SKIPPED")) return "neutral";
  return "neutral";
}


function _promoTone(s: string): string {
  if (s === "READY_FOR_PAPER_REDUCE") return "u-chip-success";
  if (s === "ADVISORY_HEALTHY")       return "u-chip-accent";
  if (s === "PAPER_REDUCE_PAUSED")    return "u-chip-warning";
  if (s.startsWith("NOT_READY"))      return "u-chip-neutral";
  return "u-chip-neutral";
}
