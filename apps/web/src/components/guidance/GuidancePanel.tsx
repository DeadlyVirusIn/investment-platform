// Phase SYSTEM-UI-BEGINNER v3 — unified gate source + working Explain
// toggle + spec-correct message logic.

import { useEffect, useState } from "react";
import { useUIMode } from "@/lib/ui/mode";
import { useGateStatus } from "@/lib/gates/hooks";
import type { GateRow, EngineArming, GateStatus } from "@/lib/gates/hooks";
import type {
  CurrentState, PaperSummary, AnomalySummary,
} from "@/lib/operator/types";
import { cn } from "@/lib/cn";

const LS_KEY = "GUIDANCE_COLLAPSED";

const GATE_KEYS = [
  "rates_calm", "vrp_supportive",
  "credit_stable", "liquidity_expanding",
] as const;

const GATE_LABELS: Record<string, string> = {
  rates_calm:          "Rates",
  vrp_supportive:      "Volatility",
  credit_stable:       "Credit conditions",
  liquidity_expanding: "Liquidity",
};

const GATE_FAIL_HINTS: Record<string, string> = {
  rates_calm:          "rates not calm",
  vrp_supportive:      "vol premium not supportive",
  credit_stable:       "credit not aligned",
  liquidity_expanding: "liquidity not expanding",
};


