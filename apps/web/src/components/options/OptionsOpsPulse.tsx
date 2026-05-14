// Phase 6b-3-g — Ops triage pulse.
//
// Single line. Triage-first. Healthy state visually recedes.
//
// Renders:
//   "OPS · engine dormant · all checks pass"
// or:
//   "OPS · engine dormant · 1 issue: universe drift"

import { useQuery } from "@tanstack/react-query";

import { useOptionsPipelineStatus } from "@/lib/options/hooks";
import { apiGet } from "@/lib/api";


interface IntegrityShape {
  coherent_batch_present: boolean;
  provider_homogeneous:   boolean;
  universe_closure_pass:  boolean;
  freshness_bound_pass:   boolean;
  shadow_persistence_active: boolean;
}


export default function OptionsOpsPulse() {
  const { data: pipeline } = useOptionsPipelineStatus();
  const { data: integ }    = useQuery<IntegrityShape>({
    queryKey: ["options", "analytics", "integrity"],
    queryFn:  () => apiGet("/options/analytics/integrity"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const flags = integ ? [
    ["coherent batch",    integ.coherent_batch_present],
    ["provider",          integ.provider_homogeneous],
    ["universe drift",    integ.universe_closure_pass],
    ["freshness",         integ.freshness_bound_pass],
    ["shadow log",        integ.shadow_persistence_active],
  ] : [];
  const failing = flags.filter(([, v]) => !v).map(([k]) => k as string);
  const engineState = pipeline?.engine_state ?? "—";

  return (
    <div
      className="opt-research-pulse-strip opt-ops-pulse"
      data-test="options-ops-pulse"
    >
      <span className="opt-pulse-eyebrow">OPS</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        engine{" "}
        <strong className="opt-pulse-num">{engineState}</strong>
      </span>
      <span className="opt-pulse-sep">·</span>
      {failing.length === 0 ? (
        <span className="opt-pulse-ok">all checks pass</span>
      ) : (
        <span className="opt-pulse-warn">
          {failing.length} issue{failing.length === 1 ? "" : "s"}:
          {" "}{failing.join(", ")}
        </span>
      )}
    </div>
  );
}
