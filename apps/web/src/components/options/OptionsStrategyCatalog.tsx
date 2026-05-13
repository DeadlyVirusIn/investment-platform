// Phase Opt-C1 Step 1 — Supported strategy catalog.
//
// Reads /api/options/strategies (existing endpoint). Renders a
// responsive grid of strategy families (one card per family
// returned by the endpoint) with calm explainer copy. Visible
// in dormant mode AND active mode (always educational).
//
// Discipline: NO suggestions, NO recommendations, NO confidence
// scores. Pure catalog — what the engine CAN evaluate, not what
// it IS evaluating.
//
// Terminology note: per-strategy `criteria` are the strategy's
// own structural rules (legs, deltas, IV-rank, etc.) and are
// distinct from the universal 7 quality-check filters surfaced
// in OptionsRejectionsSection. To avoid the collision we label
// these here as "strategy criteria", never "quality checks".

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface StrategyCriterion {
  code: string;
  label: string;
  description: string;
}


interface StrategyEntry {
  rule_id: string;
  name: string;
  summary: string;
  criteria: StrategyCriterion[];
}


interface StrategiesResponse {
  notice: string;
  observation_only_notice: string;
  strategies: StrategyEntry[];
}


// Direction tag derived from strategy name — kept plain.
function _directionFor(name: string): string {
  const lower = name.toLowerCase();
  if (lower.includes("bull") || lower.includes("long call")) return "directional ↑";
  if (lower.includes("bear") || lower.includes("long put"))  return "directional ↓";
  if (lower.includes("iron condor"))                          return "neutral · range";
  if (lower.includes("straddle") || lower.includes("strangle")) return "volatility";
  if (lower.includes("calendar"))                             return "time decay";
  if (lower.includes("credit"))                               return "premium harvest";
  return "defined risk";
}


function useOptionsStrategies() {
  return useQuery<StrategiesResponse>({
    queryKey: ["options", "strategies-catalog"],
    queryFn: () => apiGet<StrategiesResponse>("/options/strategies"),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


export default function OptionsStrategyCatalog() {
  const { data, isLoading } = useOptionsStrategies();
  const strategies = data?.strategies ?? [];

  return (
    <section className="u-card opt-card" data-test="options-strategy-catalog">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Supported strategy families</span>
        <span className="opt-card-meta">
          {isLoading
            ? "loading…"
            : `${strategies.length} famil${strategies.length === 1 ? "y" : "ies"} · ${strategies.reduce(
                (n, s) => n + s.criteria.length, 0
              )} strategy criteria`}
        </span>
      </header>

      <p className="opt-explain-body" style={{ marginBottom: 12 }}>
        These are the strategy templates the engine can evaluate.
        When live, candidates must satisfy each strategy's own
        criteria (and the universal quality-check filters) before
        promotion.
      </p>

      <div className="opt-strategy-grid">
        {strategies.map((s) => (
          <div
            key={s.rule_id}
            className="opt-strategy-card"
            data-rule-id={s.rule_id}
          >
            <div className="opt-strategy-name">{s.name}</div>
            <div className="opt-strategy-direction">{_directionFor(s.name)}</div>
            <p className="opt-strategy-summary">{s.summary}</p>
            <div className="opt-strategy-checks">
              {s.criteria.length} strategy criteri{s.criteria.length === 1 ? "on" : "a"}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