export default function GuidancePanel({
  state, anomSummary,
}: {
  state: CurrentState | undefined;
  summary?: PaperSummary | undefined;
  anomSummary: AnomalySummary | undefined;
}) {
  const [mode] = useUIMode();
  const { data: gs, isLoading: gsLoading } = useGateStatus();

  const [expanded, setExpanded] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const v = window.localStorage.getItem(LS_KEY);
    // Legacy key stored "1" = collapsed; invert → expanded = !("1")
    return v === "0";
  });
  useEffect(() => {
    window.localStorage.setItem(LS_KEY, expanded ? "0" : "1");
  }, [expanded]);

  if (mode !== "guided") return null;

  const toggleExplain = () => setExpanded(prev => !prev);

  // Single source of truth — prefer /api/gates/status; else derive from
  // state.context_values. Both must use the same GATE_KEYS count so the
  // number displayed in the header and in Explain cannot diverge.
  const gates = resolveGates(gs, state);

  // Loading state: no hero data AND gates API still resolving.
  if (gates == null) {
    return (
      <div className="u-guidance-card mt-4">
        <div className="flex items-center justify-between">
          <span className="u-caption text-fg-2 truncate mr-2">
            {gsLoading ? "Loading gate status…"
                        : "Gate status unavailable."}
          </span>
          <button
            className="u-chip u-chip-accent shrink-0"
            disabled
            title="Waiting for gate data">
            Explain
          </button>
        </div>
      </div>
    );
  }

  const { passing, total, rows } = gates;

  const crit = anomSummary?.by_severity?.critical ?? 0;
  const action = deriveBestAction({ passing, total, crit,
                                       fire: state?.fire });
  const headline = buildHeadline({ passing, total }) + ". " + action;

  return (
    <div className="u-guidance-card mt-4">
      <div className="flex items-center justify-between">
        <span className="u-caption text-fg-2 truncate mr-2">{headline}</span>
        <button
          className="u-chip u-chip-accent shrink-0"
          aria-expanded={expanded}
          onClick={toggleExplain}
          title={expanded ? "Hide details" : "Show gate + engine details"}>
          {expanded ? "Collapse" : "Explain"}
        </button>
      </div>

      {expanded && (
        <ExplainSection rows={rows} engines={gs?.engine_arming ?? []}
                         state={state} action={action}
                         onCollapse={() => setExpanded(false)} />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Explain section — never returns null, always renders something useful.
// ---------------------------------------------------------------------------

function ExplainSection({
  rows, engines, state, action, onCollapse,
}: {
  rows: ExplainRow[];
  engines: EngineArming[];
  state: CurrentState | undefined;
  action: string;
  onCollapse: () => void;
}) {
  const passingRows = rows.filter(r => r.status === "pass");
  const failingRows = rows.filter(r => r.status === "fail");
  const regime =
    state?.context_values?.stress_regime ? "stress"
    : state?.context_values?.directional_regime ? "directional"
    : "neutral";

  return (
    <div className="mt-3 space-y-3">
      <div>
        <div className="u-label-sm mb-1">Regime</div>
        <div className="u-caption text-fg">{regime}</div>
      </div>

      {passingRows.length > 0 && (
        <div>
          <div className="u-label-sm mb-1">Passing</div>
          <ul>
            {passingRows.map(r => (
              <li key={r.gate_id} className="u-gate-row">
                <span className="u-gate-ok">✓</span>
                <span className="u-caption text-fg-2">{r.name}</span>
                <span className="u-caption-2 ml-auto">{r.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {failingRows.length > 0 && (
        <div>
          <div className="u-label-sm mb-1">Waiting</div>
          <ul>
            {failingRows.map(r => (
              <li key={r.gate_id} className="u-gate-row">
                <span className="u-gate-fail">✗</span>
                <span className="u-caption text-fg-2">{r.name}</span>
                <span className="u-caption-2 ml-auto">{r.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {engines.length > 0 && (
        <div>
          <div className="u-label-sm mb-1">Engines</div>
          <ul>
            {engines.map(e => (
              <li key={e.engine} className="u-gate-row">
                <span className={cn(
                  e.status === "armed" ? "u-gate-ok" : "u-gate-unknown",
                )}>
                  {e.status === "armed" ? "●" : "○"}
                </span>
                <span className="u-caption text-fg-2">{e.engine}</span>
                <span className="u-caption-2 ml-auto">{e.plain_english}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="u-card-tight"
           style={{ background: "var(--accent-subtle)",
                    borderColor: "rgba(75,139,255,0.25)" }}>
        <div className="u-label-sm mb-1">User guidance</div>
        <div className="u-plain text-fg">{action}</div>
      </div>

      <div className="flex justify-end">
        <button className="u-chip u-chip-neutral shrink-0"
                onClick={onCollapse}>
          Collapse
        </button>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Gate resolution — unified single source of truth.
// ---------------------------------------------------------------------------

interface ExplainRow {
  gate_id: string;
  name: string;
  status: "pass" | "fail";
  detail: string;
}

interface ResolvedGates {
  passing: number;
  total: number;
  rows: ExplainRow[];
}

function resolveGates(
  gs: GateStatus | undefined,
  state: CurrentState | undefined,
): ResolvedGates | null {
  // Preferred: full API response
  if (gs && gs.summary && Array.isArray(gs.gates) && gs.gates.length > 0) {
    return {
      passing: gs.summary.passing,
      total: gs.summary.total,
      rows: gs.gates
        .filter(g => g.status === "pass" || g.status === "fail")
        .map((g: GateRow) => ({
          gate_id: g.gate_id,
          name: g.name,
          status: g.status as "pass" | "fail",
          detail: g.status === "pass"
            ? g.plain_english : g.what_would_make_it_pass,
        })),
    };
  }
  // Fallback: derive from hero state.context_values using same GATE_KEYS
  const ctx = state?.context_values as Record<string, boolean> | undefined;
  if (ctx) {
    const rows: ExplainRow[] = GATE_KEYS.map(k => ({
      gate_id: k,
      name: GATE_LABELS[k] ?? k,
      status: ctx[k] === true ? "pass" : "fail",
      detail: ctx[k] === true
        ? "aligned"
        : (GATE_FAIL_HINTS[k] ?? "not aligned"),
    }));
    const passing = rows.filter(r => r.status === "pass").length;
    return { passing, total: GATE_KEYS.length, rows };
  }
  return null;
}


// ---------------------------------------------------------------------------
// Message logic — per spec, NO contradictions.
// ---------------------------------------------------------------------------

function buildHeadline({
  passing, total,
}: { passing: number; total: number }): string {
  if (passing === total) {
    return "All gates aligned — system ready";
  }
  if (passing === 0) {
    return "No gates passing — system defensive";
  }
  return `${passing}/${total} gates passing — waiting for confirmation`;
}


function deriveBestAction({
  passing, total, crit, fire,
}: {
  passing: number;
  total: number;
  crit: number;
  fire?: boolean;
}): string {
  if (crit > 0) return "Best action: review — pause new entries.";
  if (fire) return "Best action: monitor — system is trading.";
  if (passing === total) {
    return "Best action: monitor — trade-ready window open.";
  }
  if (passing >= total - 1) {
    return "Best action: monitor — close to a high-quality setup.";
  }
  return "Best action: wait, or enable paper-only exploratory mode.";
}
