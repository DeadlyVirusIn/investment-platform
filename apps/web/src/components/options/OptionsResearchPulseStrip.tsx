// Phase 6b-3-d — Compact pulse strip on Research.
//
// Single-line orientation. NOT a full hero (the full hero lives on
// Overview). Research is a workstation, so the pulse strip just
// keeps the operator anchored:
//
//   "Today · 7,495 contracts · tradier-sandbox · 1.8 h ago · ✓ within bounds"
//
// Discipline:
//   * Read-only. Two endpoint reads (cached).
//   * No buttons. No mutation.
//   * Falls back to skeleton text on cold fetch.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface IntegrityShape {
  run_date: string;
  coherent_batch_present: boolean;
  freshness_bound_pass: boolean;
  active_batch: null | {
    provider: string;
    provider_version: string;
    age_seconds: number;
    age_hours: number;
  };
  thresholds: { max_run_chain_age_hours: number };
}

interface DailyShape {
  series: Array<{ run_date: string; total: number; would_trade: number }>;
}


function _humanDelta(secs: number): string {
  if (secs < 60) return `${Math.round(secs)} s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)} m ago`;
  if (secs < 86400) {
    const h = Math.floor(secs / 3600);
    const m = Math.round((secs % 3600) / 60);
    return m === 0 ? `${h} h ago` : `${h} h ${m} m ago`;
  }
  return `${Math.floor(secs / 86400)} d ago`;
}


export default function OptionsResearchPulseStrip() {
  const { data: integ } = useQuery<IntegrityShape>({
    queryKey: ["options", "analytics", "integrity"],
    queryFn: () => apiGet("/options/analytics/integrity"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });
  const { data: daily } = useQuery<DailyShape>({
    queryKey: ["options", "analytics", "daily-counts", 1],
    queryFn: () => apiGet("/options/analytics/daily-counts?days=1"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const today = daily?.series?.[0];
  const contracts = today?.total ?? null;
  const candidates = today?.would_trade ?? null;
  const provider = integ?.active_batch?.provider_version ?? "—";
  const ageStr = integ?.active_batch
    ? _humanDelta(integ.active_batch.age_seconds) : "—";
  const withinBounds = integ?.freshness_bound_pass ?? false;
  const coherent = integ?.coherent_batch_present ?? false;

  return (
    <div
      className="opt-research-pulse-strip"
      data-test="options-research-pulse-strip"
    >
      <span className="opt-pulse-eyebrow">RESEARCH</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        {contracts == null ? "loading…" : (
          <>
            <strong className="opt-pulse-num">
              {contracts.toLocaleString()}
            </strong>
            {" contracts evaluated"}
            {", "}
            <strong className="opt-pulse-num">
              {(candidates ?? 0).toLocaleString()}
            </strong>
            {" passed all filters"}
          </>
        )}
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">{provider}</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">{ageStr}</span>
      {(coherent && withinBounds) && (
        <>
          <span className="opt-pulse-sep">·</span>
          <span className="opt-pulse-ok">✓ within bounds</span>
        </>
      )}
      {!coherent && (
        <>
          <span className="opt-pulse-sep">·</span>
          <span className="opt-pulse-warn">! no coherent batch</span>
        </>
      )}
      {coherent && !withinBounds && (
        <>
          <span className="opt-pulse-sep">·</span>
          <span className="opt-pulse-warn">! freshness exceeded</span>
        </>
      )}
    </div>
  );
}
