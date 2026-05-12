// Phase 16 v1 — IntradayContextLine.
//
// Renders a calm one-line intraday context annotation below a holding's
// glance row. Reads the backend's ephemeral overlay endpoint
// `/api/recommendations/{rec_id}/intraday-context`. Renders nothing
// when:
//   - The feature flag (INTRADAY_OVERLAY_ENABLED) is off — endpoint
//     returns 404 "overlay disabled"
//   - No overlay entry exists for the recommendation_id — endpoint
//     returns 404 "no overlay entry for recommendation_id"
//   - The underlying tape data is stale (`stale: true`)
//   - The label is "quiet" (no observation worth surfacing) or
//     "windfall" (deferred per arch doc §9 v1 scope)
//
// Strict v1 scope:
//   - Renders only "aligned", "drift", "stress" — three labels
//   - No animation, no color flash, no live indicator
//   - 11px italic, var(--fg-3), single-line wraps on mobile
//   - Hover tooltip carries the source + delay disclosure
//   - Symbol -> recommendation_id resolved via the existing latest-
//     picks query (shared cache; no new endpoint)

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


// Lightweight rec-lookup row. Only the two fields this component
// needs from the /api/recommendations payload — id (the recommendation_id
// used as overlay key) and symbol (the holding symbol we match on).
interface RecLookupRow {
  id: string;
  symbol: string | null;
}


interface RecLookupResponse {
  recommendations: RecLookupRow[];
  count: number;
}


interface IntradayContextResponse {
  recommendation_id: string;
  symbol: string;
  intraday_change_pct: number | null;
  vs_recommendation_entry_pct: number | null;
  vs_macro_drift_pct: number | null;
  context_label: "aligned" | "drift" | "stress" | "quiet" | "windfall";
  derived_at: string | null;
  quote_ts: string | null;
  source: string;
  delay_minutes: number;
  stale: boolean;
}


// Shared latest-recommendations lookup — sorted by generated_at desc
// so EVERY asset's latest rec is in scope (the default sort_by=confidence
// truncation in fetchPicks() would drop hold-action holdings like HR).
// limit=1000 is the backend cap; covers ~all assets since the universe
// has ~1k recs total. Cached 5 min so multiple cards share the fetch.
function useLatestRecLookup() {
  return useQuery<RecLookupResponse>({
    queryKey: ["intraday-context", "rec-lookup"],
    queryFn: () => apiGet<RecLookupResponse>(
      "/recommendations?latest=true&sort_by=generated_at&order=desc&limit=1000",
    ),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}


function useIntradayContext(rec_id: string | null) {
  return useQuery<IntradayContextResponse | null>({
    queryKey: ["intraday-context", rec_id],
    queryFn: async () => {
      if (!rec_id) return null;
      try {
        return await apiGet<IntradayContextResponse>(
          `/recommendations/${rec_id}/intraday-context`,
        );
      } catch {
        // 404 (overlay disabled or no entry) -> render nothing.
        // Network/transport errors -> also render nothing (calm).
        return null;
      }
    },
    enabled: !!rec_id,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });
}


function fmtPct(v: number | null): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}


function copyForLabel(ctx: IntradayContextResponse): string | null {
  switch (ctx.context_label) {
    case "aligned":
      return `Today aligned · ${ctx.symbol} ${fmtPct(ctx.intraday_change_pct)} vs morning thesis`;
    case "drift":
      return `Today drifting · ${ctx.symbol} ${fmtPct(ctx.intraday_change_pct)}, watching`;
    case "stress": {
      const drift = ctx.vs_macro_drift_pct;
      const driftClause = drift != null ? ` · ${fmtPct(drift)} vs SPY` : "";
      return `Today under stress · ${ctx.symbol} ${fmtPct(ctx.vs_recommendation_entry_pct)} vs entry${driftClause}`;
    }
    // "quiet" + "windfall" + any unknown future label -> render nothing
    default:
      return null;
  }
}


export interface IntradayContextLineProps {
  symbol: string;
}


export default function IntradayContextLine({ symbol }: IntradayContextLineProps) {
  const lookupQ = useLatestRecLookup();
  const rec = lookupQ.data?.recommendations?.find(r => r.symbol === symbol);
  const rec_id = rec?.id ?? null;
  const ctxQ = useIntradayContext(rec_id);
  const ctx = ctxQ.data;

  if (!ctx) return null;          // 404, network error, or still loading
  if (ctx.stale) return null;     // tape behind STALE_AFTER_SECONDS
  const copy = copyForLabel(ctx);
  if (copy === null) return null; // quiet / windfall / unknown

  return (
    <div
      className="intraday-context-line"
      data-context-label={ctx.context_label}
      data-symbol={ctx.symbol}
      title={`${ctx.delay_minutes}m delayed · ${ctx.source}`}
      role="note"
    >
      {copy}
    </div>
  );
}
