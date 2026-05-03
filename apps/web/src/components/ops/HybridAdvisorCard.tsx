// Phase ML-5 — Hybrid Advisor status + toggle card.

import { useHybridStatus } from "@/lib/ml/shadow";
import { Label } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/cn";

export default function HybridAdvisorCard() {
  const { data, isLoading } = useHybridStatus();
  const qc = useQueryClient();

  if (isLoading || !data) {
    return (
      <div className="u-card">
        <Label>Hybrid Advisor</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }
  const cfg = data.config;
  const run = data.latest_model_run;
  const last = data.recent_activity[0];

  const enabled = cfg.enabled;
  const mode = cfg.mode;
  const healthLabel = run?.status?.split("_").join(" ").toLowerCase() ?? "—";
  const healthTone = _healthTone(run?.status);
  const cal = run?.calibration;
  const cmp = run?.baseline_comparison;
  const calStr = cal?.ece != null ? cal.ece.toFixed(3) : "—";
  const deltaStr = cmp?.delta_sharpe != null
    ? cmp.delta_sharpe.toFixed(3) : "—";
  const lastMult = last != null ? last.multiplier.toFixed(2) : "—";

  const toggle = async (next: boolean) => {
    await apiPost("/ml/hybrid/toggle", { enabled: next });
    qc.invalidateQueries({ queryKey: ["ml", "hybrid", "status"] });
  };
  const setMode = async (m: "advisory" | "paper_reduce") => {
    await apiPost("/ml/hybrid/mode", { mode: m });
    qc.invalidateQueries({ queryKey: ["ml", "hybrid", "status"] });
  };

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Hybrid Advisor</Label>
          <div className="u-caption-2 mt-0.5">
            ML shadow · risk-reducing only · never executes
          </div>
        </div>
        <span className={cn("u-chip",
          enabled ? "u-chip-success" : "u-chip-neutral")}>
          {enabled ? "enabled" : "off"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
        <KV k="Mode"              v={mode} />
        <KV k="Model status"      v={healthLabel} tone={healthTone} />
        <KV k="Calibration (ECE)" v={calStr}
            tone={cal?.poor_calibration ? "warn" : "neutral"} />
        <KV k="Δ Sharpe vs base"  v={deltaStr}
            tone={cmp?.winner === "ml" ? "pos"
                   : cmp?.winner === "baseline" ? "neg" : "neutral"} />
        <KV k="Min confidence"    v={cfg.min_confidence.toFixed(2)} />
        <KV k="Max stale days"    v={`${cfg.max_stale_days}`} />
        <KV k="Last multiplier"   v={`×${lastMult}`}
            tone={last && last.multiplier < 1 ? "warn" : "neutral"} />
        <KV k="Floor"             v={`×${cfg.min_multiplier.toFixed(2)}`} />
      </div>

      {/* Recommendation */}
      <div className="u-card-tight mb-3"
           style={{ background: "var(--accent-subtle)",
                    borderColor: "rgba(75,139,255,0.25)" }}>
        <div className="u-caption text-fg">
          {_recommendation(enabled, mode, run?.status, cal, cmp)}
        </div>
      </div>

      {/* Recent activity */}
      {data.recent_activity.length > 0 && (
        <div className="mb-3">
          <div className="u-label-sm mb-1.5">Recent Hybrid Activity</div>
          <ul className="space-y-1">
            {data.recent_activity.slice(0, 5).map((r) => (
              <li key={r.trade_id} className="u-caption-2 flex gap-2">
                <span className="u-mono-sm text-fg-3 w-[88px] shrink-0">
                  {r.entry_date}
                </span>
                <span className="u-mono-sm text-fg">{r.instrument}</span>
                <span className="text-fg-3">
                  eng {r.engine ?? "—"}
                </span>
                <span className={cn(
                  "u-mono-sm ml-auto",
                  r.multiplier < 1 ? "text-warning" : "text-fg-3",
                )}>
                  ×{r.multiplier.toFixed(2)} {r.action ?? ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Actions — CF-2: real buttons, NOT status chips */}
      <div className="pt-3 border-t border-b1">
        <div className="u-label-sm mb-2">Actions</div>
        <div className="flex flex-wrap gap-2 items-center">
          <ToggleButton
            label={enabled ? "Disable advisor" : "Enable advisory"}
            tone={enabled ? "neutral" : "success"}
            pressed={enabled}
            onClick={() => toggle(!enabled)}
            title={enabled
              ? "Stop logging ML advice"
              : "Start logging ML advice (no execution)"}
          />
          {enabled && (
            <div role="group" aria-label="Advisor mode"
                  className="flex gap-1 items-center">
              <ModeButton
                label="advisory"
                pressed={mode === "advisory"}
                onClick={() => setMode("advisory")}
                title="Log ML reasoning only — paper size unchanged."
              />
              <ModeButton
                label="paper_reduce"
                pressed={mode === "paper_reduce"}
                onClick={() => setMode("paper_reduce")}
                title="Apply ML reduction to paper size. Still never touches real money."
              />
            </div>
          )}
          <span className="u-caption-2 text-fg-3 ml-auto">
            Execution locked · ML cannot trade
          </span>
        </div>
      </div>
    </div>
  );
}


// CF-2 — distinct button class. Looks like a button (1px border, label
// verb, focus ring), not a status chip. aria-pressed reflects state so
// screen readers announce toggle state correctly.
function ToggleButton({
  label, tone, pressed, onClick, title,
}: {
  label: string;
  tone: "success" | "neutral";
  pressed: boolean;
  onClick: () => void;
  title?: string;
}) {
  const base: React.CSSProperties = {
    padding: "6px 12px",
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 600,
    border: "1px solid",
    borderColor: tone === "success"
      ? "rgba(34,197,94,0.45)" : "var(--border-2)",
    color: tone === "success" ? "var(--success)" : "var(--fg-2)",
    background: "transparent",
    cursor: "pointer",
    outline: "none",
    transition: "background 120ms ease, border-color 120ms ease",
  };
  return (
    <button
      type="button"
      role="switch"
      aria-pressed={pressed}
      onClick={onClick}
      title={title}
      style={base}
      className="u-btn-toggle">
      {label}
    </button>
  );
}


function ModeButton({
  label, pressed, onClick, title,
}: {
  label: string;
  pressed: boolean;
  onClick: () => void;
  title?: string;
}) {
  const style: React.CSSProperties = {
    padding: "6px 12px",
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 500,
    border: "1px solid",
    borderColor: pressed
      ? "rgba(59,130,246,0.65)" : "var(--border-2)",
    color: pressed ? "var(--accent)" : "var(--fg-2)",
    background: pressed
      ? "rgba(59,130,246,0.10)" : "transparent",
    cursor: "pointer",
    outline: "none",
    transition: "background 120ms ease, border-color 120ms ease",
  };
  return (
    <button
      type="button"
      role="radio"
      aria-checked={pressed}
      onClick={onClick}
      title={title}
      style={style}
      className="u-btn-toggle">
      {label}
    </button>
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


function _healthTone(s: string | undefined): "pos" | "neg" | "warn" | "neutral" {
  if (!s) return "neutral";
  if (s === "SHADOW_OUTPERFORMING") return "pos";
  if (s === "TRAINED_SHADOW")       return "neutral";
  if (s.startsWith("TRAINED_BUT"))  return "warn";
  if (s === "SKIPPED_LEAKAGE_RISK") return "neg";
  if (s.startsWith("SKIPPED"))      return "neutral";
  return "neutral";
}


function _recommendation(
  enabled: boolean, mode: string, status: string | undefined,
  cal: { ece?: number; poor_calibration?: boolean } | null | undefined,
  cmp: { winner?: string; delta_sharpe?: number } | null | undefined,
): string {
  if (!enabled) {
    return "Advisor is off. Enable advisory mode to start logging ML " +
           "recommendations without reducing size.";
  }
  if (status === "SHADOW_OUTPERFORMING"
       && cmp?.winner === "ml"
       && !cal?.poor_calibration
       && mode === "advisory") {
    return "ML is outperforming baseline with clean calibration. Once " +
           "advisory log has 7–14 days of stable reductions, consider " +
           "moving to paper_reduce.";
  }
  if (mode === "paper_reduce" && status !== "SHADOW_OUTPERFORMING") {
    return "paper_reduce is active but latest model is not outperforming " +
           "baseline. Revert to advisory until model health is green.";
  }
  if (cal?.poor_calibration) {
    return "Calibration is poor (ECE too high). ML reduction will not " +
           "apply until calibration recovers.";
  }
  return "Collecting shadow evidence. ML multiplier will only apply when " +
         "all gates pass.";
}
