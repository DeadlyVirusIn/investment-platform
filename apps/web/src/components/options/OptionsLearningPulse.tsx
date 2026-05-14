// Phase 6b-3-f — Learning pulse strip.
//
// Single line. Quietly scientific tone.
//
// Renders:
//   "LEARNING · {N} of 7 gates satisfied · {D} days of coherent
//    evidence accumulated"
//
// No motivational language. No "X% complete". No celebration of
// any single gate flipping.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface ReadinessResponse {
  all_gates_pass: boolean;
  ml_options_learning_enabled: boolean;
  gates: Record<string, { pass: boolean; [k: string]: unknown }>;
}


export default function OptionsLearningPulse() {
  const { data } = useQuery<ReadinessResponse>({
    queryKey: ["options", "analytics", "learning-readiness"],
    queryFn:  () => apiGet("/options/analytics/learning-readiness"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const gates = data?.gates ?? {};
  const totalGates = Object.keys(gates).length || 7;
  const satisfied = Object.values(gates).filter(g => g.pass).length;
  const coherentDays =
    (gates["coherent_batch_days"] as { value?: number } | undefined)?.value ?? 0;

  return (
    <div
      className="opt-research-pulse-strip opt-learning-pulse"
      data-test="options-learning-pulse"
    >
      <span className="opt-pulse-eyebrow">LEARNING</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{satisfied}</strong>
        {" "}of{" "}
        <strong className="opt-pulse-num">{totalGates}</strong>
        {" "}readiness gates satisfied
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{coherentDays}</strong>
        {" "}day{coherentDays === 1 ? "" : "s"} of coherent evidence accumulated
      </span>
      {data && !data.all_gates_pass && (
        <>
          <span className="opt-pulse-sep">·</span>
          <span
            className="opt-pulse-text"
            style={{ color: "var(--fg-3)" }}
          >
            advisory state · no claim of intelligence yet
          </span>
        </>
      )}
    </div>
  );
}
